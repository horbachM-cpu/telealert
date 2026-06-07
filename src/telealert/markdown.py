from __future__ import annotations

import html
import re

_TOKEN_RE = re.compile(
    r"(`[^`\n]+`)|(\*\*[^*\n]+\*\*)|(\*[^*\n]+\*)|(\[[^\]\n]+\]\(https?://[^)\s]+?\))"
)
_LINK_RE = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+?)\)")


def markdown_to_telegram_html(text: str) -> str:
    """Convert a deliberately small Markdown subset to Telegram HTML."""

    parts: list[str] = []
    position = 0
    for match in _TOKEN_RE.finditer(text):
        parts.append(html.escape(text[position : match.start()]))
        token = match.group(0)
        parts.append(_convert_token(token))
        position = match.end()

    parts.append(html.escape(text[position:]))
    return "".join(parts)


def plain_to_telegram_html(text: str) -> str:
    return html.escape(text)


def _convert_token(token: str) -> str:
    if token.startswith("`") and token.endswith("`"):
        return f"<code>{html.escape(token[1:-1])}</code>"
    if token.startswith("**") and token.endswith("**"):
        return f"<b>{html.escape(token[2:-2])}</b>"
    if token.startswith("*") and token.endswith("*"):
        return f"<i>{html.escape(token[1:-1])}</i>"

    link = _LINK_RE.fullmatch(token)
    if link:
        label, url = link.groups()
        return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'

    return html.escape(token)
