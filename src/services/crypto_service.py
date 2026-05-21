from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def _get_key() -> bytes | None:
    key = os.environ.get("SIRAN_ENCRYPT_KEY", "").strip()
    return key.encode() if key else None


def encrypt(plaintext: str) -> str:
    key = _get_key()
    if not key:
        logger.warning("SIRAN_ENCRYPT_KEY no configurada; credencial almacenada en texto plano.")
        return plaintext
    from cryptography.fernet import Fernet
    return Fernet(key).encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    key = _get_key()
    if not key:
        return ciphertext
    from cryptography.fernet import Fernet, InvalidToken
    try:
        return Fernet(key).decrypt(ciphertext.encode()).decode()
    except (InvalidToken, Exception):
        # Valor en texto plano (anterior a la migración); devolver tal cual.
        return ciphertext
