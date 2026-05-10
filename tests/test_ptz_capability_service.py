from __future__ import annotations

import threading

from src.services.ptz_capability_service import PTZCapabilityService


class _Cfg:
    def __init__(self, *, host: str | None, port: int | None, username: str | None, password: str | None):
        self.onvif_host = host
        self.onvif_port = port
        self.onvif_username = username
        self.onvif_password = password


def test_initial_state():
    calls: list[tuple[str, bool]] = []
    svc = PTZCapabilityService(
        state_lock=threading.Lock(),
        current_detection_state={"camera_source_mode": "fixed"},
        is_camera_configured_ptz=lambda: False,
        set_auto_tracking_enabled=lambda v: calls.append(("tracking", bool(v))),
        set_inspection_mode_enabled=lambda v: calls.append(("inspection", bool(v))),
        get_or_create_camera_config=lambda: _Cfg(host=None, port=None, username=None, password=None),
        normalized_onvif_port=lambda p: int(p or 80),
    )
    assert svc.is_ptz_capable is False
    assert svc.camera_source_mode == "fixed"


def test_set_ptz_capable_true_sets_mode_ptz():
    state = {"camera_source_mode": "fixed"}
    svc = PTZCapabilityService(
        state_lock=threading.Lock(),
        current_detection_state=state,
        is_camera_configured_ptz=lambda: False,
        set_auto_tracking_enabled=lambda _v: None,
        set_inspection_mode_enabled=lambda _v: None,
        get_or_create_camera_config=lambda: _Cfg(host=None, port=None, username=None, password=None),
        normalized_onvif_port=lambda p: int(p or 80),
    )
    svc.set_ptz_capable(True, error=None)
    assert svc.is_ptz_capable is True
    assert svc.camera_source_mode == "ptz"
    assert state["camera_source_mode"] == "ptz"


def test_set_ptz_capable_false_disables_modes_if_not_configured_ptz():
    seen = {"tracking": None, "inspection": None}

    def _set_tracking(v: bool) -> None:
        seen["tracking"] = bool(v)

    def _set_inspection(v: bool) -> None:
        seen["inspection"] = bool(v)

    svc = PTZCapabilityService(
        state_lock=threading.Lock(),
        current_detection_state={"camera_source_mode": "fixed"},
        is_camera_configured_ptz=lambda: False,
        set_auto_tracking_enabled=_set_tracking,
        set_inspection_mode_enabled=_set_inspection,
        get_or_create_camera_config=lambda: _Cfg(host=None, port=None, username=None, password=None),
        normalized_onvif_port=lambda p: int(p or 80),
    )
    svc.set_ptz_capable(False, error="x")
    assert seen["tracking"] is False
    assert seen["inspection"] is False
    assert svc.camera_source_mode == "fixed"


def test_set_ptz_capable_false_keeps_mode_ptz_if_configured_ptz_true():
    svc = PTZCapabilityService(
        state_lock=threading.Lock(),
        current_detection_state={"camera_source_mode": "fixed"},
        is_camera_configured_ptz=lambda: True,
        set_auto_tracking_enabled=lambda _v: None,
        set_inspection_mode_enabled=lambda _v: None,
        get_or_create_camera_config=lambda: _Cfg(host=None, port=None, username=None, password=None),
        normalized_onvif_port=lambda p: int(p or 80),
    )
    svc.set_ptz_capable(False, error="x")
    assert svc.is_ptz_capable is False
    assert svc.camera_source_mode == "ptz"


def test_readiness_manual_true_if_configured_ptz():
    svc = PTZCapabilityService(
        state_lock=threading.Lock(),
        current_detection_state={"camera_source_mode": "fixed"},
        is_camera_configured_ptz=lambda: True,
        set_auto_tracking_enabled=lambda _v: None,
        set_inspection_mode_enabled=lambda _v: None,
        get_or_create_camera_config=lambda: _Cfg(host=None, port=None, username=None, password=None),
        normalized_onvif_port=lambda p: int(p or 80),
    )
    assert svc.is_ptz_ready_for_manual() is True


def test_readiness_automation_true_if_discovered_ptz():
    svc = PTZCapabilityService(
        state_lock=threading.Lock(),
        current_detection_state={"camera_source_mode": "fixed"},
        is_camera_configured_ptz=lambda: False,
        set_auto_tracking_enabled=lambda _v: None,
        set_inspection_mode_enabled=lambda _v: None,
        get_or_create_camera_config=lambda: _Cfg(host=None, port=None, username=None, password=None),
        normalized_onvif_port=lambda p: int(p or 80),
    )
    svc.is_ptz_capable = True
    assert svc.is_ptz_ready_for_automation() is True


def test_probe_onvif_host_missing_sets_error_and_false():
    svc = PTZCapabilityService(
        state_lock=threading.Lock(),
        current_detection_state={"camera_source_mode": "fixed"},
        is_camera_configured_ptz=lambda: False,
        set_auto_tracking_enabled=lambda _v: None,
        set_inspection_mode_enabled=lambda _v: None,
        get_or_create_camera_config=lambda: _Cfg(host="", port=80, username="u", password="p"),
        normalized_onvif_port=lambda p: int(p or 80),
    )
    ok = svc.probe_onvif_ptz_capability()
    assert ok is False
    assert svc.onvif_last_probe_error == "ONVIF host no configurado."


def test_probe_onvif_credentials_missing_sets_error_and_false():
    svc = PTZCapabilityService(
        state_lock=threading.Lock(),
        current_detection_state={"camera_source_mode": "fixed"},
        is_camera_configured_ptz=lambda: False,
        set_auto_tracking_enabled=lambda _v: None,
        set_inspection_mode_enabled=lambda _v: None,
        get_or_create_camera_config=lambda: _Cfg(host="h", port=80, username="", password=""),
        normalized_onvif_port=lambda p: int(p or 80),
    )
    ok = svc.probe_onvif_ptz_capability()
    assert ok is False
    assert svc.onvif_last_probe_error == "Credenciales ONVIF incompletas."


def test_probe_onvif_port_554_calls_normalizer():
    seen = {"called_with": None}

    def _norm(p: int | None) -> int:
        seen["called_with"] = p
        return 80

    svc = PTZCapabilityService(
        state_lock=threading.Lock(),
        current_detection_state={"camera_source_mode": "fixed"},
        is_camera_configured_ptz=lambda: False,
        set_auto_tracking_enabled=lambda _v: None,
        set_inspection_mode_enabled=lambda _v: None,
        get_or_create_camera_config=lambda: _Cfg(host="", port=554, username="u", password="p"),
        normalized_onvif_port=_norm,
    )
    _ = svc.probe_onvif_ptz_capability()
    assert seen["called_with"] == 554

