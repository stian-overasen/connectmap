"""Keychain-backed Garmin session token storage helpers."""

import keyring
from keyring.errors import KeyringError

KEYCHAIN_SERVICE = "connectmap"
KEYCHAIN_ACCOUNT = "garmin_session"


class GarminSessionStorageError(Exception):
    """Base exception for Garmin session storage failures."""


class MissingGarminSessionError(GarminSessionStorageError):
    """Raised when no Garmin session token exists in keychain."""


def load_garmin_session_token():
    """Load the Garmin session token from the OS keychain."""
    try:
        token = keyring.get_password(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT)
    except KeyringError as exc:
        raise GarminSessionStorageError(f"Unable to access OS keychain: {exc}") from exc

    if not token:
        raise MissingGarminSessionError("No Garmin session token found in OS keychain.")

    return token


def save_garmin_session_token(session_token):
    """Save the Garmin session token to the OS keychain."""
    if not session_token:
        raise GarminSessionStorageError("Refusing to store empty Garmin session token.")

    try:
        keyring.set_password(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT, session_token)
    except KeyringError as exc:
        raise GarminSessionStorageError(f"Unable to write Garmin session token to OS keychain: {exc}") from exc
