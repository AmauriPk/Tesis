from __future__ import annotations

import time


class PTZController:
    """
    Controlador PTZ vía ONVIF.

    Nota: esta implementación intenta usar `onvif-zeep` si está instalado.
    Si no, funciona como stub para no romper el sistema (útil en entornos sin ONVIF).
    """

    def __init__(self, host: str, port: int = 80, username: str | None = None, password: str | None = None):
        """Crea un controlador PTZ con parámetros ONVIF."""
        self.host = host
        self.port = port
        self.username = username or ""
        self.password = password or ""
        self._ptz = None
        self._media = None
        self._profile = None

    def connect(self) -> None:
        """Conecta a la cámara ONVIF y resuelve el perfil por defecto."""
        try:
            from onvif import ONVIFCamera  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError("Dependencia ONVIF no instalada. Instala `onvif-zeep`.") from e

        cam = ONVIFCamera(self.host, self.port, self.username, self.password)
        self._media = cam.create_media_service()
        self._ptz = cam.create_ptz_service()
        profiles = self._media.GetProfiles()
        if not profiles:
            raise RuntimeError("No se encontraron perfiles ONVIF.")
        self._profile = profiles[0]

    def test_connection(self) -> dict:
        """Prueba de conectividad ONVIF: retorna `ok` y latencia aproximada (ms)."""
        start = time.time()
        self.connect()
        elapsed_ms = int((time.time() - start) * 1000)
        return {"ok": True, "elapsed_ms": elapsed_ms}

    def continuous_move(self, x: float = 0.0, y: float = 0.0, zoom: float = 0.0, duration_s: float = 0.2) -> None:
        """Realiza un movimiento continuo y luego envía `Stop` tras `duration_s`."""
        if not self._ptz or not self._profile:
            self.connect()
        req = self._ptz.create_type("ContinuousMove")
        req.ProfileToken = self._profile.token
        req.Velocity = {"PanTilt": {"x": float(x), "y": float(y)}, "Zoom": {"x": float(zoom)}}
        self._ptz.ContinuousMove(req)
        time.sleep(max(0.05, float(duration_s)))
        self.stop()

    def stop(self) -> None:
        """Detiene pan/tilt y zoom (si hay sesión PTZ activa)."""
        if not self._ptz or not self._profile:
            return
        req = self._ptz.create_type("Stop")
        req.ProfileToken = self._profile.token
        req.PanTilt = True
        req.Zoom = True
        self._ptz.Stop(req)
