"""
Módulo      : ptz_service.py
Rol         : Estado centralizado de automatización PTZ y capacidad de hardware.
              PTZStateService guarda flags (auto_tracking, inspection_mode) y
              el objetivo de tracking con locks. PTZCapabilityService gestiona
              el autodescubrimiento ONVIF y expone los predicados de readiness.
Conectado con: config.py (ONVIF_CONFIG, SECURITY_CONFIG),
              src/services/camera_state_service.py (is_camera_configured_ptz).
Usado por   : app.py (instancia ambos servicios al arranque y los pasa a workers
              y routes), src/services/tracking_worker_service.py,
              src/services/inspection_patrol_service.py, src/routes/automation.py.
Hilos       : state_lock (RLock) y tracking_target_lock (Lock) protegen el estado
              compartido accedido simultáneamente por el hilo de video, los workers
              PTZ y los request handlers de Flask.
Base de datos: No accede a DB directamente.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Callable

from config import ONVIF_CONFIG

logger = logging.getLogger(__name__)


class PTZStateService:
    """
    Estado centralizado de automatización PTZ (flags + objetivo de tracking).

    Responsabilidad: ser la única fuente de verdad para auto_tracking_enabled,
                     inspection_mode_enabled y el último bounding box del objetivo.
                     NO controla el PTZ — eso es responsabilidad de PTZCommandWorker.
    Ciclo de vida  : instanciado una vez en app.py; nunca se recrea.
    Atributos clave: ``state_lock`` (RLock compartido con app.py),
                     ``tracking_target_lock``, ``tracking_target_state`` (dict).
    """

    def __init__(self) -> None:
        self.state_lock = threading.RLock()
        self.tracking_target_lock = threading.Lock()

        self._auto_tracking_enabled = False
        self._inspection_mode_enabled = False

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
        """
        Actualiza el objetivo de tracking con el bbox del último frame confirmado.

        Llamado desde LiveVideoProcessor._run() en cada frame con detección
        confirmada — el TrackingPTZWorker lee este estado para calcular el
        vector de corrección PTZ.

        Args:
            payload: Dict con ``has_target``, ``bbox`` (xyxy), ``frame_w``,
                     ``frame_h``, ``confidence``, ``updated_at``.
        """
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
                    logger.debug(
                        "tracking_target bbox=%s conf=%.3f updated=True",
                        tuple(bbox), float(payload.get('confidence') or 0.0),
                    )
        except Exception as e:
            logger.warning("PTZ state update_tracking_target error: %s", e)

    def get_tracking_target_snapshot(self) -> dict:
        with self.tracking_target_lock:
            return dict(self.tracking_target_state)


class PTZCapabilityService:
    """
    Gestiona la capacidad PTZ descubierta por ONVIF y los predicados de readiness.

    Responsabilidad: separar "la cámara es PTZ según el Admin" (camera_state_service)
                     de "la cámara respondió ONVIF PTZ" (autodescubrimiento). Un
                     sistema es ready-for-automation si cualquiera de los dos es True.
    Ciclo de vida  : instanciado en app.py; ``probe_onvif_ptz_capability()`` se llama
                     en el arranque y después de guardar nueva config de cámara.
    Atributos clave: ``is_ptz_capable`` (resultado del último probe ONVIF),
                     ``camera_source_mode`` ("fixed"|"ptz" — enviado al frontend).
    """

    def __init__(
        self,
        *,
        state_lock: Any,
        current_detection_state: dict,
        is_camera_configured_ptz: Callable[[], bool],
        set_auto_tracking_enabled: Callable[[bool], None],
        set_inspection_mode_enabled: Callable[[bool], None],
        get_or_create_camera_config: Callable[[], Any],
        normalized_onvif_port: Callable[[int | None], int],
    ):
        self.state_lock = state_lock
        self.current_detection_state = current_detection_state
        self.is_camera_configured_ptz = is_camera_configured_ptz
        self.set_auto_tracking_enabled = set_auto_tracking_enabled
        self.set_inspection_mode_enabled = set_inspection_mode_enabled
        self.get_or_create_camera_config = get_or_create_camera_config
        self.normalized_onvif_port = normalized_onvif_port

        self.is_ptz_capable: bool = False
        self.camera_source_mode: str = "fixed"
        self.onvif_last_probe_at: float | None = None
        self.onvif_last_probe_error: str | None = None
        self.last_ptz_ready_automation: bool | None = None
        self.last_ptz_ready_manual: bool | None = None

    def set_ptz_capable(self, value: bool, *, error: str | None = None) -> None:
        from config import SECURITY_CONFIG
        with self.state_lock:
            self.is_ptz_capable = bool(value)
            self.onvif_last_probe_error = error
            configured_ptz = bool(self.is_camera_configured_ptz())
            if (not self.is_ptz_capable) and (not configured_ptz):
                self.set_auto_tracking_enabled(False)
                self.set_inspection_mode_enabled(False)
            self.camera_source_mode = "ptz" if (self.is_ptz_capable or configured_ptz) else "fixed"
            self.current_detection_state["camera_source_mode"] = self.camera_source_mode

    def ptz_discovered_capable(self) -> bool:
        with self.state_lock:
            return bool(self.is_ptz_capable)

    def should_log_ptz_ready(self) -> bool:
        from config import SECURITY_CONFIG
        return bool(SECURITY_CONFIG.get("debug_ptz_ready", False))

    def log_ptz_ready(self, *, kind: str, ready: bool, configured: bool, discovered: bool) -> None:
        if self.should_log_ptz_ready():
            logger.debug("PTZ ready: %s=%s configured=%s discovered=%s", kind, bool(ready), bool(configured), bool(discovered))
            return
        if str(kind) == "automation":
            if self.last_ptz_ready_automation is None or bool(self.last_ptz_ready_automation) != bool(ready):
                self.last_ptz_ready_automation = bool(ready)
                logger.info("PTZ ready: automation=%s configured=%s discovered=%s", bool(ready), bool(configured), bool(discovered))
            return
        if str(kind) == "manual":
            if self.last_ptz_ready_manual is None or bool(self.last_ptz_ready_manual) != bool(ready):
                self.last_ptz_ready_manual = bool(ready)
                logger.info("PTZ ready: manual=%s configured=%s discovered=%s", bool(ready), bool(configured), bool(discovered))
            return

    def is_ptz_ready_for_manual(self) -> bool:
        configured_ptz = bool(self.is_camera_configured_ptz())
        discovered = bool(self.ptz_discovered_capable())
        ready = bool(configured_ptz or discovered)
        self.log_ptz_ready(kind="manual", ready=ready, configured=configured_ptz, discovered=discovered)
        return bool(ready)

    def is_ptz_ready_for_automation(self) -> bool:
        configured_ptz = bool(self.is_camera_configured_ptz())
        discovered = bool(self.ptz_discovered_capable())
        ready = bool(configured_ptz or discovered)
        self.log_ptz_ready(kind="automation", ready=ready, configured=configured_ptz, discovered=discovered)
        return bool(ready)

    def get_camera_source_mode(self) -> str:
        with self.state_lock:
            return str(self.camera_source_mode)

    def probe_onvif_ptz_capability(self) -> bool:
        cfg = self.get_or_create_camera_config()
        host = (getattr(cfg, "onvif_host", None) or "").strip()
        try:
            raw_onvif_port = int(getattr(cfg, "onvif_port", None) or 80)
        except Exception:
            raw_onvif_port = 80
        if raw_onvif_port == ONVIF_CONFIG["rtsp_port"]:
            logger.warning("onvif_port=554 parece RTSP; usando 80 para ONVIF.")
        configured_onvif_port = self.normalized_onvif_port(raw_onvif_port)
        username = (getattr(cfg, "onvif_username", None) or "").strip()
        password = (getattr(cfg, "onvif_password", None) or "").strip()

        self.onvif_last_probe_at = time.time()

        if not host:
            self.set_ptz_capable(False, error="ONVIF host no configurado.")
            return False
        if not username or not password:
            self.set_ptz_capable(False, error="Credenciales ONVIF incompletas.")
            return False

        def _ports_to_try(port: int) -> list[int]:
            common = [80, 8000, 8080]
            if port == ONVIF_CONFIG["rtsp_port"]:
                logger.warning("ONVIF_PORT=554 parece RTSP; se ignorará y se probarán puertos ONVIF comunes.")
                return common
            ports: list[int] = [port]
            for p in common:
                if p not in ports:
                    ports.append(p)
            return ports

        last_error: str | None = None
        for port in _ports_to_try(int(configured_onvif_port)):
            try:
                from onvif import ONVIFCamera  # type: ignore

                cam = ONVIFCamera(host, int(port), username, password)

                try:
                    dev = cam.create_devicemgmt_service()
                    caps = dev.GetCapabilities({"Category": "All"})
                    ptz_caps = getattr(caps, "PTZ", None)
                    xaddr = getattr(ptz_caps, "XAddr", None) if ptz_caps is not None else None
                    if xaddr:
                        self.set_ptz_capable(True, error=None)
                        return True
                except Exception:
                    pass

                try:
                    ptz = cam.create_ptz_service()
                    _ = ptz.GetServiceCapabilities()
                    self.set_ptz_capable(True, error=None)
                    return True
                except Exception as e:
                    last_error = str(e)
            except Exception as e:
                last_error = str(e)

        self.set_ptz_capable(False, error=last_error or "ONVIF/PTZ no disponible.")
        return False
