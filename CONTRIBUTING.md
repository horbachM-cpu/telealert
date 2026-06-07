# Contributing

Thanks for improving `telealert`.

## Local Setup

For normal user testing of the global command, prefer the README's `pipx install` flow. For code changes, use an isolated development environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e .
```

The editable install exposes the command inside the virtual environment:

```powershell
.\.venv\Scripts\telealert.exe --help
```

## Run Tests

```powershell
.\.venv\Scripts\python -m unittest discover
```

The tests must not use real Telegram bot tokens, real chat IDs, or real network calls. Use only placeholders:

```text
TELEGRAM_BOT_TOKEN_PLACEHOLDER
TELEGRAM_CHAT_ID_PLACEHOLDER
```

## Secret Handling

Never add real credentials to source, docs, tests, screenshots, logs, or issue text.

`telealert setup` stores user-provided credentials in the local OS credential store through `keyring`. The DPAPI fallback may only be used after an explicit warning and confirmation.

## Pull Request Notes

Before opening a pull request:

1. Run the test suite.
2. Update `README.md` when behavior or setup changes.
3. Update `CHANGELOG.md` for user-facing changes.
4. Check that no generated files, local config, or secret files are included.
