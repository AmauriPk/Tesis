"""
Módulo      : src/routes/media.py
Rol         : Blueprint de servido de archivos multimedia (evidencias, frames).
              Previene path traversal con ``_safe_join()`` / ``_safe_rel_path()``
              que aseguran que la ruta resultante quede dentro de ``app.root_path``.
Conectado con: Flask (send_file, abort), src/routes/__init__.py (get_dep).
Usado por   : app.py (registra media_bp; init_media_routes(**deps)).
Hilos       : Ninguno — solo I/O de archivo síncrono en el hilo del request.
Base de datos: No accede a ninguna DB.
"""
from __future__ import annotations

import os
import os.path
from typing import Any

from flask import Blueprint, abort, current_app, send_file
from flask_login import login_required

from src.routes import get_dep


def _safe_rel_path(rel_path: str) -> str:
    """
    Normaliza y valida una ruta relativa para prevenir path traversal.

    Convierte separadores a ``/``, elimina el slash inicial y rechaza
    cualquier segmento ``".."`` en la ruta.

    Args:
        rel_path: Ruta relativa proporcionada por el cliente (p.ej. query param).

    Returns:
        Ruta relativa normalizada (sin slash inicial, sin ``..``).

    Raises:
        ValueError: Si la ruta contiene segmentos ``".."``.
    """
    rel = (rel_path or "").replace("\\", "/").lstrip("/")
    if ".." in rel.split("/"):
        raise ValueError("invalid_path")
    return rel


def _safe_join(base_dir: str, rel_path: str) -> str:
    """
    Une ``base_dir`` con ``rel_path`` y verifica que el resultado esté dentro de la base.

    Doble defensa contra path traversal:
    1. ``_safe_rel_path`` rechaza segmentos ``".."``.
    2. ``os.path.abspath`` resuelve symlinks/puntos y se compara con la base.

    Args:
        base_dir: Directorio raíz permitido (p.ej. ``app.root_path``).
        rel_path: Ruta relativa proporcionada por el cliente.

    Returns:
        Ruta absoluta validada dentro de ``base_dir``.

    Raises:
        ValueError: Si la ruta resultante escapa de ``base_dir``.
    """
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

