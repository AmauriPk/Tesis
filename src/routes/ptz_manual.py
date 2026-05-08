from __future__ import annotations

from typing import Any, Callable

from flask import Blueprint, jsonify, request
from flask_login import login_required

ptz_manual_bp = Blueprint("ptz_manual", __name__)

_deps: dict[str, Any] = {}
_routes_initialized = False


def init_ptz_manual_routes(**deps: Any) -> None:
    """
    Inicializa dependencias y registra rutas PTZ manual en el Blueprint.

    Evita imports circulares con `app.py` al recibir referencias explícitas.
    """
    global _deps, _routes_initialized
    _deps = dict(deps or {})

    if _routes_initialized:
        return
    _routes_initialized = True

    app = _deps["app"]
    role_required = _deps["role_required"]
    ptz_worker = _deps["ptz_worker"]

    state_lock = _deps["state_lock"]
    tracking_target_lock = _deps["tracking_target_lock"]
    tracking_target_state = _deps["tracking_target_state"]

    is_camera_configured_ptz: Callable[[], bool] = _deps["is_camera_configured_ptz"]
    ptz_discovered_capable: Callable[[], bool] = _deps["ptz_discovered_capable"]
    is_ptz_ready_for_manual: Callable[[], bool] = _deps["is_ptz_ready_for_manual"]

    get_or_create_camera_config = _deps["get_or_create_camera_config"]
    normalized_onvif_port: Callable[[int | None], int] = _deps["normalized_onvif_port"]
    clamp: Callable[[float, float, float], float] = _deps["clamp"]

    get_auto_tracking_enabled: Callable[[], bool] = _deps["get_auto_tracking_enabled"]
    set_auto_tracking_enabled: Callable[[bool], None] = _deps["set_auto_tracking_enabled"]

    @ptz_manual_bp.post("/ptz_move", endpoint="ptz_move")
    @login_required
    @role_required("operator")
    def ptz_move():
        """Movimiento PTZ (joystick) o vector libre; bloqueado si la cámara no es PTZ."""
        configured_ptz = bool(is_camera_configured_ptz())
        ptz_capable = bool(ptz_discovered_capable())
        ready = bool(is_ptz_ready_for_manual())
        print(
            "[PTZ_READY]",
            f"manual={bool(ready)} configured={bool(configured_ptz)} discovered={bool(ptz_capable)}",
        )
        if not ready:
            return (
                jsonify({"ok": False, "error": "PTZ manual bloqueado: la cámara no está configurada como PTZ"}),
                403,
            )
        with app.app_context():
            cfg = get_or_create_camera_config()
            host = (cfg.onvif_host or "").strip()
            username = (cfg.onvif_username or "").strip()
            password = (cfg.onvif_password or "").strip()
            _ = normalized_onvif_port(cfg.onvif_port)

        if not host:
            return jsonify({"ok": False, "error": "ONVIF_HOST no configurado."}), 400
        if not username or not password:
            return jsonify({"ok": False, "error": "Credenciales ONVIF incompletas (ONVIF_USERNAME/ONVIF_PASSWORD)."}), 400
        if int(cfg.onvif_port or 0) == 554:
            print("[ONVIF][WARN] onvif_port=554 parece RTSP; usando 80 para ONVIF.")

        payload = request.get_json(silent=True) or {}
        direction = (payload.get("direction") or "").strip().lower()
        if direction:
            ptz_worker.enqueue_direction(direction)
            return jsonify({"ok": True})

        try:
            x = float(payload.get("x") or 0.0)
            y = float(payload.get("y") or 0.0)
            zoom = float(payload.get("zoom") or 0.0)
            duration_s = float(payload.get("duration_s") or 0.15)
        except Exception:
            return jsonify({"ok": False, "error": "Payload inválido."}), 400

        x = clamp(x, -1.0, 1.0)
        y = clamp(y, -1.0, 1.0)
        zoom = clamp(zoom, -1.0, 1.0)
        duration_s = clamp(duration_s, 0.05, 0.6)
        ptz_worker.enqueue_move(x=x, y=y, zoom=zoom, duration_s=duration_s)
        return jsonify({"ok": True})

    @ptz_manual_bp.post("/api/ptz_stop", endpoint="ptz_stop")
    @login_required
    @role_required("operator")
    def ptz_stop():
        """Stop PTZ; bloqueado si la cámara no es PTZ."""
        configured_ptz = bool(is_camera_configured_ptz())
        ptz_capable = bool(ptz_discovered_capable())
        ready = bool(is_ptz_ready_for_manual())
        print(
            "[PTZ_READY]",
            f"manual={bool(ready)} configured={bool(configured_ptz)} discovered={bool(ptz_capable)}",
        )
        if not ready:
            return (
                jsonify({"ok": False, "error": "PTZ manual bloqueado: la cámara no está configurada como PTZ"}),
                403,
            )
        payload = request.get_json(silent=True) or {}
        source = str(payload.get("source") or "manual").strip().lower() or "manual"
        disable_tracking = bool(payload.get("disable_tracking", True if source == "manual" else False))

        if source == "manual" and bool(disable_tracking):
            with state_lock:
                set_auto_tracking_enabled(False)
            # Invalida el objetivo de tracking para que el worker no reanude inmediatamente.
            with tracking_target_lock:
                tracking_target_state["has_target"] = False
                tracking_target_state["bbox"] = None
                tracking_target_state["updated_at"] = 0.0
        print(
            f"[PTZ_STOP] source={source} disable_tracking={bool(disable_tracking)} auto_tracking={bool(get_auto_tracking_enabled())}"
        )
        ptz_worker.enqueue_stop()
        if source == "manual" and bool(disable_tracking):
            return jsonify(
                {
                    "ok": True,
                    "auto_tracking_enabled": False,
                    "message": "PTZ detenido y seguimiento automático desactivado",
                }
            )
        return jsonify({"ok": True})

