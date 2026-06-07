# telealert

`telealert` is a Windows-first CLI that sends Telegram alerts from any shell using credentials stored in the OS credential store.

```cmd
telealert Aufgabe wurde erledigt
telealert --title "Build" "Tests bestanden"
telealert --silent "Nightly job fertig"
telealert --markdown "**Build fertig**"
```

No Telegram bot token or chat ID belongs in this repository. Setup stores them locally for your Windows user in the OS credential store.

## Technical Decision

This project uses Python plus the widely used `keyring` package. On Windows, `keyring` stores secrets in the Windows Credential Manager / Credential Locker. That is a better default than a project-owned file because users can inspect and remove the credentials with normal Windows tooling.

If `keyring` is missing or no acceptable backend is available, `telealert setup` prints a warning and asks whether you explicitly want to use the fallback store. The fallback is a DPAPI-encrypted local file:

```text
%APPDATA%\telealert\secrets.dpapi.json
```

The fallback file contains DPAPI-encrypted blobs, not plaintext secrets. It can only be decrypted by the same Windows user profile. The fallback is not used silently during setup.

## Install on Windows

Recommended one-time install for normal use:

```powershell
python -m pip install --user pipx
python -m pipx ensurepath
```

Close and reopen PowerShell or CMD after `ensurepath`, then install `telealert` from the repository:

```powershell
pipx install C:\Users\Marcel\Documents\telealert
```

After that, `telealert` should work from any directory:

```powershell
telealert --help
telealert status
```

On this machine the installed command lives at:

```text
C:\Users\Marcel\.local\bin\telealert.exe
```

If a terminal was already open before installation, open a new terminal before testing `telealert`.

To upgrade after pulling new repository changes:

```powershell
pipx reinstall telealert
```

To remove it:

```powershell
pipx uninstall telealert
```

Alternative without `pipx`:

```powershell
python -m pip install --user C:\Users\Marcel\Documents\telealert
```

If PowerShell cannot find `telealert` after a `--user` install, add Python's user Scripts directory to `PATH`. `pipx ensurepath` handles this automatically for the recommended install.

## Configure Telegram

After installing, configure your local Telegram settings:

```cmd
telealert setup
```

`telealert setup` prompts for:

- Telegram Bot Token
- Telegram Chat ID

The bot token and chat ID prompts are hidden where the terminal supports it. The values are never passed as command-line arguments and are never written into project files.

If `keyring` is not available, setup asks before using the DPAPI fallback:

```text
Warning: Python package `keyring` is not installed.
Use DPAPI fallback anyway? [y/N]:
```

Answering `N` or pressing Enter saves nothing.

## Development Install

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e .
```

If your Windows installation has the Python Launcher, `py -m venv .venv` works too. If `py` is not found, use `python -m venv .venv`.

You can also run the package without installing the console script:

```powershell
.\.venv\Scripts\python -m telealert status
```

## Usage

```cmd
telealert Aufgabe wurde erledigt
telealert Build erfolgreich
telealert Tests fertig
```

Options:

```cmd
telealert --title "Build" "Tests bestanden"
telealert --silent "Nightly job fertig"
telealert --markdown "**Build fertig**"
```

Management commands:

```cmd
telealert setup
telealert status
telealert clear
```

`telealert status` reports whether a bot token and chat ID are configured, but never prints their values.

`telealert clear` deletes the configured secrets from the OS credential store and also removes the DPAPI fallback file if one exists.

## Exit Codes

- `0`: message sent successfully
- `1`: missing or unreadable local configuration
- `2`: network or Telegram API failure
- `3`: invalid usage

## Markdown

`--markdown` accepts a small safe Markdown subset and converts it to Telegram HTML before sending:

- `**bold**`
- `*italic*`
- `` `code` ``
- `[label](https://example.com)`

This is intentionally not a full Markdown or MarkdownV2 parser. Unsupported syntax is escaped and sent as text. This avoids common Telegram MarkdownV2 escaping mistakes.

## Security Notes

Treat the Telegram bot token like a password. Anyone with the token can control that bot through Telegram's Bot API.

If a token leaks, rotate it with BotFather immediately:

```text
/revoke
```

The chat ID is less critical than the bot token, but it should still not be published unnecessarily.

The local OS credential store protects against accidental disclosure through Git commits, logs, shell history, and project files. The optional DPAPI fallback provides the same accidental-disclosure protection, but it is less convenient to inspect than Windows Credential Manager. Neither mode protects against malware, a compromised Windows account, malicious debugging tools, or a process already running as your user.

## Threat Model

This tool protects against:

- accidentally committing a bot token or chat ID to Git
- exposing secrets through CLI arguments or shell history
- printing secrets in normal status, setup, or error output
- storing plaintext secrets in the repository
- silently falling back to a project-owned secret file during setup

This tool does not protect against:

- malware running as the same Windows user
- a compromised Telegram account or bot
- someone with full access to your Windows profile
- Telegram-side outages or Bot API policy changes

If a token leak happens:

1. Revoke or rotate the bot token with BotFather.
2. Run `telealert setup` and enter the new token.
3. Review recent bot activity and repository history.

## Development

Run tests with:

```powershell
python -m unittest discover
```

The tests use fake stores and fake Telegram clients. They do not contain real secrets and do not call Telegram.

## License

MIT. See [LICENSE](LICENSE).
