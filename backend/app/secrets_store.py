"""Encryption for stored credentials (SSH keys, passwords).

Secrets are encrypted with Fernet (AES + HMAC) using MASTER_KEY before they reach the database, and
are only decrypted inside the worker at the moment it connects to a server. In production MASTER_KEY
comes from Azure Key Vault.
"""
from cryptography.fernet import Fernet, InvalidToken

from . import config


def _fernet() -> Fernet:
    return Fernet(config.MASTER_KEY.encode())


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        raise RuntimeError("Can't decrypt a stored credential: MASTER_KEY has changed since it was saved.")
