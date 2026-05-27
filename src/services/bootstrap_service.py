"""
Módulo      : bootstrap_service.py
Rol         : Inicialización del sistema en el arranque: configura logging,
              genera/carga la Flask SECRET_KEY y crea usuarios por defecto.
              Se invoca ANTES de que Flask y config.py estén disponibles.
Conectado con: src/system_core.py (User, db — importación tardía para evitar
              circularidad), logging.handlers (RotatingFileHandler), secrets.
Usado por   : app.py (las tres funciones se llaman al inicio del módulo).
Hilos       : Ninguno — ejecución síncrona en el proceso principal de arranque.
Base de datos: app.db (SQLAlchemy vía User.query) — solo en bootstrap_users().
"""
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
    """
    Carga la Flask SECRET_KEY desde disco o genera una nueva si no existe.

    Persiste la clave en `key_file` para que sobreviva reinicios del servidor
    y no invalide las cookies de sesión activas de los operadores.

    Args:
        key_file: Ruta del archivo donde se persiste la clave hex (p.ej.
                  ``instance/.secret_key``).

    Returns:
        Cadena hex de 64 caracteres (32 bytes) usable como ``app.secret_key``.
    """
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
    """
    Crea usuarios ``admin`` y ``operador`` si la tabla User está vacía (primera ejecución).

    Lee DEFAULT_ADMIN_PASSWORD y DEFAULT_OPERATOR_PASSWORD del entorno; si no están
    configuradas usa passwords débiles por defecto y emite WARNING — la intención es
    que el operador los cambie antes de poner el sistema en producción.
    """
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
