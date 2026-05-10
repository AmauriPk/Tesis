from __future__ import annotations

import importlib

import pytest

from src.services.session_security_service import SessionSecurityService


def test_generates_boot_id_when_missing():
    s = SessionSecurityService()
    assert isinstance(s.boot_id, str)
    assert len(s.boot_id) >= 16


def test_respects_provided_boot_id():
    s = SessionSecurityService(boot_id="x")
    assert s.boot_id == "x"


def test_idle_timeout_default_900(monkeypatch):
    monkeypatch.delenv("SESSION_IDLE_TIMEOUT_SECONDS", raising=False)
    assert SessionSecurityService.get_idle_timeout_seconds() == 900


@pytest.mark.parametrize("value", ["", "nope", "  nope  "])
def test_idle_timeout_invalid_falls_back_to_900(monkeypatch, value):
    monkeypatch.setenv("SESSION_IDLE_TIMEOUT_SECONDS", value)
    assert SessionSecurityService.get_idle_timeout_seconds() == 900


def test_idle_timeout_clamps_min_60(monkeypatch):
    monkeypatch.setenv("SESSION_IDLE_TIMEOUT_SECONDS", "10")
    assert SessionSecurityService.get_idle_timeout_seconds() == 60


def test_idle_timeout_clamps_max_86400(monkeypatch):
    monkeypatch.setenv("SESSION_IDLE_TIMEOUT_SECONDS", "9999999")
    assert SessionSecurityService.get_idle_timeout_seconds() == 86400


def test_is_session_from_old_boot():
    s = SessionSecurityService(boot_id="bootA")
    assert s.is_session_from_old_boot("bootB") is True
    assert s.is_session_from_old_boot("bootA") is False
    assert s.is_session_from_old_boot(None) is False


def test_is_idle_expired_recent(monkeypatch):
    monkeypatch.setenv("SESSION_IDLE_TIMEOUT_SECONDS", "60")
    s = SessionSecurityService(boot_id="b")
    assert s.is_idle_expired(100.0, now=120.0) is False


def test_is_idle_expired_expired(monkeypatch):
    monkeypatch.setenv("SESSION_IDLE_TIMEOUT_SECONDS", "60")
    s = SessionSecurityService(boot_id="b")
    assert s.is_idle_expired(100.0, now=200.0) is True


def test_mark_seen_sets_last_seen_at():
    s = SessionSecurityService(boot_id="b")
    sess = {}
    s.mark_seen(sess, now=123.0)
    assert sess.get("last_seen_at") == 123.0

