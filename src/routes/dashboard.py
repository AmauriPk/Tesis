from __future__ import annotations

from typing import Any, Callable

from flask import Blueprint, Response, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

dashboard_bp = Blueprint("dashboard", __name__)

_deps: dict[str, Any] = {}
_routes_initialized = False


def init_dashboard_routes(**deps: Any) -> None:
    """
    Inicializa dependencias y registra rutas del dashboard operador en el Blueprint.

    Evita imports circulares con `app.py` al recibir referencias explícitas.
    """
    global _deps, _routes_initialized
    _deps = dict(deps or {})

    if _routes_initialized:
        return
    _routes_initialized = True

    role_required = _deps["role_required"]
    state_lock = _deps["state_lock"]
    current_detection_state = _deps["current_detection_state"]

    get_live_processor: Callable[[], Any] = _deps["get_live_processor"]
    get_live_reader: Callable[[], Any] = _deps["get_live_reader"]

    get_or_create_camera_config = _deps["get_or_create_camera_config"]
    leer_config_camara = _deps["leer_config_camara"]
    get_configured_camera_type = _deps["get_configured_camera_type"]

    @dashboard_bp.route("/", endpoint="index")
    @login_required
    def index():
        """Dashboard principal (manual + live). Operador-only por regla de negocio."""
        if current_user.role == "admin":
            return redirect(url_for("admin_camera.admin_dashboard"))
        _ = get_or_create_camera_config()
        # Fuente de verdad: config_camara.json (evita sobrescrituras por DB / memoria volátil).
        is_ptz = bool(leer_config_camara())
        camera_type_str = "ptz" if is_ptz else "fixed"
        active_tab = (request.args.get("tab") or "").strip().lower() or "live"
        if active_tab not in {"live", "manual"}:
            active_tab = "live"
        return render_template(
            "index.html",
            is_admin=(current_user.role == "admin"),
            camera_type=camera_type_str,
            current_user=current_user,
            active_tab=active_tab,
        )

    @dashboard_bp.route("/video_feed", endpoint="video_feed")
    @login_required
    @role_required("operator")
    def video_feed():
        """Entrega el stream MJPEG anotado."""
        live_processor = get_live_processor()
        return Response(
            live_processor.mjpeg_generator(),
            mimetype="multipart/x-mixed-replace; boundary=frame",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache"},
        )

    @dashboard_bp.route("/detection_status", endpoint="detection_status")
    @login_required
    @role_required("operator")
    def detection_status():
        """Estado resumido (para badge/UI)."""
        with state_lock:
            return jsonify(dict(current_detection_state))

    @dashboard_bp.get("/api/camera_status", endpoint="camera_status")
    @login_required
    @role_required("operator")
    def camera_status():
        """Expone si el hardware soporta PTZ (resultado de Auto-Discovery ONVIF)."""
        ct = get_configured_camera_type()
        rtsp_status = {}
        live_reader = get_live_reader()
        try:
            rtsp_status = dict(live_reader.get_status() or {})
        except Exception:
            rtsp_status = {"error": "rtsp_status_unavailable"}
        try:
            age = rtsp_status.get("last_frame_age_s")
            rtsp_status["stale_over_5s"] = (age is None) or (float(age) > 5.0)
        except Exception:
            rtsp_status["stale_over_5s"] = True
        return (
            jsonify(
                {
                    "status": "ok",
                    "camera_type": ct,
                    "configured_is_ptz": (ct == "ptz"),
                    "rtsp": rtsp_status,
                }
            ),
            200,
        )

