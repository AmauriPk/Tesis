from __future__ import annotations

import os
import os.path
from typing import Any

from flask import Blueprint, abort, current_app, send_file
from flask_login import login_required

from src.routes import get_dep


def _safe_rel_path(rel_path: str) -> str:
    rel = (rel_path or "").replace("\\", "/").lstrip("/")
    if ".." in rel.split("/"):
        raise ValueError("invalid_path")
    return rel


def _safe_join(base_dir: str, rel_path: str) -> str:
    rel = _safe_rel_path(rel_path)
    base = os.path.abspath(base_dir)
    full = os.path.abspath(os.path.join(base, rel))
    if not (full == base or full.startswith(base + os.sep)):
        raise ValueError("invalid_path")
    return full

media_bp = Blueprint("media", __name__)

_deps: dict[str, Any] = {}
_routes_initialized = False


def _get_dep(key: str): return get_dep(_deps, key)


def init_media_routes(**deps: Any) -> None:
    """
    Inicializa dependencias y registra rutas de media en el Blueprint.

    Evita imports circulares con `app.py` al recibir referencias explícitas.
    """
    global _deps, _routes_initialized
    _deps = dict(deps or {})

    if _routes_initialized:
        return
    _routes_initialized = True

    role_required = _get_dep("role_required")

    @media_bp.get("/media/<path:rel_path>", endpoint="media")
    @login_required
    @role_required("operator", "admin")
    def media(rel_path: str):
        """
        Sirve evidencias/frames de manera segura.
        Permite solo archivos dentro de `app.root_path` (bloquea traversal).
        """
        try:
            rel = _safe_rel_path(rel_path)
            full = _safe_join(os.path.abspath(current_app.root_path), rel)
        except Exception:
            abort(400)
        if not os.path.exists(full) or not os.path.isfile(full):
            abort(404)
        return send_file(full)

