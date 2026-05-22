from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Callable

from config import PTZ_CONFIG

logger = logging.getLogger(__name__)


class ReacquisitionPattern:
    """
    Genera secuencia de movimientos de búsqueda tras pérdida de target.
    Patrón: L → R → L+arriba → R+arriba → L+abajo → R+abajo → arriba → abajo
    Simula barrido angular ±15° usando ContinuousMove con pulsos cortos.
    """

    _PATTERN = [
        (-1,  0),   # pan izquierda
        ( 1,  0),   # pan derecha
        (-1,  1),   # izquierda + arriba
        ( 1,  1),   # derecha + arriba
        (-1, -1),   # izquierda + abajo
        ( 1, -1),   # derecha + abajo
        ( 0,  1),   # tilt arriba (centro)
        ( 0, -1),   # tilt abajo (centro)
    ]

    def __init__(self, speed: float, pulse_s: float, pause_s: float, total_s: float):
        self.speed    = float(speed)
        self.pulse_s  = float(pulse_s)
        self.pause_s  = float(pause_s)
        self.total_s  = float(total_s)
        self._started_at  = time.time()
        self._step_idx    = 0
        self._step_until  = time.time() + float(pulse_s)  # primer pulso arranca de inmediato
        self._pause_until = 0.0

    @property
    def expired(self) -> bool:
        return (time.time() - self._started_at) >= self.total_s

    def next_command(self) -> tuple[float, float] | None:
        """
        Retorna (pan, tilt) para el pulso actual, o None si está en pausa.
        Avanza el patrón automáticamente cuando el pulso termina.
        """
        now = time.time()

        if self.expired:
            return None

        if now < self._pause_until:
            return None

        if now < self._step_until:
            pan_s, tilt_s = self._PATTERN[self._step_idx % len(self._PATTERN)]
            return (pan_s * self.speed, tilt_s * self.speed)

        # Pulso terminado → pausa y avanzar al siguiente paso
        self._pause_until = now + self.pause_s
        self._step_idx   += 1
        self._step_until  = self._pause_until + self.pulse_s
        return None


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
        self._reacq: ReacquisitionPattern | None = None
        self._reacq_log_done = False  # True = reacq agotada; previene reinicio hasta recuperar target

    def start(self):
        if not self._thread.is_alive():
            self._thread.start()

    def get_reacq_state(self) -> dict:
        """Estado de readquisición para exposición en métricas."""
        reacq = self._reacq
        if reacq is None:
            return {"ptz_reacquiring": False, "ptz_reacq_remaining_s": 0.0}
        elapsed = time.time() - reacq._started_at
        remaining = round(max(0.0, reacq.total_s - elapsed), 1)
        return {"ptz_reacquiring": not reacq.expired, "ptz_reacq_remaining_s": remaining}

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
                target_lost = (not has_target) or (age > ttl)

                if target_lost:
                    if bool(PTZ_CONFIG.get("reacq_enabled", True)):
                        # Iniciar readquisición si no está activa y no está agotada
                        if self._reacq is None and not self._reacq_log_done:
                            self._reacq = ReacquisitionPattern(
                                speed=float(PTZ_CONFIG["reacq_speed"]),
                                pulse_s=float(PTZ_CONFIG["reacq_pulse_s"]),
                                pause_s=float(PTZ_CONFIG["reacq_pause_s"]),
                                total_s=float(PTZ_CONFIG["reacq_duration_s"]),
                            )
                            logger.info(
                                "PTZ readquisición iniciada — buscando target por %.1fs",
                                float(PTZ_CONFIG["reacq_duration_s"]),
                            )

                        if self._reacq is not None:
                            if self._reacq.expired:
                                if not self._reacq_log_done:
                                    logger.warning("PTZ readquisición agotada — target no recuperado")
                                    self._reacq_log_done = True
                                self._reacq = None
                                if self._was_moving:
                                    self._ptz_worker.enqueue_stop()
                                    self._was_moving = False
                            else:
                                cmd = self._reacq.next_command()
                                if cmd is not None:
                                    pan, tilt = cmd
                                    self._ptz_worker.enqueue_move(
                                        x=float(pan), y=float(tilt), zoom=0.0,
                                        duration_s=float(PTZ_CONFIG["reacq_pulse_s"]),
                                        source="reacq",
                                    )
                                    self._was_moving = True
                                else:
                                    if self._was_moving:
                                        self._ptz_worker.enqueue_stop()
                                        self._was_moving = False
                        else:
                            # Reacq agotada — mantener parado
                            if self._was_moving:
                                self._ptz_worker.enqueue_stop()
                                self._was_moving = False
                    else:
                        # Readquisición deshabilitada — comportamiento original
                        if self._was_moving:
                            self._ptz_worker.enqueue_stop()
                            self._was_moving = False
                            logger.debug("tracking_worker stop reason=target_lost age=%.2f", float(age))
                    continue

                # Target recuperado — cancelar readquisición activa si existía
                if self._reacq is not None or self._reacq_log_done:
                    logger.info("PTZ target recuperado — readquisición cancelada")
                    self._reacq = None
                    self._reacq_log_done = False

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

                if PTZ_CONFIG["invert_pan"]:
                    pan = -1.0 * float(pan)
                if PTZ_CONFIG["invert_tilt"]:
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

