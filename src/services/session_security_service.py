"""
Módulo      : session_security_service.py
Rol         : Seguridad de sesión Flask — dos mecanismos independientes:
              (1) boot_id: invalida todas las sesiones activas tras reiniciar
              el servidor, forzando re-login de todos los operadores.
              (2) idle timeout: cierra sesiones inactivas por más de N segundos.
Conectado con: config.py (SESSION_IDLE_TIMEOUT_SECONDS vía os.environ),
              app.py (_volatile_sessions before_request hook).
Usado por   : app.py (instancia y usa los métodos en before_request).
Hilos       : Sin estado mutable compartido — el boot_id es inmutable tras __init__.
Base de datos: No accede a ninguna DB.
"""
from __future__ import annotations

import os
import secrets
import time
from typing import Any


class SessionSecurityService:
    """
    Seguridad de sesión Flask con boot-id e idle timeout.

    Responsabilidad: detectar sesiones de arranques anteriores (invalidarlas)
                     y sesiones inactivas más allá del timeout configurado.
    Ciclo de vida  : instanciado una vez en app.py; ``boot_id`` es inmutable.
    Atributos clave: ``boot_id`` — hex aleatorio único por arranque del proceso;
                     no se persiste en disco (intencionalmente volátil).

    Este servicio NO importa Flask — opera con cualquier dict-like como session.
    """

    def __init__(self, *, boot_id: str | None = None):
        self.boot_id = str(boot_id or secrets.token_hex(16))

    @staticmethod
    def get_idle_timeout_seconds() -> int:
        try:
            raw = (os.environ.get("SESSION_IDLE_TIMEOUT_SECONDS") or "900").strip()
            v = int(raw)
        except Exception:
            v = 900
        return max(60, min(86400, int(v)))

    def is_session_from_old_boot(self, session_boot_id: Any) -> bool:
        """
        Detecta si una sesión pertenece a un arranque anterior del servidor.

        Args:
            session_boot_id: Valor de ``session["boot_id"]`` leído de la cookie.

        Returns:
            True si el boot_id de la sesión difiere del actual — indica que el
            servidor fue reiniciado y la sesión debe invalidarse.
        """
        return bool(session_boot_id) and (str(session_boot_id) != str(self.boot_id))

    def is_idle_expired(self, last_seen_at: Any, *, now: float | None = None) -> bool:
        """
        Comprueba si la sesión ha superado el idle timeout.

        Args:
            last_seen_at: Timestamp epoch (float) del último request del usuario.
            now: Timestamp actual (None → time.time()); inyectable en tests.

        Returns:
            True si la sesión lleva más de ``SESSION_IDLE_TIMEOUT_SECONDS`` sin actividad.
            False si ``last_seen_at`` es None (sesión nueva sin timestamp aún).
        """
        if last_seen_at is None:
            return False
        timeout_s = float(self.get_idle_timeout_seconds())
        now_ts = float(time.time() if now is None else now)
        try:
            age_s = now_ts - float(last_seen_at)
        except Exception:
            return True
        return float(age_s) > float(timeout_s)

    def mark_seen(self, session_obj: Any, *, now: float | None = None) -> None:
        """
        Actualiza ``session["last_seen_at"]`` con el timestamp actual.

        Llamado en cada request autenticado para reiniciar el contador de inactividad.

        Args:
            session_obj: Objeto de sesión Flask (dict-like mutable).
            now: Timestamp epoch (None → time.time()); inyectable en tests.
        """
        try:
            session_obj["last_seen_at"] = float(time.time() if now is None else now)
        except Exception:
            pass

