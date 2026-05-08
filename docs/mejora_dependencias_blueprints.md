# Mejora: validación de dependencias en Blueprints — SIRAN

Fecha: 2026-05-08

## Qué se cambió

En cada Blueprint de `src/routes/*.py` se agregó un helper interno:

- `_get_dep(key: str)`
  - Obtiene dependencias desde `_deps`.
  - Si falta una clave, levanta `RuntimeError` con un mensaje claro indicando:
    - el módulo/Blueprint afectado, y
    - la dependencia faltante.

Además, se reemplazaron los accesos directos de:
- `_deps["clave"]`

por:
- `_get_dep("clave")`

## Por qué ayuda

Cuando falta una dependencia en `init_*_routes(...)`, antes el error típico era un `KeyError` poco descriptivo.

Ahora el fallo es explícito y accionable, por ejemplo:
- `RuntimeError: Dependencia faltante en automation: ptz_worker`

Esto acelera diagnóstico sin cambiar lógica ni endpoints.

## Blueprints cubiertos

- `src/routes/analysis.py`
- `src/routes/events.py`
- `src/routes/dataset.py`
- `src/routes/admin_camera.py`
- `src/routes/auth.py`
- `src/routes/dashboard.py`
- `src/routes/model_params.py`
- `src/routes/ptz_manual.py`
- `src/routes/automation.py`

## Cómo probar

Compilación (sin ejecutar Flask):
- `py -m py_compile app.py src/system_core.py src/video_processor.py`
- y compilar también `src/routes/*.py` + `src/services/*.py` (en Windows se validó con un script que expande glob).

Pruebas funcionales recomendadas:
1. `py app.py`
2. Login operador → dashboard → video_feed.
3. PTZ manual (mover + stop).
4. Tracking automático (activar/desactivar).
5. Inspección automática (activar/desactivar).
6. Login admin → `admin_dashboard`.

## Nota

Este cambio no altera comportamiento en runtime normal: solo mejora el mensaje cuando falta una dependencia.

