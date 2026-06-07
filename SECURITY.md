# Security Policy

## Secret Handling

Never commit a real Telegram bot token or chat ID.

Use only placeholder values in examples:

```text
TELEGRAM_BOT_TOKEN_PLACEHOLDER
TELEGRAM_CHAT_ID_PLACEHOLDER
```

`telealert setup` stores local values in the OS credential store through Python `keyring`. On Windows, this means Windows Credential Manager / Credential Locker.

If `keyring` is missing or no acceptable backend is available, setup warns and asks before using the DPAPI fallback file. Declining the fallback saves nothing.

## Reporting a Security Issue

Do not include real bot tokens, chat IDs, screenshots containing secrets, or command output containing secrets in a public issue.

If you believe a token leaked, rotate it immediately with BotFather before investigating further.

## Token Rotation

With BotFather, revoke or rotate the affected token, then run:

```cmd
telealert setup
```

Enter the new token and the chat ID when prompted.

## Local Threat Model

The OS credential store helps prevent accidental disclosure through Git, logs, examples, shell history, and plaintext files. The DPAPI fallback has the same accidental-disclosure goal, but it is only used after explicit confirmation.

It does not protect against malware, a compromised Windows user account, memory inspection, malicious shell profiles, or tools already running with your user privileges.
