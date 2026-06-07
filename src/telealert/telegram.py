from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from .errors import TelegramDeliveryError, TelegramTemporaryError
from .redaction import redact

API_BASE = "https://api.telegram.org"


@dataclass(frozen=True)
class SendOptions:
    title: str | None = None
    silent: bool = False
    parse_mode: str | None = None


class TelegramClient:
    def __init__(
        self,
        timeout_seconds: float = 10.0,
        max_retries: int = 2,
        backoff_seconds: float = 0.5,
        opener: Any | None = None,
        sleeper: Any | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self._opener = opener or urllib.request.urlopen
        self._sleep = sleeper or time.sleep

    def send_message(self, bot_token: str, chat_id: str, text: str, options: SendOptions) -> None:
        if not text.strip():
            raise TelegramDeliveryError("message must not be empty.")

        payload = {
            "chat_id": chat_id,
            "text": text,
            "disable_notification": "true" if options.silent else "false",
        }
        if options.parse_mode:
            payload["parse_mode"] = options.parse_mode

        encoded = urllib.parse.urlencode(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{API_BASE}/bot{bot_token}/sendMessage",
            data=encoded,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )

        last_error: TelegramDeliveryError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                self._send_once(request)
                return
            except TelegramTemporaryError as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                self._sleep(self.backoff_seconds * (2**attempt))
            except TelegramDeliveryError:
                raise

        raise TelegramDeliveryError(str(last_error or "temporary Telegram delivery failure."))

    def _send_once(self, request: urllib.request.Request) -> None:
        try:
            with self._opener(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="replace")
                status = getattr(response, "status", response.getcode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            self._raise_for_telegram_error(exc.code, body)
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            reason = getattr(exc, "reason", None) or exc.__class__.__name__
            raise TelegramTemporaryError(f"temporary network error while contacting Telegram: {reason}") from exc

        if status >= 500 or status == 429:
            raise TelegramTemporaryError(f"temporary Telegram API error HTTP {status}.")
        if status >= 400:
            self._raise_for_telegram_error(status, body)

        parsed = _parse_json(body)
        if parsed.get("ok") is not True:
            self._raise_for_telegram_error(status, body)

    def _raise_for_telegram_error(self, status: int, body: str) -> None:
        if status >= 500 or status == 429:
            raise TelegramTemporaryError(f"temporary Telegram API error HTTP {status}.")

        parsed = _parse_json(body)
        code = int(parsed.get("error_code") or status or 0)
        description = str(parsed.get("description") or f"HTTP {status}")
        lowered = description.lower()

        if code == 401 or "unauthorized" in lowered:
            raise TelegramDeliveryError("Telegram rejected the configured bot token. Run `telealert setup` with a valid token.")
        if code in {400, 403} and any(fragment in lowered for fragment in ["chat", "blocked", "forbidden", "not found"]):
            raise TelegramDeliveryError(
                "Telegram could not reach the configured chat ID. Check the chat ID and whether the bot has access."
            )

        raise TelegramDeliveryError(f"Telegram API error: {redact(description)}")


def _parse_json(body: str) -> dict[str, Any]:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
