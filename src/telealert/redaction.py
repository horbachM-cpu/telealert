from __future__ import annotations

REDACTION = "[redacted]"


def redact(text: object, secrets: list[str] | tuple[str, ...] = ()) -> str:
    """Remove known secret values from text before it is printed."""

    safe = str(text)
    for secret in secrets:
        if secret:
            safe = safe.replace(secret, REDACTION)
    return safe
