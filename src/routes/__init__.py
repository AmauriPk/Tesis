"""
Blueprints del sistema de rutas.

Se mantiene minimalista para evitar imports circulares con `app.py`.
"""
from typing import Any


def get_dep(deps: dict[str, Any], key: str) -> Any:
    try:
        return deps[key]
    except KeyError as exc:
        raise RuntimeError(
            f"Dependencia '{key}' no inicializada. "
            "Llamar a init_*_routes() antes de usar este blueprint."
        ) from exc
