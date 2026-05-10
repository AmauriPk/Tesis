from __future__ import annotations

import os
import time
from typing import Any, Callable


class PTZCapabilityService:
    """
    Servicio para manejar:
    - capacidad PTZ descubierta por ONVIF (autodescubrimiento);
    - readiness para PTZ manual / automatización;
    - logs controlados de readiness;
    - estado auxiliar del último probe ONVIF.

    Este servicio NO importa `app.py`. Si `get_or_create_camera_config()` requiere
    `app.app_context()`, debe proporcionarse desde un wrapper externo (en `app.py`).
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
        self.camera_source_mode: str = "fixed"  # fixed | ptz
        self.onvif_last_probe_at: float | None = None
        self.onvif_last_probe_error: str | None = None
        self.last_ptz_ready_automation: bool | None = None
        self.last_ptz_ready_manual: bool | None = None

    def set_ptz_capable(self, value: bool, *, error: str | None = None) -> None:
        """
        Actualiza el estado global de capacidad PTZ.

        Importante:
        - Si el hardware NO es PTZ y tampoco está configurado como PTZ, se deshabilita tracking/inspección.
        - Mantiene el espejo en `current_detection_state["camera_source_mode"]`.
        """
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
        v = (os.environ.get("DEBUG_PTZ_READY") or "").strip().lower()
        return v in {"1", "true", "t", "yes", "y", "on"}

    def log_ptz_ready(self, *, kind: str, ready: bool, configured: bool, discovered: bool) -> None:
        if self.should_log_ptz_ready():
            print("[PTZ_READY]", f"{kind}={bool(ready)} configured={bool(configured)} discovered={bool(discovered)}")
            return
        if str(kind) == "automation":
            if self.last_ptz_ready_automation is None or bool(self.last_ptz_ready_automation) != bool(ready):
                self.last_ptz_ready_automation = bool(ready)
                print("[PTZ_READY]", f"automation={bool(ready)} configured={bool(configured)} discovered={bool(discovered)}")
            return
        if str(kind) == "manual":
            if self.last_ptz_ready_manual is None or bool(self.last_ptz_ready_manual) != bool(ready):
                self.last_ptz_ready_manual = bool(ready)
                print("[PTZ_READY]", f"manual={bool(ready)} configured={bool(configured)} discovered={bool(discovered)}")
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

    def get_onvif_probe_status(self) -> dict:
        with self.state_lock:
            return {
                "last_probe_at": self.onvif_last_probe_at,
                "last_probe_error": self.onvif_last_probe_error,
                "is_ptz_capable": bool(self.is_ptz_capable),
                "camera_source_mode": str(self.camera_source_mode),
            }

    def probe_onvif_ptz_capability(self) -> bool:
        """
        Autodescubre PTZ por ONVIF.
        Asume que si `get_or_create_camera_config()` lo requiere, el caller ya está en app_context.
        """
        cfg = self.get_or_create_camera_config()
        host = (getattr(cfg, "onvif_host", None) or "").strip()
        try:
            raw_onvif_port = int(getattr(cfg, "onvif_port", None) or 80)
        except Exception:
            raw_onvif_port = 80
        if raw_onvif_port == 554:
            print("[ONVIF][WARN] onvif_port=554 parece RTSP; usando 80 para ONVIF.")
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
            if port == 554:
                print("[ONVIF][WARN] ONVIF_PORT=554 parece RTSP; se ignorará y se probarán puertos ONVIF comunes.")
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

                # Opción A: Capabilities
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

                # Opción B: crear PTZ service y pedir capacidades
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

