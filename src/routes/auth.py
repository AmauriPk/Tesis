from __future__ import annotations

import os
import threading
import time
from typing import Any
from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

auth_bp = Blueprint("auth", __name__)

_deps: dict[str, Any] = {}
_routes_initialized = False

# Rate limit básico in-memory (no persistente) para evitar fuerza bruta local.
_login_attempts: dict[str, dict[str, Any]] = {}
_login_attempts_lock = threading.Lock()


def _get_dep(key: str):
    try:
        return _deps[key]
    except KeyError as exc:
        raise RuntimeError(f"Dependencia faltante en auth: {key}") from exc


def _client_ip() -> str:
    xff = (request.headers.get("X-Forwarded-For") or "").strip()
    if xff:
        return xff.split(",")[0].strip() or "unknown"
    return (request.remote_addr or "unknown").strip() or "unknown"


def _attempt_key(username: str) -> str:
    u = (username or "").strip().lower() or "__empty__"
    return f"{_client_ip()}:{u}"


def _prune_attempts(now: float, *, window_s: int) -> None:
    # Limpia intentos viejos para evitar crecimiento indefinido.
    cutoff = float(now) - float(window_s)
    keys_to_delete: list[str] = []
    for k, rec in list(_login_attempts.items()):
        ts = [t for t in (rec.get("attempts") or []) if float(t) >= cutoff]
        rec["attempts"] = ts
        locked_until = float(rec.get("locked_until") or 0.0)
        if (not ts) and (locked_until <= float(now)):
            keys_to_delete.append(k)
    for k in keys_to_delete:
        try:
            _login_attempts.pop(k, None)
        except Exception:
            pass


def _is_locked(key: str, now: float, *, window_s: int) -> bool:
    with _login_attempts_lock:
        _prune_attempts(now, window_s=window_s)
        rec = _login_attempts.get(key) or {}
        locked_until = float(rec.get("locked_until") or 0.0)
        return float(now) < locked_until


def _record_failed_attempt(
    key: str,
    now: float,
    *,
    max_attempts: int,
    window_s: int,
    lockout_s: int,
) -> None:
    with _login_attempts_lock:
        _prune_attempts(now, window_s=window_s)
        rec = _login_attempts.get(key)
        if rec is None:
            rec = {"attempts": [], "locked_until": 0.0}
            _login_attempts[key] = rec
        attempts = list(rec.get("attempts") or [])
        attempts.append(float(now))
        rec["attempts"] = attempts
        if len(attempts) >= int(max_attempts):
            rec["locked_until"] = float(now) + float(lockout_s)


def _clear_attempts(key: str) -> None:
    with _login_attempts_lock:
        _login_attempts.pop(key, None)


def init_auth_routes(**deps: Any) -> None:
    """
    Inicializa dependencias y registra rutas de autenticación en el Blueprint.

    Evita imports circulares con `app.py` al recibir referencias explícitas.
    """
    global _deps, _routes_initialized
    _deps = dict(deps or {})

    if _routes_initialized:
        return
    _routes_initialized = True

    User = _get_dep("User")
    FLASK_CONFIG = _get_dep("FLASK_CONFIG")
    SESSION_BOOT_ID = _get_dep("SESSION_BOOT_ID")

    @auth_bp.route("/login", methods=["GET", "POST"])
    def login():
        """Login simple (Flask-Login)."""
        if current_user.is_authenticated:
            return redirect(url_for("dashboard.index"))

        if request.method == "POST":
            now = time.time()
            # Config por env (dinámico; no requiere reiniciar tests).
            try:
                max_attempts = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "5").strip() or "5")
            except Exception:
                max_attempts = 5
            try:
                lockout_s = int(os.environ.get("LOGIN_LOCKOUT_SECONDS", "60").strip() or "60")
            except Exception:
                lockout_s = 60
            try:
                window_s = int(os.environ.get("LOGIN_WINDOW_SECONDS", "300").strip() or "300")
            except Exception:
                window_s = 300
            max_attempts = max(1, min(50, int(max_attempts)))
            lockout_s = max(1, min(3600, int(lockout_s)))
            window_s = max(5, min(3600, int(window_s)))

            raw_username = request.form.get("username") or ""
            username = raw_username.strip()
            password = request.form.get("password") or ""
            key = _attempt_key(username)

            # Bloqueo por intentos repetidos (solo POST).
            if _is_locked(key, now, window_s=window_s):
                flash("Demasiados intentos. Intente nuevamente más tarde.", "danger")
                return render_template("login.html", show_bootstrap_hint=bool(FLASK_CONFIG.get("debug")))

            # Seguridad: no corregir silenciosamente whitespace en username.
            if (raw_username != username) or (not username):
                _record_failed_attempt(key, now, max_attempts=max_attempts, window_s=window_s, lockout_s=lockout_s)
                flash("Credenciales inválidas.", "danger")
                return render_template("login.html", show_bootstrap_hint=bool(FLASK_CONFIG.get("debug")))
            user = User.query.filter_by(username=username).first()
            if user and user.check_password(password):
                _clear_attempts(key)
                login_user(user)
                session.permanent = False
                # Invalida sesiones previas al reiniciar servidor.
                session["boot_id"] = str(SESSION_BOOT_ID)
                # Expiración por inactividad.
                session["last_seen_at"] = float(time.time())
                next_url = (request.form.get("next") or request.args.get("next") or "").strip()
                if next_url:
                    parsed = urlparse(next_url)
                    is_safe = (parsed.scheme == "") and (parsed.netloc == "")
                    if is_safe and next_url not in {"/", "/?tab=live"}:
                        return redirect(next_url)
                return redirect(url_for("dashboard.index", tab="live"))
            # Credenciales inválidas (incluye usuario inexistente).
            _record_failed_attempt(key, now, max_attempts=max_attempts, window_s=window_s, lockout_s=lockout_s)
            flash("Credenciales inválidas.", "danger")

        return render_template("login.html", show_bootstrap_hint=bool(FLASK_CONFIG.get("debug")))

    @auth_bp.route("/logout")
    @login_required
    def logout():
        """Cierra sesión."""
        logout_user()
        return redirect(url_for("auth.login"))
