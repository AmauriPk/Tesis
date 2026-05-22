from __future__ import annotations

import sqlite3
from typing import Any, Callable

from flask import Blueprint, Response, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from config import STORAGE_CONFIG
from src.routes import get_dep

dashboard_bp = Blueprint("dashboard", __name__)

_deps: dict[str, Any] = {}
_routes_initialized = False


def _get_dep(key: str): return get_dep(_deps, key)


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

    role_required = _get_dep("role_required")
    state_lock = _get_dep("state_lock")
    current_detection_state = _get_dep("current_detection_state")

    get_live_processor: Callable[[], Any] = _get_dep("get_live_processor")
    get_live_reader: Callable[[], Any] = _get_dep("get_live_reader")
    get_tracking_worker: Callable[[], Any] = _deps.get("get_tracking_worker") or (lambda: None)

    get_or_create_camera_config = _get_dep("get_or_create_camera_config")
    leer_config_camara = _get_dep("leer_config_camara")
    get_configured_camera_type = _get_dep("get_configured_camera_type")

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

    @dashboard_bp.get("/api/live_metrics", endpoint="live_metrics")
    @login_required
    @role_required("operator")
    def live_metrics():
        """Métricas en tiempo real del procesador de video."""
        processor = get_live_processor()
        try:
            data = processor.get_metrics()
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500
        try:
            worker = get_tracking_worker()
            if worker is not None:
                data.update(worker.get_reacq_state())
        except Exception:
            pass
        return jsonify(data), 200

    @dashboard_bp.get("/api/historical_metrics", endpoint="historical_metrics")
    @login_required
    @role_required("operator")
    def historical_metrics():
        """Agrega las últimas 100 filas de inference_frames para métricas históricas."""
        db_path = str(STORAGE_CONFIG.get("db_path", "detections.db"))
        try:
            con = sqlite3.connect(db_path, timeout=5, check_same_thread=False)
            con.row_factory = sqlite3.Row
            rows = con.execute(
                """
                SELECT inference_ms, detections_count, confirmed
                FROM inference_frames
                ORDER BY id DESC
                LIMIT 100
                """
            ).fetchall()
            con.close()
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

        if not rows:
            return jsonify({
                "sample_count": 0,
                "inference_ms_avg": 0.0,
                "inference_ms_p95": 0.0,
                "detection_rate": 0.0,
                "confirmed_count": 0,
            }), 200

        ms_vals = [float(r["inference_ms"]) for r in rows if r["inference_ms"] is not None]
        det_vals = [int(r["detections_count"] or 0) for r in rows]
        confirmed_vals = [int(r["confirmed"] or 0) for r in rows]

        ms_sorted = sorted(ms_vals)
        p95_idx = max(0, int(len(ms_sorted) * 0.95) - 1)

        return jsonify({
            "sample_count": len(rows),
            "inference_ms_avg": round(sum(ms_vals) / len(ms_vals), 2) if ms_vals else 0.0,
            "inference_ms_p95": round(ms_sorted[p95_idx], 2) if ms_sorted else 0.0,
            "detection_rate": round(sum(1 for d in det_vals if d > 0) / len(det_vals), 3) if det_vals else 0.0,
            "confirmed_count": sum(confirmed_vals),
        }), 200

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
