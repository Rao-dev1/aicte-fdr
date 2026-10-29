"""Encryption for the FDR number and bank name stored in the database.

- Values are encrypted with Fernet (AES-128-CBC + HMAC) using FIELD_ENCRYPTION_KEY.
- A keyed hash ("blind index") of each value is stored next to it, so the app can still
  check for duplicates and look things up exactly. The hash cannot be reversed without the key.
- The key lives only in the environment (Render settings or your local .env). It is never stored in the database or code.

Generate a key once with:  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import hashlib
import hmac
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator


@lru_cache(maxsize=1)
def _key_bytes() -> bytes:
    raw = os.getenv("FIELD_ENCRYPTION_KEY", "").strip()
    if not raw:
        raise RuntimeError("FIELD_ENCRYPTION_KEY is not set. Generate one and add it to the environment.")
    try:
        Fernet(raw.encode())
    except (ValueError, TypeError) as exc:
        raise RuntimeError("FIELD_ENCRYPTION_KEY is not a valid Fernet key") from exc
    return raw.encode()


def require_key() -> None:
    """Called at start-up so a missing key stops the app before it stores anything unencrypted."""
    _key_bytes()


def _fernet() -> Fernet:
    return Fernet(_key_bytes())


def encrypt_text(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_text(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("A stored value could not be decrypted. Check FIELD_ENCRYPTION_KEY.") from exc


def _blind_key() -> bytes:
    return hashlib.sha256(b"blind-index-v1:" + _key_bytes()).digest()


def _blind(normalized: str) -> str:
    return hmac.new(_blind_key(), normalized.encode("utf-8"), hashlib.sha256).hexdigest()


def fdr_number_hash(value: str) -> str:
    """FDR numbers match regardless of case and surrounding spaces."""
    return _blind("ref:" + value.strip().lower())


def bank_hash(value: str) -> str:
    return _blind("bank:" + " ".join(value.lower().split()))


class EncryptedText(TypeDecorator):
    """A text column that is encrypted when written and decrypted when read."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else encrypt_text(value)

    def process_result_value(self, value, dialect):
        return None if value is None else decrypt_text(value)
