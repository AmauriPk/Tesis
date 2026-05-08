# Refactor: rutas de parámetros del modelo a Blueprint

Fecha: 2026-05-07

## Qué se movió

Desde `app.py` se extrajo a un Blueprint separado el endpoint administrativo para actualizar parámetros operativos del modelo:

- `POST /api/update_model_params`

Se mantuvieron exactamente la misma URL HTTP, método, validaciones, JSON y permisos (`login_required` + `role_required("admin")`).

## Dónde quedó

- Blueprint: `src/routes/model_params.py`
  - `model_params_bp = Blueprint("model_params", __name__)`
  - `init_model_params_routes(**deps)` para inyección de dependencias y evitar imports circulares con `app.py`.

## Dependencias inyectadas (desde app.py)

`src/routes/model_params.py` no importa `app.py`. En su lugar, `app.py` llama:

- `init_model_params_routes(...)` con:
  - `role_required`
  - `update_model_params` (callable)

Luego registra:
- `app.register_blueprint(model_params_bp)`

## Qué quedó en app.py (por seguridad)

Para evitar cambios de comportamiento y dependencias cruzadas, se mantuvieron en `app.py`:

- `MODEL_PARAMS`, `model_params_lock`
- `get_model_params()`
- `update_model_params(...)` (solo se inyecta al Blueprint)

Esto permite que otros módulos (por ejemplo render de `/admin_dashboard` en `admin_camera`) sigan usando `get_model_params()` sin cambios.

## Nota (url_for y Blueprint)

Al mover el endpoint a Blueprint, el nombre interno para `url_for(...)` cambió a:

- `url_for("model_params.api_update_model_params")`

La URL HTTP sigue siendo:
- `POST /api/update_model_params`

## Cómo probar

1. Arrancar la app:
   - `py app.py`
2. Login con rol `admin`.
3. Abrir `/admin_dashboard` y en la sección de parámetros:
   - mover sliders (confianza/persistencia/IoU)
   - guardar (debe pegar a `POST /api/update_model_params` y responder `200` con `{status: "success", model_params: ...}`).

## Riesgos conocidos

- Si `init_model_params_routes(...)` no se llama antes de registrar el Blueprint, la ruta no queda registrada.
- Si `templates/admin.html` usa `url_for("api_update_model_params")` sin prefijo, puede ocurrir `BuildError`.

