from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable


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
                        print("[TRACKING_WORKER]", "stop reason=tracking_disabled")
                    continue

                snap = self._get_tracking_target_snapshot()
                now = time.time()

                try:
                    ttl = float(os.environ.get("PTZ_TRACKING_TARGET_TTL", "1.5"))
                except Exception:
                    ttl = 1.5
                ttl = float(self._clamp(ttl, 0.5, 3.0))

                has_target = bool(snap.get("has_target")) and bool(snap.get("bbox"))
                age = now - float(snap.get("updated_at") or 0.0)
                if (not has_target) or (age > ttl):
                    if self._was_moving:
                        self._ptz_worker.enqueue_stop()
                        self._was_moving = False
                        print("[TRACKING_WORKER]", f"stop reason=target_lost age={float(age):.2f}")
                    continue

                try:
                    command_interval = float(os.environ.get("PTZ_TRACKING_COMMAND_INTERVAL", "0.35"))
                except Exception:
                    command_interval = 0.35
                command_interval = float(self._clamp(command_interval, 0.20, 1.00))
                if (now - float(self._last_cmd_at)) < float(command_interval):
                    continue

                try:
                    max_speed = float(os.environ.get("PTZ_TRACKING_MAX_SPEED", "0.50"))
                except Exception:
                    max_speed = 0.50
                max_speed = float(self._clamp(max_speed, 0.10, 0.70))

                try:
                    min_speed = float(os.environ.get("PTZ_TRACKING_MIN_SPEED", "0.12"))
                except Exception:
                    min_speed = 0.12
                min_speed = float(self._clamp(min_speed, 0.05, 0.30))

                try:
                    pan_duration = float(
                        os.environ.get("PTZ_TRACKING_PAN_DURATION", os.environ.get("PTZ_TRACKING_DURATION", "0.30"))
                    )
                except Exception:
                    pan_duration = 0.30
                pan_duration = float(self._clamp(pan_duration, 0.10, 1.00))

                try:
                    tilt_duration = float(
                        os.environ.get("PTZ_TRACKING_TILT_DURATION", os.environ.get("PTZ_TRACKING_DURATION", "0.55"))
                    )
                except Exception:
                    tilt_duration = 0.55
                tilt_duration = float(self._clamp(tilt_duration, 0.10, 1.50))

                try:
                    pan_speed = float(os.environ.get("PTZ_TRACKING_PAN_SPEED", os.environ.get("PTZ_TRACKING_SPEED", "0.35")))
                except Exception:
                    pan_speed = 0.35
                pan_speed = float(self._clamp(pan_speed, 0.05, 0.80))

                try:
                    tilt_speed = float(
                        os.environ.get("PTZ_TRACKING_TILT_SPEED", os.environ.get("PTZ_TRACKING_SPEED", "0.45"))
                    )
                except Exception:
                    tilt_speed = 0.45
                tilt_speed = float(self._clamp(tilt_speed, 0.05, 0.95))

                try:
                    tolerance_frac = float(os.environ.get("PTZ_TRACKING_TOLERANCE", "0.18"))
                except Exception:
                    tolerance_frac = 0.18
                tolerance_frac = float(self._clamp(tolerance_frac, 0.05, 0.45))

                try:
                    edge_tilt_boost = float(os.environ.get("PTZ_TRACKING_EDGE_TILT_BOOST", "1.8"))
                except Exception:
                    edge_tilt_boost = 1.8
                edge_tilt_boost = float(self._clamp(edge_tilt_boost, 1.0, 3.0))

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

                pan = 0.0
                reason = "center"
                if cx < (fx - deadzone_x):
                    pan = -float(pan_speed)
                    reason = "left"
                elif cx > (fx + deadzone_x):
                    pan = float(pan_speed)
                    reason = "right"

                tilt = 0.0
                if top_edge:
                    tilt = float(tilt_speed) * float(edge_tilt_boost)
                    edge_boost_applied = True
                    reason = "top_edge"
                elif bottom_edge:
                    tilt = -float(tilt_speed) * float(edge_tilt_boost)
                    edge_boost_applied = True
                    reason = "bottom_edge"
                else:
                    if cy < (fy - deadzone_y):
                        tilt = float(tilt_speed)
                        reason = "up"
                    elif cy > (fy + deadzone_y):
                        tilt = -float(tilt_speed)
                        reason = "down"

                if abs(float(tilt)) > 1.0:
                    tilt = 1.0 if float(tilt) > 0 else -1.0

                if os.environ.get("PTZ_INVERT_PAN", "").strip().lower() in {"1", "true", "t", "yes", "y", "on"}:
                    pan = -1.0 * float(pan)
                if os.environ.get("PTZ_INVERT_TILT", "").strip().lower() in {"1", "true", "t", "yes", "y", "on"}:
                    tilt = -1.0 * float(tilt)

                def _apply_min(v: float) -> float:
                    if abs(float(v)) < 1e-6:
                        return 0.0
                    sign = 1.0 if float(v) > 0 else -1.0
                    mag = float(min(max(abs(float(v)), float(min_speed)), float(max_speed)))
                    return float(sign) * float(mag)

                pan = _apply_min(float(pan))
                tilt = _apply_min(float(tilt))

                if abs(float(pan)) < 1e-6 and abs(float(tilt)) < 1e-6:
                    if top_edge or bottom_edge:
                        self._last_cmd_at = now
                        continue
                    if self._was_moving:
                        self._ptz_worker.enqueue_stop()
                        self._was_moving = False
                        print("[TRACKING_WORKER]", "stop reason=centered")
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
                print(
                    "[TRACKING_WORKER]",
                    f"move pan={float(pan):.3f} tilt={float(tilt):.3f} pan_speed={float(pan_speed):.2f} "
                    f"tilt_speed={float(tilt_speed):.2f} duration={float(duration_s):.2f} edge_boost={bool(edge_boost_applied)} "
                    f"reason={reason} age={float(age):.2f}",
                )
            except Exception as e:
                now = time.time()
                if (now - float(self._last_error_log_at)) > 2.0:
                    print(f"[TRACKING_WORKER][ERROR] {e}")
                    self._last_error_log_at = now

