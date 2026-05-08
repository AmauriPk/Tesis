from __future__ import annotations

import time

from src.services.ptz_state_service import PTZStateService


def test_flags_default_false():
    svc = PTZStateService()
    assert svc.get_auto_tracking_enabled() is False
    assert svc.get_inspection_mode_enabled() is False


def test_set_flags():
    svc = PTZStateService()
    svc.set_auto_tracking_enabled(True)
    assert svc.get_auto_tracking_enabled() is True
    svc.set_inspection_mode_enabled(True)
    assert svc.get_inspection_mode_enabled() is True


def test_tracking_target_default_shape():
    svc = PTZStateService()
    snap = svc.get_tracking_target_snapshot()
    assert snap["has_target"] is False
    assert snap["bbox"] is None
    assert "updated_at" in snap


def test_update_tracking_target_and_snapshot_copy():
    svc = PTZStateService()
    payload = {
        "has_target": True,
        "bbox": [1, 2, 3, 4],
        "frame_w": 1280,
        "frame_h": 720,
        "confidence": 0.9,
        "updated_at": time.time(),
    }
    svc.update_tracking_target(payload)
    snap1 = svc.get_tracking_target_snapshot()
    assert snap1["has_target"] is True
    assert snap1["bbox"] == [1, 2, 3, 4]
    assert snap1["frame_w"] == 1280
    assert snap1["frame_h"] == 720
    assert float(snap1["confidence"]) == 0.9

    # snapshot debe ser copia (mutar snapshot no debe mutar estado interno)
    snap1["has_target"] = False
    snap2 = svc.get_tracking_target_snapshot()
    assert snap2["has_target"] is True


def test_clear_tracking_target():
    svc = PTZStateService()
    svc.update_tracking_target({"has_target": True, "bbox": [1, 2, 3, 4]})
    svc.clear_tracking_target()
    snap = svc.get_tracking_target_snapshot()
    assert snap["has_target"] is False
    assert snap["bbox"] is None
    assert float(snap["updated_at"]) == 0.0


def test_update_tracking_target_invalid_payload_does_not_raise():
    svc = PTZStateService()
    svc.update_tracking_target({"has_target": True, "bbox": object()})
    svc.update_tracking_target({"has_target": "no-bool", "confidence": "not-float"})
    svc.update_tracking_target(None)  # type: ignore[arg-type]

