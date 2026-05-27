"""
Módulo      : src/routes/__init__.py
Rol         : Paquete de Blueprints Flask de SIRAN. Expone ``get_dep()``,
              el único helper de inyección de dependencias usado por todos los
              blueprints para recuperar sus dependencias del dict ``_deps`` sin
              necesidad de importar ``app.py`` (evita imports circulares).
Conectado con: Todos los módulos en src/routes/*.py.
Usado por   : app.py (registra los blueprints e inicializa sus rutas).
Hilos       : Ninguno — solo utilidades de setup.
Base de datos: No accede a ninguna DB.
"""
from typing import Any


def get_dep(deps: dict[str, Any], key: str) -> Any:
    """
    Recupera una dependencia inyectada del dict ``_deps`` del blueprint.

    Centraliza el mensaje de error para que sea consistente en todos los blueprints.
    El patrón de inyección evita que los blueprints importen ``app.py`` directamente
    (lo que causaría imports circulares).

    Args:
        deps: Dict de dependencias pasado por ``init_*_routes(**deps)``.
        key:  Nombre de la dependencia a recuperar.

    Returns:
        El objeto inyectado (servicio, callable, flag, etc.).

    Raises:
        RuntimeError: Si ``key`` no está en ``deps`` — indica error de setup en app.py.
    """
    try:
        return deps[key]
    except KeyError as exc:
        raise RuntimeError(
            f"Dependencia '{key}' no inicializada. "
            "Llamar a init_*_routes() antes de usar este blueprint."
        ) from exc
