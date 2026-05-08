from __future__ import annotations

from typing import Any, Callable

from flask import Blueprint, jsonify, request
from flask_login import login_required

model_params_bp = Blueprint("model_params", __name__)

_deps: dict[str, Any] = {}
_routes_initialized = False


def _get_dep(key: str):
    try:
        return _deps[key]
    except KeyError as exc:
        raise RuntimeError(f"Dependencia faltante en model_params: {key}") from exc


def init_model_params_routes(**deps: Any) -> None:
    """
    Inicializa dependencias y registra rutas de parámetros del modelo.

    Evita imports circulares con `app.py` al recibir referencias explícitas.
    """
    global _deps, _routes_initialized
    _deps = dict(deps or {})

    if _routes_initialized:
        return
    _routes_initialized = True

    role_required = _get_dep("role_required")
    update_model_params: Callable[..., dict] = _get_dep("update_model_params")

    @model_params_bp.post("/api/update_model_params")
    @login_required
    @role_required("admin")
    def api_update_model_params():
        """
        Actualiza parámetros operativos del modelo en caliente.
        Body JSON esperado:
          - confidence_threshold: float [0.10, 1.00]
          - persistence_frames: int [1, 10]
          - iou_threshold: float [0.10, 1.00]
        """
        payload = request.get_json(silent=True) or {}
        if not payload:
            payload = request.form.to_dict(flat=True)

        try:
            conf = float(payload.get("confidence_threshold"))
            iou = float(payload.get("iou_threshold"))
            persistence = int(payload.get("persistence_frames"))
        except Exception:
            return jsonify({"status": "error", "message": "Parámetros inválidos (tipos)."}), 400

        if not (0.10 <= conf <= 1.00):
            return jsonify({"status": "error", "message": "CONFIDENCE_THRESHOLD fuera de rango (0.10 - 1.00)."}), 400
        if not (0.10 <= iou <= 1.00):
            return jsonify({"status": "error", "message": "IOU_THRESHOLD fuera de rango (0.10 - 1.00)."}), 400
        if not (1 <= persistence <= 10):
            return jsonify({"status": "error", "message": "PERSISTENCE_FRAMES fuera de rango (1 - 10)."}), 400

        updated = update_model_params(confidence_threshold=conf, persistence_frames=persistence, iou_threshold=iou)
        return jsonify({"status": "success", "model_params": updated}), 200
