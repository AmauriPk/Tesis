from __future__ import annotations

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_CAMERA_ROOT_PATH: Optional[str] = None
_last_camera_cfg_is_ptz: Optional[bool] = None


def init_camera_state_service(*, root_path: str) -> None:
    """
    Inicializa el servicio de estado de cámara con la raíz de la app.

    Args:
        root_path: equivalente a `app.root_path`.
    """
    global _CAMERA_ROOT_PATH
    _CAMERA_ROOT_PATH = str(root_path or "")


def _require_root_path() -> str:
    root = (_CAMERA_ROOT_PATH or "").strip()
    if not root:
        raise RuntimeError("camera_state_service_not_initialized")
    return root


def _camera_cfg_path() -> str:
    """
    Construye la ruta absoluta del archivo de configuración de cámara.

    Returns:
        Ruta absoluta a `config_camara.json` dentro del `root_path` inicializado.
    """
    return os.path.join(_require_root_path(), "config_camara.json")


def guardar_config_camara(is_ptz: bool) -> None:
    """Persiste en disco si la cámara está configurada como PTZ o Fija."""
    path = _camera_cfg_path()
    tmp = f"{path}.tmp"
    payload = {"is_ptz": bool(is_ptz)}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def leer_config_camara() -> bool:
    """Lee `config_camara.json` y retorna is_ptz. Si no existe, False."""
    path = _camera_cfg_path()
    debug = os.environ.get("DEBUG_CAMERA_CFG", "").strip().lower() in {"1", "true", "t", "yes", "y", "on"}
    global _last_camera_cfg_is_ptz
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        value = bool(data.get("is_ptz", False))
        if debug or (_last_camera_cfg_is_ptz is None) or (bool(_last_camera_cfg_is_ptz) != bool(value)):
            logger.debug("camera_cfg read %s -> is_ptz=%s", path, value)
        _last_camera_cfg_is_ptz = bool(value)
        return value
    except FileNotFoundError:
        logger.debug("camera_cfg read %s -> MISSING (default False)", path)
        return False
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.warning("camera_cfg read %s -> PARSE ERROR: %s (default False)", path, e)
        # Fail-safe: ante corrupciones/parcial, asumir fija.
        return False


def get_configured_camera_type() -> str:
    """
    Obtiene el tipo de cámara configurado por el administrador.

    La fuente de verdad es el archivo JSON persistente (`config_camara.json`).

    Returns:
        `"ptz"` si la configuración persistida indica PTZ; en caso contrario `"fixed"`.
    """
    return "ptz" if leer_config_camara() else "fixed"


def set_configured_camera_type(camera_type: str) -> str:
    """
    Normaliza y persiste el tipo de cámara configurado por el administrador.

    Args:
        camera_type: Tipo solicitado (`"fixed"` o `"ptz"`). Cualquier otro valor se normaliza a `"fixed"`.

    Returns:
        El tipo normalizado que se terminó persistiendo (`"fixed"` o `"ptz"`).
    """
    ct = (camera_type or "fixed").strip().lower()
    if ct not in {"fixed", "ptz"}:
        ct = "fixed"
    # Persistir en disco (lo que realmente usan threads/UI).
    try:
        guardar_config_camara(ct == "ptz")
    except Exception as e:
        logger.warning("camera_cfg guardar_config failed: %s", e)
    return ct


def is_camera_configured_ptz() -> bool:
    """
    Indica si la cámara está configurada como PTZ en disco.

    Returns:
        True si el administrador dejó configurado PTZ (persistido); de lo contrario False.
    """
    return bool(leer_config_camara())

