"""
Módulo      : camera_config_service.py
Rol         : Operaciones CRUD sobre CameraConfig (tabla ``camera_config`` en app.db).
              Normaliza valores ONVIF desde variables de entorno y maneja el
              singleton de configuración de cámara.
Conectado con: src/system_core.py (CameraConfig, db — inyectados en __init__),
              config.py (RTSP_CONFIG, ONVIF_CONFIG — inyectados en __init__).
Usado por   : app.py (instancia camera_config_service al arranque),
              src/routes/admin_camera.py, src/routes/ptz_manual.py.
Hilos       : Ninguno propio — llamado desde request handlers de Flask (threaded).
Base de datos: app.db (SQLAlchemy vía self.db.session).
"""
from __future__ import annotations

from typing import Any


class CameraConfigService:
    """
    Servicio para gestionar la configuración persistida de cámara en app.db.

    Responsabilidad: proveer CRUD sobre CameraConfig (singleton), normalizar
                     puertos ONVIF y rellenar valores faltantes desde env.
    Ciclo de vida  : instanciado una vez en app.py al arranque; sus métodos son
                     invocados en cada request que necesite la config de cámara.
    Nota           : NO gestiona ``config_camara.json`` (eso vive en camera_state_service).

    Atributos:
        db: Instancia SQLAlchemy inyectada (evita import circular con app.py).
        CameraConfig: Clase del modelo inyectada (misma razón).
        rtsp_config: Diccionario RTSP_CONFIG de config.py.
        onvif_config: Diccionario ONVIF_CONFIG de config.py.
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
        """
        Obtiene el registro singleton CameraConfig o lo crea si no existe.

        Al crear, precarga URL/credenciales RTSP y ONVIF desde las variables
        de entorno — permite arrancar el sistema con configuración mínima sin
        necesidad de pasar por el panel Admin.

        Returns:
            Instancia CameraConfig con campos sincronizados desde env.
        """
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

