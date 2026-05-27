"""
Módulo      : crypto_service.py
Rol         : Cifrado y descifrado simétrico de credenciales (Fernet/AES-128-CBC).
              Abstrae el uso de `cryptography.fernet` para que el resto de la app
              no gestione claves directamente.
Conectado con: Variable de entorno SIRAN_ENCRYPT_KEY (clave Fernet en base64-url).
Usado por   : src/system_core.py (_EncryptedString), CameraConfig (onvif_password,
              rtsp_password).
Hilos       : Sin estado propio — invocable desde cualquier hilo de forma segura.
Base de datos: No accede a DB; cifra/descifra antes de persistir en SQLAlchemy.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def _get_key() -> bytes | None:
    """
    Lee SIRAN_ENCRYPT_KEY del entorno y la convierte a bytes para Fernet.

    Returns:
        bytes con la clave Fernet si la variable está configurada y no vacía,
        None si la variable está ausente o es cadena vacía.
    """
    key = os.environ.get("SIRAN_ENCRYPT_KEY", "").strip()
    return key.encode() if key else None


def encrypt(plaintext: str) -> str:
    """
    Cifra una cadena con Fernet (AES-128-CBC + HMAC-SHA256).

    Si SIRAN_ENCRYPT_KEY no está configurada la función devuelve el texto plano
    con un warning — esto permite arrancar el sistema en entornos de desarrollo
    sin clave configurada, sin romper la aplicación (degraded mode).

    Args:
        plaintext: Texto a cifrar, p.ej. contraseña ONVIF o RTSP.

    Returns:
        Token Fernet en base64-url (str) si hay clave, o plaintext si no la hay.
    """
    key = _get_key()
    if not key:
        # Sin clave no se puede cifrar; se persiste en claro con advertencia.
        logger.warning("SIRAN_ENCRYPT_KEY no configurada; credencial almacenada en texto plano.")
        return plaintext
    from cryptography.fernet import Fernet
    return Fernet(key).encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """
    Descifra un token Fernet y devuelve el texto plano.

    Maneja de forma transparente credenciales legadas en texto plano
    (almacenadas antes de que se implementara el cifrado): si Fernet lanza
    InvalidToken, devuelve el ciphertext tal cual — compatibilidad hacia atrás
    sin excepción al operador.

    Args:
        ciphertext: Token Fernet (base64-url) o texto plano legado.

    Returns:
        Texto descifrado, o el valor original si no hay clave o el token es inválido.
    """
    key = _get_key()
    if not key:
        return ciphertext
    from cryptography.fernet import Fernet, InvalidToken
    try:
        return Fernet(key).decrypt(ciphertext.encode()).decode()
    except (InvalidToken, Exception):
        # Valor en texto plano (anterior a la migración); devolver tal cual.
        return ciphertext
