from __future__ import annotations

from typing import Any


class CameraConfigService:
    """
    Servicio para manejar configuración persistida de cámara (DB) vía `CameraConfig`.

    Nota: esto NO maneja `config_camara.json` (eso vive en `camera_state_service`).
    """

    def __init__(self, *, db: Any, CameraConfig: Any, rtsp_config: dict, onvif_config: dict):
        self.db = db
        self.CameraConfig = CameraConfig
        self.rtsp_config = dict(rtsp_config or {})
        self.onvif_config = dict(onvif_config or {})

    def sync_onvif_config_from_env(self, cfg: Any) -> Any:
        """
        Completa configuración ONVIF desde variables/config si está vacía.

        Regla: no sobreescribe valores ya persistidos en DB.
        Mantiene el mismo comportamiento que `app.py`.
        """
        changed = False

        host = (self.onvif_config.get("host") or "").strip()
        username = (self.onvif_config.get("username") or "").strip()
        password = (self.onvif_config.get("password") or "").strip()

        try:
            port_env = int(self.onvif_config.get("port") or 80)
        except Exception:
            port_env = 80

        if not (getattr(cfg, "onvif_host", "") or "").strip() and host:
            cfg.onvif_host = host
            changed = True
        if not (getattr(cfg, "onvif_username", "") or "").strip() and username:
            cfg.onvif_username = username
            changed = True
        if not (getattr(cfg, "onvif_password", "") or "").strip() and password:
            cfg.onvif_password = password
            changed = True
        if not getattr(cfg, "onvif_port", None):
            cfg.onvif_port = int(port_env or 80)
            changed = True

        if changed:
            self.db.session.commit()
        return cfg

    def normalized_onvif_port(self, port: int | None) -> int:
        """Normaliza el puerto ONVIF, evitando el puerto RTSP (554)."""
        try:
            p = int(port or 80)
        except Exception:
            p = 80
        if p == 554:
            return 80
        return p

    def get_or_create_camera_config(self) -> Any:
        """Obtiene o inicializa el registro singleton con configuración RTSP/ONVIF."""
        cfg = self.CameraConfig.query.order_by(self.CameraConfig.id.asc()).first()
        if cfg:
            return self.sync_onvif_config_from_env(cfg)

        cfg = self.CameraConfig(
            camera_type="fixed",
            rtsp_url=self.rtsp_config.get("url"),
            rtsp_username=self.rtsp_config.get("username"),
            rtsp_password=self.rtsp_config.get("password"),
            onvif_host=(self.onvif_config.get("host") or "").strip() or None,
            onvif_port=int(self.onvif_config.get("port") or 80),
            onvif_username=(self.onvif_config.get("username") or "").strip() or None,
            onvif_password=(self.onvif_config.get("password") or "").strip() or None,
        )
        self.db.session.add(cfg)
        self.db.session.commit()
        return cfg

