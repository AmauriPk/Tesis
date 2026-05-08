from __future__ import annotations

import os


def safe_rel_path(rel_path: str) -> str:
    """
    Normaliza un path relativo y bloquea traversal básico.

    Args:
        rel_path: Path relativo recibido desde request.

    Returns:
        Path relativo normalizado (separador `/` y sin prefijo `/`).

    Raises:
        ValueError: Si el path intenta traversal (contiene `..`).
    """
    rel = (rel_path or "").replace("\\", "/").lstrip("/")
    if ".." in rel.split("/"):
        raise ValueError("invalid_path")
    return rel


def safe_join(base_dir: str, rel_path: str) -> str:
    """
    Hace join seguro `base_dir` + `rel_path` bloqueando path traversal.

    Args:
        base_dir: Directorio base permitido.
        rel_path: Path relativo proporcionado por el usuario.

    Returns:
        Ruta absoluta dentro de `base_dir`.

    Raises:
        ValueError: Si el path resultante escapa de `base_dir`.
    """
    rel = safe_rel_path(rel_path)
    base = os.path.abspath(base_dir)
    full = os.path.abspath(os.path.join(base, rel))
    if not (full == base or full.startswith(base + os.sep)):
        raise ValueError("invalid_path")
    return full

