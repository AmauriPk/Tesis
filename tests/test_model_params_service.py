from __future__ import annotations

import os

from src.services.model_params_service import ModelParamsService


def _env_float(_name: str, default: float) -> float:
    return default


def _env_int(_name: str, default: int) -> int:
    return default


def test_get_model_params_shape_and_copy():
    svc = ModelParamsService(env_float=_env_float, env_int=_env_int)
    params1 = svc.get_model_params()
    assert set(params1.keys()) == {"confidence_threshold", "persistence_frames", "iou_threshold"}

    # Debe ser copia (mutar no afecta al estado)
    params1["confidence_threshold"] = 0.1
    params2 = svc.get_model_params()
    assert params2["confidence_threshold"] != 0.1


def test_update_model_params_updates_values_and_normalizes_persistence():
    svc = ModelParamsService(env_float=_env_float, env_int=_env_int)
    updated = svc.update_model_params(confidence_threshold=0.77, persistence_frames=0, iou_threshold=0.33)
    assert updated["confidence_threshold"] == 0.77
    assert updated["iou_threshold"] == 0.33
    assert updated["persistence_frames"] == 1


def test_get_detection_persistence_frames_default_and_env(monkeypatch):
    svc = ModelParamsService(env_float=_env_float, env_int=_env_int)
    monkeypatch.delenv("DETECTION_PERSISTENCE_FRAMES", raising=False)
    assert svc.get_detection_persistence_frames() == 3

    monkeypatch.setenv("DETECTION_PERSISTENCE_FRAMES", "5")
    assert svc.get_detection_persistence_frames() == 5

    monkeypatch.setenv("DETECTION_PERSISTENCE_FRAMES", "0")
    assert svc.get_detection_persistence_frames() == 1

    monkeypatch.setenv("DETECTION_PERSISTENCE_FRAMES", "nope")
    assert svc.get_detection_persistence_frames() == 3

