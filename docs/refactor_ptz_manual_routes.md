# Refactor: rutas PTZ manual a Blueprint

Fecha: 2026-05-07

## Qué se movió

Desde `app.py` se extrajeron a un Blueprint separado **solo** las rutas de PTZ manual:

- `POST /ptz_move`
- `POST /api/ptz_stop`

Se mantuvieron exactamente las mismas **URLs HTTP**, métodos, payloads, logs y respuestas JSON.

## Endpoints conservados (sin prefijo)

El Blueprint se registra sin prefijo, por lo que se conservan:

- `POST /ptz_move`
- `POST /api/ptz_stop`

## Dónde quedó

- Blueprint: `src/routes/ptz_manual.py`
  - `ptz_manual_bp = Blueprint("ptz_manual", __name__)`
  - `init_ptz_manual_routes(**deps)` para inyección de dependencias y evitar imports circulares con `app.py`.

## Dependencias inyectadas (desde app.py)

`src/routes/ptz_manual.py` no importa `app.py`. En su lugar, `app.py` llama:

- `init_ptz_manual_routes(...)` con:
  - `app` (para `app.app_context()` como antes)
  - `role_required`
  - `ptz_worker` (se mantiene el mismo worker; no se refactoriza)
  - `state_lock`
  - `tracking_target_lock`, `tracking_target_state`
  - `is_camera_configured_ptz`
  - `ptz_discovered_capable` (callable `_ptz_discovered_capable`)
  - `is_ptz_ready_for_manual`
  - `get_or_create_camera_config`
  - `normalized_onvif_port`
  - `clamp` (callable `_clamp`)
  - `get_auto_tracking_enabled`, `set_auto_tracking_enabled`

Luego registra:
- `app.register_blueprint(ptz_manual_bp)`

## Qué NO se movió (pendiente)

Este refactor **no** mueve ni cambia:

- `/api/auto_tracking`
- `/api/inspection_mode`
- `TrackingPTZWorker`, `InspectionPatrolWorker`, `PTZCommandWorker` y demás workers/hilos
- lógica de tracking automático
- lógica de inspección automática
- estado global completo de PTZ

## Cómo probar PTZ manual

1. Arrancar la app:
   - `py app.py`
2. Login operador.
3. En el dashboard, usar joystick PTZ (usa `POST /ptz_move`).
4. Probar STOP central (usa `POST /api/ptz_stop`):
   - con `disable_tracking=false` no debe apagar tracking
   - con `disable_tracking=true` debe apagar tracking y limpiar objetivo

## Riesgos conocidos

- Si `init_ptz_manual_routes(...)` no se llama antes de registrar el Blueprint, las rutas no quedan registradas.
- El STOP manual depende de poder desactivar `auto_tracking_enabled` y limpiar `tracking_target_state` como antes.

