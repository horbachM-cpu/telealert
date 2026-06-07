from __future__ import annotations

import io
import unittest

from telealert.cli import _fallback_confirmation, run
from telealert.errors import MissingConfigurationError, SecretStoreError, SecretStoreUnavailableError, TelegramDeliveryError
from telealert.secrets import DefaultSecretStore, SecretStore, TelegramConfig

BOT_TOKEN = "TELEGRAM_BOT_TOKEN_PLACEHOLDER"
CHAT_ID = "TELEGRAM_CHAT_ID_PLACEHOLDER"


class MemorySecretStore(SecretStore):
    def __init__(self, config: TelegramConfig | None = None) -> None:
        self.config = config
        self.cleared = False

    def load(self) -> TelegramConfig:
        if self.config is None:
            raise MissingConfigurationError("telealert is not configured. Run `telealert setup` first.")
        return self.config

    def save(self, config: TelegramConfig) -> None:
        self.config = config

    def clear(self) -> None:
        self.config = None
        self.cleared = True


class UnavailableSecretStore(SecretStore):
    def load(self) -> TelegramConfig:
        raise SecretStoreUnavailableError("keyring unavailable for test.")

    def save(self, config: TelegramConfig) -> None:
        raise SecretStoreUnavailableError("keyring unavailable for test.")

    def clear(self) -> None:
        raise SecretStoreUnavailableError("keyring unavailable for test.")


class RecordingTelegramClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, object]] = []

    def send_message(self, bot_token: str, chat_id: str, text: str, options: object) -> None:
        self.calls.append((bot_token, chat_id, text, options))


class FailingTelegramClient:
    def __init__(self, message: str) -> None:
        self.message = message

    def send_message(self, bot_token: str, chat_id: str, text: str, options: object) -> None:
        raise TelegramDeliveryError(self.message)


class CliTests(unittest.TestCase):
    def test_missing_configuration_returns_exit_1(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = run(
            ["Build", "fertig"],
            secret_store=MemorySecretStore(),
            telegram_client=RecordingTelegramClient(),
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(code, 1)
        self.assertIn("not configured", stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")

    def test_empty_message_returns_exit_3(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = run(
            ["   "],
            secret_store=MemorySecretStore(TelegramConfig(BOT_TOKEN, CHAT_ID)),
            telegram_client=RecordingTelegramClient(),
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(code, 3)
        self.assertIn("message must not be empty", stderr.getvalue())

    def test_successful_message_uses_configured_secret_values(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        client = RecordingTelegramClient()

        code = run(
            ["--title", "Build", "--silent", "Tests", "bestanden"],
            secret_store=MemorySecretStore(TelegramConfig(BOT_TOKEN, CHAT_ID)),
            telegram_client=client,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(stdout.getvalue(), "Telegram message sent.\n")
        bot_token, chat_id, text, options = client.calls[0]
        self.assertEqual(bot_token, BOT_TOKEN)
        self.assertEqual(chat_id, CHAT_ID)
        self.assertEqual(text, "Build\n\nTests bestanden")
        self.assertTrue(options.silent)

    def test_markdown_message_is_converted_to_telegram_html(self) -> None:
        client = RecordingTelegramClient()

        code = run(
            ["--markdown", "**Build fertig**"],
            secret_store=MemorySecretStore(TelegramConfig(BOT_TOKEN, CHAT_ID)),
            telegram_client=client,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )

        self.assertEqual(code, 0)
        _, _, text, options = client.calls[0]
        self.assertEqual(text, "<b>Build fertig</b>")
        self.assertEqual(options.parse_mode, "HTML")

    def test_telegram_error_response_returns_exit_2(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = run(
            ["Build", "fertig"],
            secret_store=MemorySecretStore(TelegramConfig(BOT_TOKEN, CHAT_ID)),
            telegram_client=FailingTelegramClient("Telegram could not reach the configured chat ID."),
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("configured chat ID", stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")

    def test_secret_values_are_redacted_from_errors(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = run(
            ["Build", "fertig"],
            secret_store=MemorySecretStore(TelegramConfig(BOT_TOKEN, CHAT_ID)),
            telegram_client=FailingTelegramClient(f"bad token {BOT_TOKEN} and chat {CHAT_ID}"),
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertNotIn(BOT_TOKEN, stderr.getvalue())
        self.assertNotIn(CHAT_ID, stderr.getvalue())
        self.assertIn("[redacted]", stderr.getvalue())

    def test_setup_saves_prompted_values_without_printing_them(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        store = MemorySecretStore()

        code = run(
            ["setup"],
            secret_store=store,
            telegram_client=RecordingTelegramClient(),
            stdout=stdout,
            stderr=stderr,
            token_prompt=lambda prompt: BOT_TOKEN,
            chat_id_prompt=lambda prompt: CHAT_ID,
        )

        self.assertEqual(code, 0)
        self.assertEqual(store.config, TelegramConfig(BOT_TOKEN, CHAT_ID))
        self.assertNotIn(BOT_TOKEN, stdout.getvalue())
        self.assertNotIn(CHAT_ID, stdout.getvalue())

    def test_default_store_uses_primary_and_clears_fallback_after_setup(self) -> None:
        primary = MemorySecretStore()
        fallback = MemorySecretStore(TelegramConfig(BOT_TOKEN, CHAT_ID))
        store = DefaultSecretStore(primary=primary, fallback=fallback, allow_fallback=lambda reason: False)

        updated = TelegramConfig("TELEGRAM_BOT_TOKEN_PLACEHOLDER_UPDATED", "TELEGRAM_CHAT_ID_PLACEHOLDER_UPDATED")

        store.save(updated)

        self.assertEqual(primary.config, updated)
        self.assertIsNone(fallback.config)
        self.assertTrue(fallback.cleared)

    def test_default_store_requires_confirmation_before_dpapi_fallback(self) -> None:
        fallback = MemorySecretStore()
        reasons: list[str] = []
        store = DefaultSecretStore(
            primary=UnavailableSecretStore(),
            fallback=fallback,
            allow_fallback=lambda reason: reasons.append(reason) or True,
        )

        store.save(TelegramConfig(BOT_TOKEN, CHAT_ID))

        self.assertEqual(fallback.config, TelegramConfig(BOT_TOKEN, CHAT_ID))
        self.assertEqual(reasons, ["keyring unavailable for test."])

    def test_default_store_declines_dpapi_fallback_without_saving(self) -> None:
        fallback = MemorySecretStore()
        store = DefaultSecretStore(
            primary=UnavailableSecretStore(),
            fallback=fallback,
            allow_fallback=lambda reason: False,
        )

        with self.assertRaises(SecretStoreError):
            store.save(TelegramConfig(BOT_TOKEN, CHAT_ID))

        self.assertIsNone(fallback.config)

    def test_cli_setup_with_confirmed_fallback_does_not_print_secrets(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        fallback = MemorySecretStore()
        store = DefaultSecretStore(
            primary=UnavailableSecretStore(),
            fallback=fallback,
            allow_fallback=lambda reason: True,
        )

        code = run(
            ["setup"],
            secret_store=store,
            telegram_client=RecordingTelegramClient(),
            stdout=stdout,
            stderr=stderr,
            token_prompt=lambda prompt: BOT_TOKEN,
            chat_id_prompt=lambda prompt: CHAT_ID,
        )

        self.assertEqual(code, 0)
        self.assertEqual(fallback.config, TelegramConfig(BOT_TOKEN, CHAT_ID))
        self.assertNotIn(BOT_TOKEN, stdout.getvalue())
        self.assertNotIn(CHAT_ID, stdout.getvalue())

    def test_fallback_confirmation_warns_and_requires_yes(self) -> None:
        stderr = io.StringIO()
        prompts: list[str] = []
        confirm = _fallback_confirmation(stderr, lambda prompt: prompts.append(prompt) or "ja")

        self.assertTrue(confirm("Python package `keyring` is not installed."))
        self.assertIn("Warning:", stderr.getvalue())
        self.assertIn("DPAPI", stderr.getvalue())
        self.assertEqual(prompts, ["Use DPAPI fallback anyway? [y/N]: "])


if __name__ == "__main__":
    unittest.main()
