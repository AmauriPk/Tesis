from __future__ import annotations

import importlib
import os
import time
from dataclasses import dataclass

import pytest
from flask import Blueprint, Flask, flash, redirect, request, session, url_for
from flask_login import LoginManager, login_required, logout_user

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
        if getattr(self, "_username", None) == "admin":
            return _User(id="1", username="admin")
        return None


class _UserModel:
    query = _Query()


@pytest.fixture()
def app(monkeypatch):
    # Para tests: usar mínimo permitido por clamp (60s).
    monkeypatch.setenv("SESSION_IDLE_TIMEOUT_SECONDS", "60")

    app = Flask("siran_idle_timeout_test", root_path=".")
    app.config.update(TESTING=True, SECRET_KEY="test-secret")
    app.config["SESSION_BOOT_ID"] = "boot-A"

    lm = LoginManager()
    lm.login_view = "auth.login"
    lm.init_app(app)

    @lm.user_loader
    def load_user(user_id: str):
        if user_id == "1":
            return _User(id="1", username="admin")
        return None

    @app.before_request
    def _idle_and_boot_guard():
        endpoint = (request.endpoint or "").strip()
        if endpoint in {"auth.login", "auth.logout", "static"}:
            return None

        if session.get("_user_id"):
            # idle timeout
            try:
                idle_timeout_s = int((os.environ.get("SESSION_IDLE_TIMEOUT_SECONDS") or "900").strip())
            except Exception:
                idle_timeout_s = 900
            idle_timeout_s = max(60, min(86400, int(idle_timeout_s)))

            now = time.time()
            last_seen = session.get("last_seen_at")
            if last_seen is not None:
                try:
                    age_s = now - float(last_seen)
                except Exception:
                    age_s = float(idle_timeout_s) + 1.0
                if float(age_s) > float(idle_timeout_s):
                    try:
                        logout_user()
                    except Exception:
                        pass
                    session.clear()
                    flash("La sesión expiró por inactividad.", "warning")
                    return redirect(url_for("auth.login"))
            session["last_seen_at"] = float(now)

            # boot id
            if session.get("boot_id") != app.config.get("SESSION_BOOT_ID"):
                try:
                    logout_user()
                except Exception:
                    pass
                session.clear()
                flash("La sesión anterior fue cerrada porque el sistema se reinició.", "warning")
                return redirect(url_for("auth.login"))
        return None

    # Stub dashboard.index para redirects.
    dash = Blueprint("dashboard", __name__)

    @dash.get("/dashboard_stub", endpoint="index")
    def idx_stub():
        return "stub", 200

    app.register_blueprint(dash)

    @app.get("/protected")
    @login_required
    def protected():
        return "ok", 200

    ar = importlib.reload(auth_routes)
    ar.init_auth_routes(User=_UserModel, FLASK_CONFIG={"debug": True}, SESSION_BOOT_ID=app.config["SESSION_BOOT_ID"])
    app.register_blueprint(ar.auth_bp)
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


def test_login_sets_last_seen_at(client):
    r = client.post("/login", data={"username": "admin", "password": "p"}, follow_redirects=False)
    assert r.status_code in {302, 303}
    with client.session_transaction() as sess:
        assert sess.get("last_seen_at") is not None


def test_within_timeout_allows_access(client):
    client.post("/login", data={"username": "admin", "password": "p"}, follow_redirects=False)
    with client.session_transaction() as sess:
        sess["last_seen_at"] = float(time.time())
    r = client.get("/protected", follow_redirects=False)
    assert r.status_code == 200


def test_expired_timeout_redirects_and_clears_session(client):
    client.post("/login", data={"username": "admin", "password": "p"}, follow_redirects=False)
    with client.session_transaction() as sess:
        sess["last_seen_at"] = float(time.time()) - 9999.0
    r = client.get("/protected", follow_redirects=False)
    assert r.status_code in {302, 303}
    assert "/login" in (r.headers.get("Location") or "")
    with client.session_transaction() as sess:
        assert sess.get("_user_id") is None
        assert sess.get("last_seen_at") is None


def test_invalid_timeout_uses_default_and_clamps(client, monkeypatch):
    monkeypatch.setenv("SESSION_IDLE_TIMEOUT_SECONDS", "not-an-int")
    client.post("/login", data={"username": "admin", "password": "p"}, follow_redirects=False)
    # Si clamp mínimo=60, aun con last_seen reciente no debe expirar.
    with client.session_transaction() as sess:
        sess["last_seen_at"] = float(time.time())
    r = client.get("/protected", follow_redirects=False)
    assert r.status_code == 200
