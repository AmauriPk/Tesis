from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable

from config import _env_float


class _InspectionPatrolWorker:
    """
    Patrullaje automático:
    - Solo aplica si hardware PTZ (fail-safe por autodescubrimiento ONVIF).
    - Si no hay detección confirmada en los últimos N segundos, pan lento y continuo.
    - Si aparece amenaza (detección confirmada), se interrumpe y el tracking toma control.
    """

    def __init__(
        self,
        *,
        idle_s: float = 10.0,
        ptz_worker: Any,
        state_lock: threading.Lock,
        current_detection_state: dict,
        get_inspection_mode_enabled: Callable[[], bool],
        set_inspection_mode_enabled: Callable[[bool], None],
        get_auto_tracking_enabled: Callable[[], bool],
        is_ptz_ready_for_automation: Callable[[], bool],
        tracking_target_is_recent: Callable[[], tuple[bool, float]],
        clamp: Callable[[float, float, float], float],
    ):
        """
        Crea el worker de patrullaje.

        Args:
            idle_s: Segundos sin deteccion confirmada tras los cuales inicia el barrido PTZ.
        """
        self._idle_s = float(idle_s)
        self._ptz_worker = ptz_worker
        self._state_lock = state_lock
        self._current_detection_state = current_detection_state
        self._get_inspection_mode_enabled = get_inspection_mode_enabled
        self._set_inspection_mode_enabled = set_inspection_mode_enabled
        self._get_auto_tracking_enabled = get_auto_tracking_enabled
        self._is_ptz_ready_for_automation = is_ptz_ready_for_automation
        self._tracking_target_is_recent = tracking_target_is_recent
        self._clamp = clamp

        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._patrolling = False
        self._dir = 1.0
        self._segment_started_at: float | None = None
        self._next_action_at = 0.0
        self._phase = "move"  # move -> wait_stop -> wait_pause -> move...
        self._stop_sent_in_pause = False

    def start(self):
        """Inicia el hilo de patrullaje (idempotente)."""
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self, *, timeout_s: float = 2.0) -> None:
        """Detiene el hilo de patrullaje (best-effort)."""
        self._stop.set()
        try:
            self._thread.join(timeout=float(timeout_s))
        except Exception:
            pass

    def _run(self):
        """
        Loop del patrullaje:

        - Si hay deteccion confirmada => desactiva inspection y emite STOP PTZ.
        - Si no hay deteccion por `idle_s` => pan lento con sweep de duracion limitada.
        - Si hay tracking activo => el tracking tiene prioridad y el patrullaje se apaga.
        """
        while not self._stop.is_set():
            try:
                time.sleep(0.25)
                with self._state_lock:
                    enabled = bool(self._get_inspection_mode_enabled())
                    tracking = bool(self._get_auto_tracking_enabled())
                    detected = bool(self._current_detection_state.get("detected"))
                ptz_ok = bool(self._is_ptz_ready_for_automation())
                has_recent_target, _age = self._tracking_target_is_recent()
                paused_by_detection = bool(tracking and detected)
                paused_by_tracking_target = bool(tracking and has_recent_target)

                if not enabled or not ptz_ok:
                    if self._patrolling:
                        self._ptz_worker.enqueue_stop()
                        self._patrolling = False
                    self._segment_started_at = None
                    self._phase = "move"
                    self._next_action_at = 0.0
                    self._stop_sent_in_pause = False
                    continue

                now = time.time()
                mode = (os.environ.get("PTZ_INSPECTION_MODE") or "sweep").strip().lower() or "sweep"
                speed = float(_env_float("PTZ_INSPECTION_SPEED", 0.45))
                duration = float(_env_float("PTZ_INSPECTION_DURATION", 4.0))
                pause = float(_env_float("PTZ_INSPECTION_PAUSE", 0.7))
                if mode == "sweep":
                    speed = self._clamp(abs(float(speed)), 0.05, 1.00)
                    duration = self._clamp(float(duration), 1.0, 30.0)
                    pause = self._clamp(float(pause), 0.2, 5.0)
                else:
                    speed = self._clamp(abs(float(speed)), 0.05, 0.80)
                    duration = self._clamp(float(duration), 0.5, 8.0)
                    pause = self._clamp(float(pause), 0.2, 3.0)
                x_speed = float(speed) * float(self._dir)

                if paused_by_detection or paused_by_tracking_target:
                    if self._patrolling and not self._stop_sent_in_pause:
                        self._ptz_worker.enqueue_stop()
                        self._stop_sent_in_pause = True
                        print(
                            "[INSPECTION_CMD]",
                            f"phase=stop paused_by_tracking={bool(paused_by_tracking_target)} paused_by_detection={bool(paused_by_detection)}",
                        )
                    self._patrolling = False
                    self._phase = "move"
                    self._next_action_at = 0.0
                    continue

                self._stop_sent_in_pause = False

                if float(self._next_action_at) > 0.0 and now < float(self._next_action_at):
                    continue

                phase = str(self._phase)
                if phase == "move":
                    continuous_360 = (os.environ.get("PTZ_INSPECTION_CONTINUOUS_360") or "1").strip().lower() in {
                        "1",
                        "true",
                        "t",
                        "yes",
                        "y",
                        "on",
                    }
                    mode_txt = "continuous_360" if continuous_360 else "sweep"
                    self._ptz_worker.enqueue_move(
                        x=float(x_speed),
                        y=0.0,
                        zoom=0.0,
                        duration_s=float(duration),
                        source="inspection",
                    )
                    self._patrolling = True
                    self._phase = "wait_stop"
                    self._next_action_at = now + float(duration)
                    print(
                        "[INSPECTION_CMD]",
                        f"phase=move mode={mode_txt} direction={'right' if self._dir > 0 else 'left'} x={float(x_speed):.2f} duration={float(duration):.1f}",
                    )
                elif phase == "wait_stop":
                    self._ptz_worker.enqueue_stop()
                    self._patrolling = False
                    self._phase = "wait_pause"
                    self._next_action_at = now + float(pause)
                    print("[INSPECTION_CMD]", "phase=stop")
                else:  # wait_pause
                    continuous_360 = (os.environ.get("PTZ_INSPECTION_CONTINUOUS_360") or "1").strip().lower() in {
                        "1",
                        "true",
                        "t",
                        "yes",
                        "y",
                        "on",
                    }
                    if not continuous_360:
                        self._dir = -1.0 * float(self._dir)
                    self._phase = "move"
                    self._next_action_at = 0.0
                    print(
                        "[INSPECTION_CMD]",
                        f"phase=pause_done next_direction={'right' if self._dir > 0 else 'left'}",
                    )
            except Exception as e:
                print(f"[INSPECTION_WORKER][ERROR] {e}")

