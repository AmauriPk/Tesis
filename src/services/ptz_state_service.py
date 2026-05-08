from __future__ import annotations

import threading
import time
from typing import Any


class PTZStateService:
    """
    Estado centralizado de automatización PTZ (flags + objetivo de tracking).

    Este servicio NO controla el PTZ ni mueve cámara; solo mantiene estado compartido
    con locks para lectura/escritura segura.
    """

    def __init__(self) -> None:
        # Reentrante para permitir patrones existentes como:
        # `with state_lock: set_auto_tracking_enabled(...)`
        self.state_lock = threading.RLock()
        self.tracking_target_lock = threading.Lock()

        self._auto_tracking_enabled = False
        self._inspection_mode_enabled = False

        # Mantener el mismo shape usado por el sistema actual.
        self.tracking_target_state: dict[str, Any] = {
            "has_target": False,
            "bbox": None,
            "frame_w": None,
            "frame_h": None,
            "confidence": 0.0,
            "updated_at": 0.0,
        }

        self._last_tracking_target_log_at = 0.0
        self._last_tracking_target_bbox = None

    def get_auto_tracking_enabled(self) -> bool:
        with self.state_lock:
            return bool(self._auto_tracking_enabled)

    def set_auto_tracking_enabled(self, value: bool) -> None:
        with self.state_lock:
            self._auto_tracking_enabled = bool(value)

    def get_inspection_mode_enabled(self) -> bool:
        with self.state_lock:
            return bool(self._inspection_mode_enabled)

    def set_inspection_mode_enabled(self, value: bool) -> None:
        with self.state_lock:
            self._inspection_mode_enabled = bool(value)

    def clear_tracking_target(self) -> None:
        with self.tracking_target_lock:
            self.tracking_target_state["has_target"] = False
            self.tracking_target_state["bbox"] = None
            self.tracking_target_state["updated_at"] = 0.0

    def update_tracking_target(self, payload: dict) -> None:
        try:
            has_target = bool(payload.get("has_target"))
            bbox = payload.get("bbox")
            with self.tracking_target_lock:
                self.tracking_target_state["has_target"] = bool(has_target)
                self.tracking_target_state["bbox"] = bbox if has_target else None
                self.tracking_target_state["frame_w"] = payload.get("frame_w")
                self.tracking_target_state["frame_h"] = payload.get("frame_h")
                self.tracking_target_state["confidence"] = float(payload.get("confidence") or 0.0)
                self.tracking_target_state["updated_at"] = float(payload.get("updated_at") or time.time())
            if has_target and bbox:
                now = time.time()
                if bbox != self._last_tracking_target_bbox or (now - float(self._last_tracking_target_log_at)) > 1.0:
                    self._last_tracking_target_bbox = bbox
                    self._last_tracking_target_log_at = now
                    print(
                        "[TRACKING_TARGET]",
                        f"bbox={tuple(bbox)} conf={float(payload.get('confidence') or 0.0):.3f} updated=True",
                    )
        except Exception:
            pass

    def get_tracking_target_snapshot(self) -> dict:
        with self.tracking_target_lock:
            return dict(self.tracking_target_state)
