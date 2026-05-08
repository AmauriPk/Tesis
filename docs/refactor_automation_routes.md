# Refactor: rutas de automatización (tracking / inspección) a Blueprint

Fecha: 2026-05-07

## Qué se movió

Desde `app.py` se extrajeron a un Blueprint separado **solo** los endpoints de control de automatización:

- `GET|POST /api/auto_tracking`
- `GET|POST /api/inspection_mode`

Se mantuvieron exactamente las mismas **URLs HTTP**, métodos, JSON, status codes y permisos (`login_required` + `role_required("operator")`).

## Endpoints conservados (sin prefijo)

El Blueprint se registra sin prefijo, por lo que se conservan:

- `GET|POST /api/auto_tracking`
- `GET|POST /api/inspection_mode`

## Dónde quedó

- Blueprint: `src/routes/automation.py`
  - `automation_bp = Blueprint("automation", __name__)`
  - `init_automation_routes(**deps)` para inyección de dependencias y evitar imports circulares con `app.py`.

## Dependencias inyectadas (desde app.py)

`src/routes/automation.py` no importa `app.py`. En su lugar, `app.py` llama:

- `init_automation_routes(...)` con:
  - `role_required`
  - `state_lock`
  - `ptz_worker` (solo para `enqueue_stop` como antes)
  - `is_ptz_ready_for_automation`
  - `get_auto_tracking_enabled`, `set_auto_tracking_enabled`
  - `get_inspection_mode_enabled`, `set_inspection_mode_enabled`

Además se pasan referencias de estado (`tracking_target_state`, `tracking_target_lock`, `current_detection_state`) para conservar el contexto, aunque estos endpoints solo usan lo necesario.

## Qué NO se movió (pendiente)

Este refactor **no** mueve ni cambia:

- `PTZWorker` / `TrackingPTZWorker` / `InspectionPatrolWorker`
- lógica interna de tracking automático
- lógica interna de inspección automática
- `LiveVideoProcessor`
- `PTZController`
- PTZ manual (`POST /ptz_move`, `POST /api/ptz_stop`)

## Cómo probar

1. Arrancar la app:
   - `py app.py`
2. Login operador.
3. Probar estado:
   - `GET /api/auto_tracking` → `200` `{ enabled: bool }`
   - `GET /api/inspection_mode` → `200` `{ enabled: bool }`
4. Probar activar/desactivar:
   - `POST /api/auto_tracking` con `{ "enabled": true|false }`
   - `POST /api/inspection_mode` con `{ "enabled": true|false }`
5. Verificar en UI:
   - los toggles en `static/dashboard.js` deben seguir funcionando sin cambios (URLs hardcodeadas).

## Riesgos conocidos

- Si `init_automation_routes(...)` no se llama antes de registrar el Blueprint, las rutas no quedan registradas.
- Estos endpoints dependen de setters inyectados (`set_auto_tracking_enabled`, `set_inspection_mode_enabled`) para mantener el mismo comportamiento de flags globales.

