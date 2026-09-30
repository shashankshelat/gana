"""Encryption at rest for secret settings (AI provider keys, alert webhooks).

Values are Fernet tokens prefixed with "enc:v1:", keyed from SECRET_KEY. Plain values without
the prefix (written before encryption existed) are still readable and get encrypted at startup.
Changing SECRET_KEY makes saved secrets unreadable: they must be entered again."""
import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = logging.getLogger(__name__)

PREFIX = "enc:v1:"


def _fernet() -> Fernet:
    digest = hashlib.sha256(f"gana-settings:{settings.secret_key}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def is_encrypted(value: str | None) -> bool:
    return bool(value) and value.startswith(PREFIX)


def encrypt(value: str) -> str:
    if not value or is_encrypted(value):
        return value
    return PREFIX + _fernet().encrypt(value.encode()).decode()


def decrypt(value: str | None) -> str:
    if not is_encrypted(value):
        return value or ""
    try:
        return _fernet().decrypt(value[len(PREFIX):].encode()).decode()
    except InvalidToken:
        logger.error("A saved secret could not be decrypted (was SECRET_KEY changed?); re-enter it in Settings")
        return ""
