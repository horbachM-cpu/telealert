# Changelog

All notable user-facing changes will be documented in this file.

## 0.1.0 - Unreleased

- Add Windows-first `telealert` CLI.
- Add `telealert setup`, `telealert status`, and `telealert clear`.
- Store Telegram credentials in the OS credential store through `keyring`.
- Add explicit DPAPI fallback confirmation when `keyring` is unavailable.
- Add Telegram `sendMessage` delivery with timeout handling and retries.
- Add safe error redaction for configured secret values.
- Add README, security policy, MIT license, contribution guide, and CI workflow.
