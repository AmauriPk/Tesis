from __future__ import annotations

from dataclasses import dataclass

import pytest
from flask import Flask, flash, redirect, request, session, url_for
from flask_login import LoginManager, login_required, logout_user

import importlib
import src.routes.auth as auth_routes


@dataclass
class _User:
    id: str
    username: str
    role: str = "operator"

    is_authenticated: bool = True
    is_active: bool = True
    is_anonymous: bool = False

    def get_id(self):
        return str(self.id)

    def check_password(self, password: str) -> bool:
        return password == "p"


class _Query:
    def filter_by(self, **kwargs):
        self._username = kwargs.get("username")
        return self

    def first(self):
        if getattr(self, "_username", None) == "u":
            return _User(id="1", username="u")
        return None


class _UserModel:
    query = _Query()


@pytest.fixture()
def app():
    app = Flask("siran_session_test", root_path=".")
    app.config.update(TESTING=True, SECRET_KEY="test-secret")
    app.config["SESSION_BOOT_ID"] = "boot-A"

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id: str):
        if user_id == "1":
            return _User(id="1", username="u")
        return None

    @app.before_request
    def _boot_id_guard():
        endpoint = (request.endpoint or "").strip()
        if endpoint in {"auth.login", "auth.logout", "static"}:
            return None
        # La cookie de Flask-Login puede sobrevivir al reinicio; invalidarla por boot id.
        if session.get("_user_id") and (session.get("boot_id") != app.config.get("SESSION_BOOT_ID")):
            try:
                logout_user()
            except Exception:
                pass
            session.clear()
            flash("La sesión anterior fue cerrada porque el sistema se reinició.", "warning")
            return redirect(url_for("auth.login"))
        return None

    # Stub mínimo para que `auth.login` pueda redirigir a `dashboard.index`.
    from flask import Blueprint

    dashboard_bp = Blueprint("dashboard", __name__)

    @dashboard_bp.get("/dashboard_stub", endpoint="index")
    def dashboard_index_stub():
        return "stub", 200

    app.register_blueprint(dashboard_bp)

    @app.get("/protected")
    @login_required
    def protected():
        return "ok", 200

    # Aislar de otras suites: `auth.login` captura deps por closure en init_auth_routes().
    # Recargar módulo asegura un Blueprint limpio para este test.
    ar = importlib.reload(auth_routes)
    ar.init_auth_routes(User=_UserModel, FLASK_CONFIG={"debug": True}, SESSION_BOOT_ID=app.config["SESSION_BOOT_ID"])
    app.register_blueprint(ar.auth_bp)
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


def test_login_sets_boot_id(client):
    r = client.post("/login", data={"username": "u", "password": "p"}, follow_redirects=False)
    # login exitoso => redirect al dashboard (no existe en este app), así que puede ser 302 a "/?tab=live"
    assert r.status_code in {302, 303}
    with client.session_transaction() as sess:
        assert sess.get("boot_id") == "boot-A"
        assert sess.get("_user_id") == "1"


def test_boot_id_mismatch_logs_out_and_redirects(client, app):
    # Login OK
    client.post("/login", data={"username": "u", "password": "p"}, follow_redirects=False)

    # Simular reinicio del servidor (boot id distinto)
    app.config["SESSION_BOOT_ID"] = "boot-B"

    r = client.get("/protected", follow_redirects=False)
    assert r.status_code in {302, 303}
    assert "/login" in (r.headers.get("Location") or "")

    with client.session_transaction() as sess:
        assert sess.get("_user_id") is None
        assert sess.get("boot_id") is None


def test_login_route_does_not_loop_on_mismatch(client, app):
    # Forzar una sesión "vieja"
    with client.session_transaction() as sess:
        sess["_user_id"] = "1"
        sess["boot_id"] = "old"
    app.config["SESSION_BOOT_ID"] = "new"

    r = client.get("/login", follow_redirects=False)
    # No debe entrar en loop ni romper por BuildError; 200 (form) o 302 (ya autenticado) son válidos.
    assert r.status_code in {200, 302, 303}
