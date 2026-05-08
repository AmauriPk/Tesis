# Refactor: `model_params_service` (parámetros operativos del modelo)

## Qué se movió

Desde `app.py` hacia `src/services/model_params_service.py`:

- `MODEL_PARAMS`
- `model_params_lock`
- `get_model_params()`
- `update_model_params()`
- Lectura inicial de:
  - `CONFIDENCE_THRESHOLD`
  - `PERSISTENCE_FRAMES`
  - `IOU_THRESHOLD`
  - `DETECTION_PERSISTENCE_FRAMES` (mitigación de aves)

## Qué quedó en `app.py` (wrappers)

Para mantener compatibilidad con el resto del sistema (Blueprints/servicios que inyectan callables):

- `get_model_params()` sigue existiendo y delega a `model_params_service.get_model_params()`.
- `update_model_params(...)` sigue existiendo y delega a `model_params_service.update_model_params(...)`.
- `MODEL_PARAMS` y `model_params_lock` quedan como aliases apuntando al servicio (`model_params_service.model_params` y `model_params_service.lock`).
- `DETECTION_PERSISTENCE_FRAMES` se mantiene como variable global en `app.py`, y sigue sincronizándose al llamar `update_model_params(...)` (mismo comportamiento previo).

## Parámetros manejados

- `confidence_threshold`
- `persistence_frames`
- `iou_threshold`

## Cómo probar

1. `py app.py`
2. Login admin.
3. Abrir panel de parámetros del modelo.
4. Cambiar `confidence_threshold`, `persistence_frames`, `iou_threshold`.
5. Guardar y verificar respuesta 200 en `/api/update_model_params`.
6. Verificar que el dashboard del operador sigue funcionando y no hay errores en detección en vivo.

## Riesgos conocidos / pendientes

- No se movieron rutas (`src/routes/model_params.py` se mantiene igual).
- No se cambió la validación de rangos que aplica el endpoint (sigue estando en el Blueprint).

