from __future__ import annotations

import importlib
from dataclasses import dataclass

import pytest
from flask import Flask
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
        # Importante: no aplicar strip al password; validar exacto.
        return password == "p"


class _Query:
    def filter_by(self, **kwargs):
        self._username = kwargs.get("username")
        return self

    def first(self):
        if getattr(self, "_username", None) == "admin":
            return _User(id="1", username="admin")
        if getattr(self, "_username", None) == "operador":
            return _User(id="2", username="operador")
        return None


class _UserModel:
    query = _Query()


@pytest.fixture()
def app():
    app = Flask("siran_auth_validation_test", root_path=".")
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id: str):
        if user_id == "1":
            return _User(id="1", username="admin")
        if user_id == "2":
            return _User(id="2", username="operador")
        return None

    # Stub mínimo para que `auth.login` pueda redirigir a `dashboard.index`.
    from flask import Blueprint

    dashboard_bp = Blueprint("dashboard", __name__)

    @dashboard_bp.get("/dashboard_stub", endpoint="index")
    def dashboard_index_stub():
        return "stub", 200

    app.register_blueprint(dashboard_bp)

    ar = importlib.reload(auth_routes)
    ar.init_auth_routes(User=_UserModel, FLASK_CONFIG={"debug": True}, SESSION_BOOT_ID="boot-test")
    app.register_blueprint(ar.auth_bp)
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.mark.parametrize(
    "username",
    [
        " admin",
        "admin ",
        "   admin   ",
        "\tadmin",
        "admin\t",
        "",
        "   ",
        "\t",
    ],
)
def test_login_rejects_username_with_outer_whitespace(client, username):
    r = client.post("/login", data={"username": username, "password": "p"}, follow_redirects=False)
    # inválido => renderiza login (200), no loguea.
    assert r.status_code == 200
    with client.session_transaction() as sess:
        assert sess.get("_user_id") is None
        assert sess.get("boot_id") is None


@pytest.mark.parametrize("username", ["admin", "operador"])
def test_login_accepts_exact_username_sets_boot_id(client, username):
    r = client.post("/login", data={"username": username, "password": "p"}, follow_redirects=False)
    assert r.status_code in {302, 303}
    with client.session_transaction() as sess:
        assert sess.get("_user_id") in {"1", "2"}
        assert sess.get("boot_id") == "boot-test"


def test_password_is_not_stripped(client):
    # Password incorrecto (por whitespace) debe fallar.
    r = client.post("/login", data={"username": "admin", "password": "p "}, follow_redirects=False)
    assert r.status_code == 200
    with client.session_transaction() as sess:
        assert sess.get("_user_id") is None
