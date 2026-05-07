# Refactor: rutas dashboard operador a Blueprint

Fecha: 2026-05-07

## Qué se movió

Desde `app.py` se extrajeron a un Blueprint separado las rutas del dashboard del operador y estado en vivo:

- `GET /`
- `GET /video_feed`
- `GET /detection_status`
- `GET /api/camera_status`

Se conservaron exactamente las mismas **URLs HTTP**, métodos, JSON y protecciones (`login_required` + `role_required(...)`).

## Dónde quedó

- Blueprint: `src/routes/dashboard.py`
  - `dashboard_bp = Blueprint("dashboard", __name__)`
  - `init_dashboard_routes(**deps)` para inyección de dependencias y evitar imports circulares con `app.py`.

## Dependencias inyectadas (desde app.py)

`src/routes/dashboard.py` no importa `app.py`. En su lugar, `app.py` llama:

- `init_dashboard_routes(...)` con:
  - `role_required`
  - `state_lock`
  - `current_detection_state`
  - `get_live_processor` (callable que retorna `live_processor`)
  - `get_live_reader` (callable que retorna `live_reader`)
  - `get_or_create_camera_config`
  - `leer_config_camara`
  - `get_configured_camera_type`

Luego registra:
- `app.register_blueprint(dashboard_bp)`

## JSON conservado

- `/detection_status` mantiene el mismo payload (copia de `current_detection_state`).
- `/api/camera_status` mantiene los mismos campos:
  - `status`, `camera_type`, `configured_is_ptz`, `rtsp`.

## Pendiente (PTZ/tracking/inspección)

Este refactor **no** mueve:

- `/ptz_move`
- `/api/ptz_stop`
- `/api/auto_tracking`
- `/api/inspection_mode`
- workers/hilos de tracking e inspección
- PTZ worker

## Nota (url_for y Blueprint)

Al mover `/` al Blueprint, el endpoint interno pasó a `dashboard.index`, por lo que se corrigieron referencias mínimas de `url_for(...)` donde era necesario (sin cambiar URLs).

## Cómo probar

1. Arrancar la app:
   - `py app.py`
2. Login operador:
   - `GET /` carga el dashboard.
3. Probar estado:
   - `GET /detection_status` → `200` y JSON.
   - `GET /api/camera_status` → `200` y JSON.
4. Probar video:
   - `GET /video_feed` → `200` y stream MJPEG (o intenta conectar).

## Riesgos conocidos

- Si `init_dashboard_routes(...)` no se llama antes de registrar el Blueprint, las rutas no quedan registradas.
- Cambios de `url_for(...)` son necesarios cuando se mueve una ruta a Blueprint (cambian nombres internos, no URLs).

