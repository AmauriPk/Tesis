from __future__ import annotations

import queue
import threading
import time
from typing import Any, Callable, Optional, Type


def _ptz_vector(direction: str):
    """Convierte una dirección simple (joystick) a vector (pan, tilt, zoom)."""
    if direction == "left":
        return (-0.3, 0.0, 0.0)
    if direction == "right":
        return (0.3, 0.0, 0.0)
    if direction == "up":
        return (0.0, 0.3, 0.0)
    if direction == "down":
        return (0.0, -0.3, 0.0)
    return (0.0, 0.0, 0.0)


class PTZCommandWorker:
    """
    Ejecuta comandos PTZ en un hilo separado para evitar congelamientos.

    La UI y el thread de inferencia no deben llamar directamente a ONVIF/PTZ porque:
    - ONVIF puede bloquear por red/RTT.
    - Un exceso de comandos puede saturar el PTZ y causar drift/jitter.

    Este worker aplica:
    - Cola con drop/backpressure (maxsize).
    - Rate-limit de movimientos.
    - Reconstrucción del controlador en caso de error.
    """

    def __init__(
        self,
        *,
        app: Any,
        get_or_create_camera_config: Callable[[], Any],
        normalized_onvif_port: Callable[[int | None], int],
        PTZController: Type[Any],
    ):
        """
        Inicializa la cola, el thread y el estado interno del worker.

        Args:
            app: instancia de Flask (solo para `app.app_context()` dentro del hilo).
            get_or_create_camera_config: callable que retorna CameraConfig.
            normalized_onvif_port: normaliza puerto ONVIF.
            PTZController: clase/controlador PTZ (no se define aquí).
        """
        self._app = app
        self._get_or_create_camera_config = get_or_create_camera_config
        self._normalized_onvif_port = normalized_onvif_port
        self._PTZController = PTZController

        self._q: queue.Queue[dict] = queue.Queue(maxsize=80)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._controller: Optional[Any] = None
        self._last_cmd_at = 0.0
        self._last_vec = (0.0, 0.0)
        self._delta_threshold = 0.05

    def start(self):
        """Inicia el hilo worker (idempotente)."""
        if not self._thread.is_alive():
            self._thread.start()

    def enqueue_move(self, *, x: float, y: float, zoom: float = 0.0, duration_s: float = 0.15, source: str = "manual"):
        """
        Encola un movimiento continuo (pan/tilt/zoom) con duración limitada.
        Aplica filtro de "cambio mínimo" para evitar spamear movimientos casi idénticos.
        """
        try:
            x_f = float(x)
            y_f = float(y)
        except Exception:
            return
        last_x, last_y = self._last_vec
        is_stop_vec = abs(x_f) <= 1e-9 and abs(y_f) <= 1e-9
        if (
            (not is_stop_vec)
            and (abs(x_f - float(last_x)) <= self._delta_threshold)
            and (abs(y_f - float(last_y)) <= self._delta_threshold)
        ):
            return
        self._last_vec = (float(x_f), float(y_f))
        try:
            self._q.put_nowait(
                {
                    "type": "move",
                    "x": float(x_f),
                    "y": float(y_f),
                    "zoom": float(zoom),
                    "duration_s": float(duration_s),
                    "source": str(source or "manual"),
                }
            )
            print(
                "[PTZ_QUEUE]",
                f"enqueue move source={str(source or 'manual')} x={float(x_f):.3f} y={float(y_f):.3f} "
                f"zoom={float(zoom):.3f} duration={float(duration_s):.2f}",
            )
        except Exception:
            pass

    def enqueue_direction(self, direction: str):
        """Encola un movimiento direccional (arriba/abajo/izq/der) para el joystick."""
        x, y, z = _ptz_vector(direction)
        self.enqueue_move(x=x, y=y, zoom=z, duration_s=0.15)

    def enqueue_stop(self):
        """
        Encola un STOP PTZ con prioridad para evitar drift.
        Intenta limpiar la cola antes de insertar el stop.
        """
        try:
            try:
                with self._q.mutex:  # type: ignore[attr-defined]
                    self._q.queue.clear()  # type: ignore[attr-defined]
            except Exception:
                pass
            self._last_vec = (0.0, 0.0)
            self._q.put_nowait({"type": "stop"})
            print("[PTZ_QUEUE]", "enqueue stop")
        except Exception:
            pass

    def _get_controller(self) -> Optional[Any]:
        """
        Construye un controlador PTZ desde la configuración persistida.

        Returns:
            Una instancia de `PTZController` si hay credenciales/host configurados; si no, None.
        """
        with self._app.app_context():
            cfg = self._get_or_create_camera_config()
            if not cfg.onvif_host or not cfg.onvif_username or not cfg.onvif_password:
                return None
            port = self._normalized_onvif_port(cfg.onvif_port)
            if int(cfg.onvif_port or 0) == 554:
                print("[ONVIF][WARN] onvif_port=554 parece RTSP; usando 80 para ONVIF.")
            username = str(cfg.onvif_username or "")
            password = str(cfg.onvif_password or "")
            print(
                "[PTZ_CFG]",
                {
                    "host": str(cfg.onvif_host or ""),
                    "port": int(port),
                    "username": username,
                    "password_configurada": bool(password),
                    "password_len": len(password) if password else 0,
                },
            )
            return self._PTZController(
                host=cfg.onvif_host,
                port=int(port),
                username=username,
                password=password,
            )

    def _run(self):
        """Loop del worker: rate-limit y ejecución segura de comandos ONVIF PTZ."""
        while not self._stop.is_set():
            try:
                cmd = self._q.get(timeout=0.2)
            except queue.Empty:
                continue
            cmd_type = (cmd.get("type") or "").lower()
            cmd_source = str(cmd.get("source") or "manual").lower()
            if cmd_type == "move":
                now = time.time()
                if now - self._last_cmd_at < 0.20:
                    continue
                self._last_cmd_at = now
            try:
                if self._controller is None:
                    self._controller = self._get_controller()
                if self._controller is None:
                    print(f"[PTZ_WORKER][ERROR] source={cmd_source} error=no_controller_configured")
                    continue
                if cmd_type == "stop":
                    print("[PTZ_WORKER]", "executing stop")
                    self._controller.stop()
                    print("[PTZ_WORKER]", "done stop")
                    continue
                if cmd_type == "move":
                    x = float(cmd.get("x") or 0.0)
                    y = float(cmd.get("y") or 0.0)
                    z = float(cmd.get("zoom") or 0.0)
                    duration_s = float(cmd.get("duration_s") or 0.15)
                    print(
                        "[PTZ_WORKER]",
                        f"executing move source={cmd_source} x={float(x):.3f} y={float(y):.3f} "
                        f"zoom={float(z):.3f} duration={float(duration_s):.2f}",
                    )
                    self._controller.continuous_move(x=x, y=y, zoom=z, duration_s=duration_s)
                    print("[PTZ_WORKER]", f"done move source={cmd_source}")
            except Exception as e:
                msg = str(e) or e.__class__.__name__
                low = msg.lower()
                if cmd_type == "move" and cmd_source in {"auto", "tracking", "inspection"} and ("out of bounds" in low):
                    # Mantener string/log legado (mismo tag/mensaje).
                    print("[PTZ][WARN] Movimiento automÃ¡tico fuera de rango. Se ignora comando y se envÃ­a STOP.")
                    try:
                        if self._controller is not None:
                            self._controller.stop()
                    except Exception:
                        pass
                    continue
                print(f"[PTZ_WORKER][ERROR] source={cmd_source} error={msg}")
                self._controller = None
