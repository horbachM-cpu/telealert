from __future__ import annotations


class TelealertError(Exception):
    """Base class for expected CLI errors."""

    exit_code = 2


class InvalidUsageError(TelealertError):
    exit_code = 3


class MissingConfigurationError(TelealertError):
    exit_code = 1


class SecretStoreError(TelealertError):
    exit_code = 1


class SecretStoreUnavailableError(SecretStoreError):
    pass


class TelegramDeliveryError(TelealertError):
    exit_code = 2


class TelegramTemporaryError(TelegramDeliveryError):
    pass
