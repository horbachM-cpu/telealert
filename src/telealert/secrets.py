from __future__ import annotations

import base64
import ctypes
import importlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import MissingConfigurationError, SecretStoreError, SecretStoreUnavailableError

_STORE_VERSION = 1
_PURPOSE = b"telealert.local.dpapi.v1"
_KEYRING_SERVICE = "telealert"
_KEYRING_BOT_TOKEN_ACCOUNT = "telegram_bot_token"
_KEYRING_CHAT_ID_ACCOUNT = "telegram_chat_id"


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    chat_id: str

    def secret_values(self) -> list[str]:
        return [self.bot_token, self.chat_id]


class SecretStore:
    def load(self) -> TelegramConfig:
        raise NotImplementedError

    def save(self, config: TelegramConfig) -> None:
        raise NotImplementedError

    def clear(self) -> None:
        raise NotImplementedError

    def status(self) -> bool:
        try:
            self.load()
        except MissingConfigurationError:
            return False
        return True


class KeyringSecretStore(SecretStore):
    """Stores Telegram settings in the OS credential store through keyring."""

    backend_label = "Windows Credential Manager"

    def __init__(self, service_name: str = _KEYRING_SERVICE) -> None:
        self.service_name = service_name

    def load(self) -> TelegramConfig:
        keyring_module = _load_keyring_module()
        try:
            bot_token = keyring_module.get_password(self.service_name, _KEYRING_BOT_TOKEN_ACCOUNT)
            chat_id = keyring_module.get_password(self.service_name, _KEYRING_CHAT_ID_ACCOUNT)
        except Exception as exc:
            raise SecretStoreUnavailableError("keyring could not read from the OS credential store.") from exc

        if bot_token is None and chat_id is None:
            raise MissingConfigurationError("telealert is not configured. Run `telealert setup` first.")
        if not bot_token or not chat_id:
            raise MissingConfigurationError("telealert is not fully configured. Run `telealert setup` again.")

        return TelegramConfig(bot_token=bot_token, chat_id=chat_id)

    def save(self, config: TelegramConfig) -> None:
        if not config.bot_token.strip() or not config.chat_id.strip():
            raise SecretStoreError("bot token and chat ID are required.")

        keyring_module = _load_keyring_module()
        try:
            keyring_module.set_password(self.service_name, _KEYRING_BOT_TOKEN_ACCOUNT, config.bot_token.strip())
            keyring_module.set_password(self.service_name, _KEYRING_CHAT_ID_ACCOUNT, config.chat_id.strip())
        except Exception as exc:
            _delete_keyring_accounts(keyring_module, self.service_name)
            raise SecretStoreUnavailableError("keyring could not write to the OS credential store.") from exc

    def clear(self) -> None:
        keyring_module = _load_keyring_module()
        _delete_keyring_accounts(keyring_module, self.service_name)


class DefaultSecretStore(SecretStore):
    """Uses keyring first and DPAPI only after explicit setup confirmation."""

    def __init__(
        self,
        primary: SecretStore | None = None,
        fallback: SecretStore | None = None,
        allow_fallback: Any | None = None,
    ) -> None:
        self.primary = primary or KeyringSecretStore()
        self.fallback = fallback or DpapiSecretStore()
        self._allow_fallback = allow_fallback

    def load(self) -> TelegramConfig:
        try:
            return self.primary.load()
        except MissingConfigurationError as primary_missing:
            try:
                return self.fallback.load()
            except MissingConfigurationError:
                raise primary_missing
        except SecretStoreUnavailableError as exc:
            try:
                return self.fallback.load()
            except MissingConfigurationError:
                raise SecretStoreError(
                    f"{exc} Install the `keyring` package, restore a supported keyring backend, "
                    "or run `telealert setup` and approve the DPAPI fallback."
                ) from exc

    def save(self, config: TelegramConfig) -> None:
        try:
            self.primary.save(config)
        except SecretStoreUnavailableError as exc:
            if not self._allow_fallback or not self._allow_fallback(str(exc)):
                raise SecretStoreError(f"{exc} DPAPI fallback was not enabled; nothing was saved.") from exc
            self.fallback.save(config)
            return

        self.fallback.clear()

    def clear(self) -> None:
        try:
            self.primary.clear()
        except SecretStoreUnavailableError:
            pass
        self.fallback.clear()


class DpapiSecretStore(SecretStore):
    """Stores encrypted Telegram settings for the current Windows user."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_secret_path()

    def load(self) -> TelegramConfig:
        if not self.path.exists():
            raise MissingConfigurationError("telealert is not configured. Run `telealert setup` first.")

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if raw.get("version") != _STORE_VERSION:
                raise SecretStoreError("unsupported secret store version. Run `telealert setup` again.")
            bot_token = _dpapi_unprotect(_decode_blob(raw["bot_token"]))
            chat_id = _dpapi_unprotect(_decode_blob(raw["chat_id"]))
        except MissingConfigurationError:
            raise
        except SecretStoreError:
            raise
        except Exception as exc:
            raise SecretStoreError("stored telealert configuration is unreadable. Run `telealert setup` again.") from exc

        if not bot_token or not chat_id:
            raise MissingConfigurationError("telealert is not fully configured. Run `telealert setup` again.")

        return TelegramConfig(bot_token=bot_token, chat_id=chat_id)

    def save(self, config: TelegramConfig) -> None:
        if not config.bot_token.strip() or not config.chat_id.strip():
            raise SecretStoreError("bot token and chat ID are required.")

        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "version": _STORE_VERSION,
            "provider": "windows-dpapi-current-user",
            "bot_token": _encode_blob(_dpapi_protect(config.bot_token.strip())),
            "chat_id": _encode_blob(_dpapi_protect(config.chat_id.strip())),
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            return


def default_secret_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "telealert" / "secrets.dpapi.json"
    return Path.home() / "AppData" / "Roaming" / "telealert" / "secrets.dpapi.json"


def _load_keyring_module() -> Any:
    try:
        keyring_module = importlib.import_module("keyring")
    except ImportError as exc:
        raise SecretStoreUnavailableError("Python package `keyring` is not installed.") from exc

    backend = keyring_module.get_keyring()
    backend_name = f"{backend.__class__.__module__}.{backend.__class__.__name__}"
    lowered = backend_name.lower()
    unsafe_fragments = (
        "keyring.backends.null",
        "keyring.backends.fail",
        "keyrings.alt",
        "plaintext",
    )
    if any(fragment in lowered for fragment in unsafe_fragments):
        raise SecretStoreUnavailableError(f"keyring backend is not acceptable for telealert: {backend_name}.")

    return keyring_module


def _delete_keyring_accounts(keyring_module: Any, service_name: str) -> None:
    for account in (_KEYRING_BOT_TOKEN_ACCOUNT, _KEYRING_CHAT_ID_ACCOUNT):
        try:
            keyring_module.delete_password(service_name, account)
        except Exception:
            continue


def _encode_blob(blob: bytes) -> str:
    return base64.b64encode(blob).decode("ascii")


def _decode_blob(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _require_windows() -> None:
    if os.name != "nt":
        raise SecretStoreError("telealert's default secret store requires Windows DPAPI.")


def _make_blob(data: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_ubyte]]:
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    return _DataBlob(len(data), buffer), buffer


def _dpapi_protect(value: str) -> bytes:
    _require_windows()
    data = value.encode("utf-8")
    in_blob, in_buffer = _make_blob(data)
    entropy_blob, entropy_buffer = _make_blob(_PURPOSE)
    out_blob = _DataBlob()

    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "telealert",
        ctypes.byref(entropy_blob),
        None,
        None,
        0,
        ctypes.byref(out_blob),
    ):
        raise SecretStoreError("Windows DPAPI could not protect the telealert secrets.")

    try:
        protected = ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)

    # Keep buffers alive until the Win32 call has consumed them.
    _ = (in_buffer, entropy_buffer)
    return protected


def _dpapi_unprotect(blob: bytes) -> str:
    _require_windows()
    in_blob, in_buffer = _make_blob(blob)
    entropy_blob, entropy_buffer = _make_blob(_PURPOSE)
    out_blob = _DataBlob()
    CRYPTPROTECT_UI_FORBIDDEN = 0x1

    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        ctypes.byref(entropy_blob),
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    ):
        raise SecretStoreError("Windows DPAPI could not read the telealert secrets for this user.")

    try:
        clear = ctypes.string_at(out_blob.pbData, out_blob.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)

    _ = (in_buffer, entropy_buffer)
    return clear
