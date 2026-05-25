"""Servicios de arranque — logging, clave secreta y usuarios por defecto."""
from __future__ import annotations

import logging
import logging.handlers
import os
import secrets


def setup_logging() -> None:
    """Configura logging con handlers de consola y archivo rotatorio.

    Lee LOG_DIR directamente de os.environ porque se invoca antes de que
    APP_CONFIG (config.py) esté disponible en el proceso de arranque.
    """
    log_dir = os.environ.get("LOG_DIR", "logs")
    os.makedirs(log_dir, exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    fh = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "siran.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(ch)
    root.addHandler(fh)


def load_or_create_secret_key(key_file: str) -> str:
    """Carga o genera la Flask SECRET_KEY y la persiste en `key_file`."""
    _log = logging.getLogger(__name__)
    if os.path.exists(key_file):
        with open(key_file, "r") as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    os.makedirs(os.path.dirname(os.path.abspath(key_file)), exist_ok=True)
    with open(key_file, "w") as f:
        f.write(key)
    _log.info("FLASK_SECRET_KEY generada y guardada en %s", key_file)
    return key


def bootstrap_users() -> None:
    """Crea usuarios por defecto en primera ejecución (solo si la tabla está vacía)."""
    from src.system_core import User, db  # import tardío — evita circular en arranque

    _log = logging.getLogger(__name__)
    if User.query.count() > 0:
        return

    admin = User(username="admin", role="admin")
    admin_pw_env = (os.environ.get("DEFAULT_ADMIN_PASSWORD") or "").strip()
    admin_pw = admin_pw_env or "admin123"
    if not admin_pw_env or admin_pw == "admin123":
        _log.warning(
            "Usando password por defecto para admin. Configura DEFAULT_ADMIN_PASSWORD. "
            "password_configurada=%s password_len=%s",
            bool(admin_pw_env),
            len(admin_pw),
        )
    admin.set_password(admin_pw)

    operator = User(username="operador", role="operator")
    operator_pw_env = (os.environ.get("DEFAULT_OPERATOR_PASSWORD") or "").strip()
    operator_pw = operator_pw_env or "operador123"
    if not operator_pw_env or operator_pw == "operador123":
        _log.warning(
            "Usando password por defecto para operador. Configura DEFAULT_OPERATOR_PASSWORD. "
            "password_configurada=%s password_len=%s",
            bool(operator_pw_env),
            len(operator_pw),
        )
    operator.set_password(operator_pw)

    db.session.add(admin)
    db.session.add(operator)
    db.session.commit()

    _log.info("Usuarios creados: admin (role=admin), operador (role=operator)")
