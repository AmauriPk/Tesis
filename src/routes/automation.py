from __future__ import annotations

from typing import Any, Callable

from flask import Blueprint, jsonify, request
from flask_login import login_required

automation_bp = Blueprint("automation", __name__)

_deps: dict[str, Any] = {}
_routes_initialized = False


def init_automation_routes(**deps: Any) -> None:
    """
    Inicializa dependencias y registra rutas de automatización (tracking/inspección).

    Evita imports circulares con `app.py` al recibir referencias explícitas.
    """
    global _deps, _routes_initialized
    _deps = dict(deps or {})

    if _routes_initialized:
        return
    _routes_initialized = True

    role_required = _deps["role_required"]
    state_lock = _deps["state_lock"]
    ptz_worker = _deps["ptz_worker"]

    is_ptz_ready_for_automation: Callable[[], bool] = _deps["is_ptz_ready_for_automation"]

    get_auto_tracking_enabled: Callable[[], bool] = _deps["get_auto_tracking_enabled"]
    set_auto_tracking_enabled: Callable[[bool], None] = _deps["set_auto_tracking_enabled"]

    get_inspection_mode_enabled: Callable[[], bool] = _deps["get_inspection_mode_enabled"]
    set_inspection_mode_enabled: Callable[[bool], None] = _deps["set_inspection_mode_enabled"]

    @automation_bp.route("/api/auto_tracking", methods=["GET", "POST"])
    @login_required
    @role_required("operator")
    def api_auto_tracking():
        """Lee o actualiza el flag de tracking automático (solo efectivo si el hardware es PTZ)."""
        if request.method == "GET":
            with state_lock:
                return jsonify({"enabled": bool(get_auto_tracking_enabled())})

        payload = {}
        try:
            payload = request.get_json(silent=True) or {}
        except Exception:
            payload = {}

        enabled = payload.get("enabled", None)
        if enabled is None:
            enabled_txt = (request.form.get("enabled") or "").strip().lower()
            enabled = enabled_txt in {"1", "true", "t", "yes", "y", "on"}

        ready_auto = bool(is_ptz_ready_for_automation())
        with state_lock:
            set_auto_tracking_enabled(bool(enabled) and bool(ready_auto))
            disabled = not bool(enabled)
        if disabled:
            ptz_worker.enqueue_stop()
        with state_lock:
            return jsonify({"enabled": bool(get_auto_tracking_enabled())})

    @automation_bp.route("/api/inspection_mode", methods=["GET", "POST"])
    @login_required
    @role_required("operator")
    def api_inspection_mode():
        """Lee o actualiza el modo de inspección/patrullaje automático (solo efectivo si PTZ)."""
        if request.method == "GET":
            with state_lock:
                return jsonify({"enabled": bool(get_inspection_mode_enabled())})

        payload = request.get_json(silent=True) or {}
        enabled = bool(payload.get("enabled"))

        ready_auto = bool(is_ptz_ready_for_automation())
        with state_lock:
            if enabled:
                set_inspection_mode_enabled(bool(enabled) and bool(ready_auto))
                # Al habilitar inspección, garantizar que el tracking esté listo para intervenir.
                # (Desacoplado) No tocar auto_tracking aquí.
            else:
                set_inspection_mode_enabled(False)
                # (Desacoplado) No tocar auto_tracking aquí.

            disabled = not bool(enabled)

        if disabled:
            ptz_worker.enqueue_stop()

        with state_lock:
            return jsonify({"enabled": bool(get_inspection_mode_enabled())})

