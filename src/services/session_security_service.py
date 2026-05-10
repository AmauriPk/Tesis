from __future__ import annotations

import os
import secrets
import time
from typing import Any


class SessionSecurityService:
    """
    Seguridad de sesión (boot-id + expiración por inactividad).

    - boot_id: invalida cookies/sesiones previas tras reinicio del servidor.
    - idle timeout: invalida sesiones tras N segundos sin actividad.

    Este servicio NO depende de Flask; opera con dict-like `session`.
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
        return bool(session_boot_id) and (str(session_boot_id) != str(self.boot_id))

    def is_idle_expired(self, last_seen_at: Any, *, now: float | None = None) -> bool:
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
        try:
            session_obj["last_seen_at"] = float(time.time() if now is None else now)
        except Exception:
            pass

