from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

auth_bp = Blueprint("auth", __name__)

_deps: dict[str, Any] = {}
_routes_initialized = False


def _get_dep(key: str):
    try:
        return _deps[key]
    except KeyError as exc:
        raise RuntimeError(f"Dependencia faltante en auth: {key}") from exc


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
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password") or ""
            user = User.query.filter_by(username=username).first()
            if user and user.check_password(password):
                login_user(user)
                session.permanent = False
                # Invalida sesiones previas al reiniciar servidor.
                session["boot_id"] = str(SESSION_BOOT_ID)
                next_url = (request.form.get("next") or request.args.get("next") or "").strip()
                if next_url:
                    parsed = urlparse(next_url)
                    is_safe = (parsed.scheme == "") and (parsed.netloc == "")
                    if is_safe and next_url not in {"/", "/?tab=live"}:
                        return redirect(next_url)
                return redirect(url_for("dashboard.index", tab="live"))
            flash("Credenciales inválidas.", "danger")

        return render_template("login.html", show_bootstrap_hint=bool(FLASK_CONFIG.get("debug")))

    @auth_bp.route("/logout")
    @login_required
    def logout():
        """Cierra sesión."""
        logout_user()
        return redirect(url_for("auth.login"))
