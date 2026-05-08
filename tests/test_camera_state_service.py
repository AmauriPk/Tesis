from __future__ import annotations

import json

import pytest

from src.services import camera_state_service as css


@pytest.fixture()
def camera_root(tmp_path):
    css.init_camera_state_service(root_path=str(tmp_path))
    return tmp_path


def test_leer_config_default_false_when_missing(camera_root):
    assert css.leer_config_camara() is False


def test_guardar_y_leer_config(camera_root):
    css.guardar_config_camara(True)
    assert (camera_root / "config_camara.json").exists()
    assert css.leer_config_camara() is True

    css.guardar_config_camara(False)
    assert css.leer_config_camara() is False


def test_get_configured_camera_type(camera_root):
    assert css.get_configured_camera_type() == "fixed"
    css.guardar_config_camara(True)
    assert css.get_configured_camera_type() == "ptz"


def test_set_configured_camera_type_persists(camera_root):
    assert css.set_configured_camera_type("ptz") == "ptz"
    assert css.leer_config_camara() is True

    assert css.set_configured_camera_type("valor_invalido") == "fixed"
    assert css.leer_config_camara() is False


def test_leer_config_corrupt_json_returns_false(camera_root):
    p = camera_root / "config_camara.json"
    p.write_text("{not-json", encoding="utf-8")
    assert css.leer_config_camara() is False


def test_leer_config_missing_is_ptz_key_defaults_false(camera_root):
    p = camera_root / "config_camara.json"
    p.write_text(json.dumps({"x": 1}), encoding="utf-8")
    assert css.leer_config_camara() is False

