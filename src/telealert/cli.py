from __future__ import annotations

import getpass
import sys
from dataclasses import dataclass
from typing import Callable, Sequence, TextIO

from .errors import InvalidUsageError, MissingConfigurationError, SecretStoreError, TelegramDeliveryError, TelealertError
from .markdown import markdown_to_telegram_html, plain_to_telegram_html
from .redaction import redact
from .secrets import DefaultSecretStore, SecretStore, TelegramConfig
from .telegram import SendOptions, TelegramClient

USAGE = """Usage:
  telealert setup
  telealert status
  telealert clear
  telealert [--title TITLE] [--silent] [--markdown] MESSAGE...
"""


@dataclass(frozen=True)
class ParsedSend:
    message: str
    title: str | None
    silent: bool
    markdown: bool


def main(argv: Sequence[str] | None = None) -> int:
    return run(argv if argv is not None else sys.argv[1:])


def run(
    argv: Sequence[str],
    *,
    secret_store: SecretStore | None = None,
    telegram_client: TelegramClient | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    token_prompt: Callable[[str], str] | None = None,
    chat_id_prompt: Callable[[str], str] | None = None,
    fallback_prompt: Callable[[str], str] | None = None,
) -> int:
    out = stdout or sys.stdout
    err = stderr or sys.stderr
    fallback_input = fallback_prompt or input
    store = secret_store or DefaultSecretStore(allow_fallback=_fallback_confirmation(err, fallback_input))
    client = telegram_client or TelegramClient()
    token_input = token_prompt or getpass.getpass
    chat_input = chat_id_prompt or getpass.getpass

    known_secrets: list[str] = []
    try:
        return _run(argv, store, client, out, token_input, chat_input, known_secrets)
    except TelealertError as exc:
        print(redact(exc, known_secrets), file=err)
        return exc.exit_code
    except Exception as exc:
        print(redact(f"unexpected telealert error: {exc}", known_secrets), file=err)
        return 2


def _run(
    argv: Sequence[str],
    store: SecretStore,
    client: TelegramClient,
    out: TextIO,
    token_input: Callable[[str], str],
    chat_input: Callable[[str], str],
    known_secrets: list[str],
) -> int:
    if not argv or argv[0] in {"-h", "--help"}:
        print(USAGE, file=out, end="")
        return 0 if argv and argv[0] in {"-h", "--help"} else 3

    command = argv[0]
    if command == "setup":
        _require_exact_arity(argv, 1, "setup does not accept arguments.")
        return _setup(store, out, token_input, chat_input)
    if command == "status":
        _require_exact_arity(argv, 1, "status does not accept arguments.")
        return _status(store, out)
    if command == "clear":
        _require_exact_arity(argv, 1, "clear does not accept arguments.")
        store.clear()
        print("telealert secrets cleared.", file=out)
        return 0

    parsed = _parse_send(argv)
    config = store.load()
    known_secrets.extend(config.secret_values())
    text, parse_mode = _format_message(parsed)
    client.send_message(config.bot_token, config.chat_id, text, SendOptions(parsed.title, parsed.silent, parse_mode))
    print("Telegram message sent.", file=out)
    return 0


def _setup(
    store: SecretStore,
    out: TextIO,
    token_input: Callable[[str], str],
    chat_input: Callable[[str], str],
) -> int:
    bot_token = token_input("Telegram Bot Token: ").strip()
    chat_id = chat_input("Telegram Chat ID: ").strip()

    if not bot_token or not chat_id:
        raise SecretStoreError("bot token and chat ID are required.")

    store.save(TelegramConfig(bot_token=bot_token, chat_id=chat_id))
    print("telealert secrets saved in the local OS credential store.", file=out)
    return 0


def _status(store: SecretStore, out: TextIO) -> int:
    try:
        configured = store.status()
    except SecretStoreError:
        configured = False

    if configured:
        print("telealert is configured: bot token present, chat ID present.", file=out)
    else:
        print("telealert is not configured. Run `telealert setup`.", file=out)
    return 0


def _parse_send(argv: Sequence[str]) -> ParsedSend:
    title: str | None = None
    silent = False
    markdown = False
    message_parts: list[str] = []

    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--title":
            index += 1
            if index >= len(argv) or not argv[index].strip():
                raise InvalidUsageError("--title requires a non-empty value.")
            title = argv[index]
        elif arg == "--silent":
            silent = True
        elif arg == "--markdown":
            markdown = True
        elif arg.startswith("-"):
            raise InvalidUsageError(f"unknown option: {arg}\n{USAGE}")
        else:
            message_parts.extend(argv[index:])
            break
        index += 1

    message = " ".join(message_parts).strip()
    if not message:
        raise InvalidUsageError(f"message must not be empty.\n{USAGE}")

    return ParsedSend(message=message, title=title, silent=silent, markdown=markdown)


def _format_message(parsed: ParsedSend) -> tuple[str, str | None]:
    if parsed.markdown:
        body = markdown_to_telegram_html(parsed.message)
        if parsed.title:
            text = f"<b>{plain_to_telegram_html(parsed.title)}</b>\n\n{body}"
        else:
            text = body
        return text, "HTML"

    if parsed.title:
        return f"{parsed.title}\n\n{parsed.message}", None
    return parsed.message, None


def _require_exact_arity(argv: Sequence[str], expected: int, message: str) -> None:
    if len(argv) != expected:
        raise InvalidUsageError(f"{message}\n{USAGE}")


def _fallback_confirmation(err: TextIO, prompt: Callable[[str], str]) -> Callable[[str], bool]:
    def confirm(reason: str) -> bool:
        print(f"Warning: {reason}", file=err)
        print(
            "telealert can fall back to a Windows DPAPI-encrypted local file instead of keyring. "
            "Use this only if you accept that the secret will not be visible in Windows Credential Manager.",
            file=err,
        )
        answer = prompt("Use DPAPI fallback anyway? [y/N]: ")
        return answer.strip().lower() in {"y", "yes", "j", "ja"}

    return confirm
