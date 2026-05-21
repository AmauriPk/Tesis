from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Callable

from config import PTZ_CONFIG

logger = logging.getLogger(__name__)


class TrackingPTZWorker:
    def __init__(
        self,
        *,
        state_lock: threading.RLock | threading.Lock,
        ptz_worker: Any,
        get_auto_tracking_enabled: Callable[[], bool],
        is_ptz_ready_for_automation: Callable[[], bool],
        get_tracking_target_snapshot: Callable[[], dict],
        clamp: Callable[[float, float, float], float],
    ):
        self._state_lock = state_lock
        self._ptz_worker = ptz_worker
        self._get_auto_tracking_enabled = get_auto_tracking_enabled
        self._is_ptz_ready_for_automation = is_ptz_ready_for_automation
        self._get_tracking_target_snapshot = get_tracking_target_snapshot
        self._clamp = clamp

        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._last_cmd_at = 0.0
        self._last_cmd = (0.0, 0.0)
        self._was_moving = False
        self._last_error_log_at = 0.0

    def start(self):
        if not self._thread.is_alive():
            self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            try:
                time.sleep(0.20)
                with self._state_lock:
                    enabled = bool(self._get_auto_tracking_enabled())
                ptz_ok = bool(self._is_ptz_ready_for_automation())
                if not enabled or not ptz_ok:
                    if self._was_moving:
                        self._ptz_worker.enqueue_stop()
                        self._was_moving = False
                        logger.debug("tracking_worker stop reason=tracking_disabled")
                    continue

                snap = self._get_tracking_target_snapshot()
                now = time.time()

                ttl = float(self._clamp(PTZ_CONFIG["target_ttl"], 0.5, 3.0))

                has_target = bool(snap.get("has_target")) and bool(snap.get("bbox"))
                age = now - float(snap.get("updated_at") or 0.0)
                if (not has_target) or (age > ttl):
                    if self._was_moving:
                        self._ptz_worker.enqueue_stop()
                        self._was_moving = False
                        logger.debug("tracking_worker stop reason=target_lost age=%.2f", float(age))
                    continue

                command_interval = float(self._clamp(PTZ_CONFIG["command_interval"], 0.20, 1.00))
                if (now - float(self._last_cmd_at)) < float(command_interval):
                    continue

                max_speed     = float(self._clamp(PTZ_CONFIG["max_speed"],      0.10, 0.70))
                min_speed     = float(self._clamp(PTZ_CONFIG["min_speed"],      0.05, 0.30))
                pan_duration  = float(self._clamp(PTZ_CONFIG["pan_duration"],   0.10, 1.00))
                tilt_duration = float(self._clamp(PTZ_CONFIG["tilt_duration"],  0.10, 1.50))
                pan_speed     = float(self._clamp(PTZ_CONFIG["pan_speed"],      0.05, 0.80))
                tilt_speed    = float(self._clamp(PTZ_CONFIG["tilt_speed"],     0.05, 0.95))
                tolerance_frac = float(self._clamp(PTZ_CONFIG["tolerance"],     0.05, 0.45))
                edge_tilt_boost = float(self._clamp(PTZ_CONFIG["edge_tilt_boost"], 1.0, 3.0))

                bbox = snap.get("bbox") or []
                fw = int(snap.get("frame_w") or 0)
                fh = int(snap.get("frame_h") or 0)
                if fw <= 0 or fh <= 0 or not bbox or len(bbox) != 4:
                    continue

                x1, y1, x2, y2 = [float(v) for v in bbox]
                cx = (x1 + x2) / 2.0
                cy = (y1 + y2) / 2.0
                fx = float(fw) / 2.0
                fy = float(fh) / 2.0

                deadzone_x = float(fw) * float(tolerance_frac) / 2.0
                deadzone_y = float(fh) * float(tolerance_frac) / 2.0

                top_edge = float(y1) <= float(fh) * 0.05
                bottom_edge = float(y2) >= float(fh) * 0.95
                edge_boost_applied = False

                k_pan  = float(PTZ_CONFIG["k_pan"])
                k_tilt = float(PTZ_CONFIG["k_tilt"])

                # Error normalizado [-0.5, 0.5]: (0,0) = centro del frame
                error_x = (cx / float(fw)) - 0.5
                error_y = (cy / float(fh)) - 0.5
                deadzone_half = float(tolerance_frac) / 2.0

                def _prop_clamp(raw: float, min_s: float, max_s: float) -> float:
                    if abs(raw) < min_s:
                        return 0.0
                    return float(max(min_s, min(max_s, abs(raw)))) * (1.0 if raw > 0 else -1.0)

                pan = 0.0
                reason = "center"
                if abs(error_x) >= deadzone_half:
                    raw_pan = float(k_pan) * float(error_x)
                    pan = _prop_clamp(raw_pan, float(min_speed), float(max_speed))
                    if pan > 1e-6:
                        reason = "right"
                    elif pan < -1e-6:
                        reason = "left"

                tilt = 0.0
                if top_edge:
                    tilt = float(self._clamp(float(tilt_speed) * float(edge_tilt_boost), -1.0, 1.0))
                    edge_boost_applied = True
                    reason = "top_edge"
                elif bottom_edge:
                    tilt = float(self._clamp(-float(tilt_speed) * float(edge_tilt_boost), -1.0, 1.0))
                    edge_boost_applied = True
                    reason = "bottom_edge"
                elif abs(error_y) >= deadzone_half:
                    raw_tilt = -float(k_tilt) * float(error_y)
                    tilt = _prop_clamp(raw_tilt, float(min_speed), float(max_speed))
                    if tilt > 1e-6:
                        reason = "up"
                    elif tilt < -1e-6:
                        reason = "down"

                if os.environ.get("PTZ_INVERT_PAN", "").strip().lower() in {"1", "true", "t", "yes", "y", "on"}:
                    pan = -1.0 * float(pan)
                if os.environ.get("PTZ_INVERT_TILT", "").strip().lower() in {"1", "true", "t", "yes", "y", "on"}:
                    tilt = -1.0 * float(tilt)

                if abs(float(pan)) < 1e-6 and abs(float(tilt)) < 1e-6:
                    if top_edge or bottom_edge:
                        self._last_cmd_at = now
                        continue
                    if self._was_moving:
                        self._ptz_worker.enqueue_stop()
                        self._was_moving = False
                        logger.debug("tracking_worker stop reason=centered")
                    self._last_cmd_at = now
                    continue

                cmd = (float(pan), float(tilt))
                if cmd == tuple(self._last_cmd) and self._was_moving:
                    self._last_cmd_at = now
                    continue

                duration_s = float(pan_duration)
                if abs(float(tilt)) > 1e-6 and abs(float(pan)) <= 1e-6:
                    duration_s = float(tilt_duration)
                elif abs(float(tilt)) > 1e-6 and abs(float(pan)) > 1e-6:
                    duration_s = float(max(float(pan_duration), float(tilt_duration)))

                self._ptz_worker.enqueue_move(x=float(pan), y=float(tilt), zoom=0.0, duration_s=float(duration_s), source="tracking")
                self._last_cmd = cmd
                self._last_cmd_at = now
                self._was_moving = True
                logger.debug(
                    "tracking_worker move pan=%.3f tilt=%.3f pan_speed=%.2f tilt_speed=%.2f duration=%.2f edge_boost=%s reason=%s age=%.2f",
                    float(pan), float(tilt), float(pan_speed), float(tilt_speed),
                    float(duration_s), bool(edge_boost_applied), reason, float(age),
                )
            except Exception as e:
                now = time.time()
                if (now - float(self._last_error_log_at)) > 2.0:
                    logger.error("tracking_worker error: %s", e)
                    self._last_error_log_at = now

