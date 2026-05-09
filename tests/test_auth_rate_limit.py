from __future__ import annotations

import importlib
from dataclasses import dataclass

import pytest
from flask import Blueprint, Flask
from flask_login import LoginManager

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
        return password == "good"


class _Query:
    def filter_by(self, **kwargs):
        self._username = kwargs.get("username")
        return self

    def first(self):
        if getattr(self, "_username", None) == "admin":
            return _User(id="1", username="admin")
        return None


class _UserModel:
    query = _Query()


@pytest.fixture()
def app(monkeypatch):
    # Forzar valores pequeños para tests.
    monkeypatch.setenv("LOGIN_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("LOGIN_LOCKOUT_SECONDS", "1")
    monkeypatch.setenv("LOGIN_WINDOW_SECONDS", "60")

    app = Flask("siran_auth_rate_limit_test", root_path=".")
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    # Stub dashboard.index para redirects.
    dash = Blueprint("dashboard", __name__)

    @dash.get("/dashboard_stub", endpoint="index")
    def index_stub():
        return "stub", 200

    app.register_blueprint(dash)

    lm = LoginManager()
    lm.login_view = "auth.login"
    lm.init_app(app)

    @lm.user_loader
    def load_user(user_id: str):
        if user_id == "1":
            return _User(id="1", username="admin")
        return None

    ar = importlib.reload(auth_routes)
    # Asegurar estado limpio entre pruebas.
    try:
        ar._login_attempts.clear()  # type: ignore[attr-defined]
    except Exception:
        pass

    ar.init_auth_routes(User=_UserModel, FLASK_CONFIG={"debug": True}, SESSION_BOOT_ID="boot-test")
    app.register_blueprint(ar.auth_bp)
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


def test_get_login_does_not_increment_attempts(client):
    r = client.get("/login")
    assert r.status_code == 200


def test_rate_limit_blocks_after_failed_attempts_then_allows_after_lockout(client, monkeypatch):
    # 1) Fallar 2 veces => lock.
    r1 = client.post("/login", data={"username": "admin", "password": "bad"}, follow_redirects=False)
    assert r1.status_code == 200
    r2 = client.post("/login", data={"username": "admin", "password": "bad"}, follow_redirects=False)
    assert r2.status_code == 200

    # 2) Intento correcto durante lock => sigue rechazando (200)
    r3 = client.post("/login", data={"username": "admin", "password": "good"}, follow_redirects=False)
    assert r3.status_code == 200
    with client.session_transaction() as sess:
        assert sess.get("_user_id") is None

    # 3) Esperar lockout (1s) y volver a intentar correcto => 302
    import time

    time.sleep(1.05)
    r4 = client.post("/login", data={"username": "admin", "password": "good"}, follow_redirects=False)
    assert r4.status_code in {302, 303}
    with client.session_transaction() as sess:
        assert sess.get("_user_id") == "1"
        assert sess.get("boot_id") == "boot-test"


def test_success_clears_attempts(client):
    # Fallar 1 vez
    r1 = client.post("/login", data={"username": "admin", "password": "bad"}, follow_redirects=False)
    assert r1.status_code == 200
    # Éxito debe limpiar intentos
    r2 = client.post("/login", data={"username": "admin", "password": "good"}, follow_redirects=False)
    assert r2.status_code in {302, 303}
    # Limpiar sesión para poder probar intentos posteriores (si no, /login redirige por current_user.is_authenticated).
    with client.session_transaction() as sess:
        sess.clear()
    # Fallar de nuevo 1 vez no debería estar bloqueado aún (max_attempts=2)
    r3 = client.post("/login", data={"username": "admin", "password": "bad"}, follow_redirects=False)
    assert r3.status_code == 200


def test_username_with_spaces_counts_as_failed_attempt(client):
    r1 = client.post("/login", data={"username": " admin", "password": "bad"}, follow_redirects=False)
    assert r1.status_code == 200
    r2 = client.post("/login", data={"username": " admin", "password": "bad"}, follow_redirects=False)
    assert r2.status_code == 200
    # Debe quedar bloqueado y rechazar incluso si password correcto (aunque username es inválido por espacios).
    r3 = client.post("/login", data={"username": " admin", "password": "good"}, follow_redirects=False)
    assert r3.status_code == 200
