# Refactor: rutas admin de cámara (RTSP/ONVIF) a Blueprint

Fecha: 2026-05-07

## Qué se movió

Desde `app.py` se extrajeron a un Blueprint separado las rutas y helpers **administrativos** relacionados con configuración y pruebas de cámara (RTSP/ONVIF).

Se conservaron las mismas **URLs HTTP**, métodos y permisos (`login_required` + `role_required("admin")`).

## Endpoints conservados (URLs sin cambios)

El Blueprint se registra **sin prefijo**, por lo que se conservan:

- `GET /admin_dashboard`
- `GET|POST /admin/camera`
- `POST /admin/camera/test`
- `POST /api/test_connection`

## Dónde quedó

- Blueprint: `src/routes/admin_camera.py`
  - `admin_camera_bp = Blueprint("admin_camera", __name__)`
  - `init_admin_camera_routes(**deps)` para inyección de dependencias y evitar imports circulares con `app.py`.

## Nota importante (url_for y Blueprints)

Al mover rutas a Blueprint, los nombres internos para `url_for(...)` cambian a `admin_camera.<endpoint>`, aunque las **URLs HTTP** se conservan.

Ejemplos:
- `url_for("admin_dashboard")` -> `url_for("admin_camera.admin_dashboard")`
- `url_for("admin_camera")` -> `url_for("admin_camera.admin_camera")`
- `url_for("api_test_connection")` -> `url_for("admin_camera.api_test_connection")`

Por eso se ajustaron las referencias en templates (sin cambiar HTML/JS fuera de `url_for`).

## Dependencias inyectadas (desde app.py)

`src/routes/admin_camera.py` no importa `app.py`. En su lugar, `app.py` llama:

- `init_admin_camera_routes(...)` con:
  - `role_required`
  - `db`
  - `get_or_create_camera_config`
  - `guardar_config_camara`
  - `normalized_onvif_port`
  - `PTZController`
  - `probe_onvif_ptz_capability`
  - `get_model_params`

Luego registra:
- `app.register_blueprint(admin_camera_bp)`

## Helpers movidos

Movidos a `src/routes/admin_camera.py` por ser exclusivos de pruebas admin:

- `_humanize_onvif_error`
- `_detect_ptz_capability`
- `_build_rtsp_url`
- `_grab_rtsp_snapshot_b64`

## Funciones compartidas que quedaron en app.py

Se mantuvieron en `app.py` por ser compartidas con otros flujos (PTZ/video/tracking/inspección) o por reducir riesgo:

- `_probe_onvif_ptz_capability` (inyectada al Blueprint)
- `get_or_create_camera_config`, `guardar_config_camara`, `_normalized_onvif_port` (inyectadas al Blueprint)

No se movieron endpoints de PTZ manual:
- `/ptz_move`
- `/api/ptz_stop`

## Cómo probar (RTSP/ONVIF y tipo PTZ/fija)

1. Arrancar la app:
   - `py app.py`
2. Login con rol `admin`.
3. Verificar:
   - `GET /admin_dashboard` carga sin 500.
4. Guardar configuración:
   - en el formulario de cámara (RTSP/ONVIF) guardar y confirmar redirección a `/admin_dashboard`.
5. Test conexión:
   - desde UI (usa `POST /api/test_connection`) debe devolver `status=success` o `status=error` con `message` controlado.
6. Cambiar fija/PTZ:
   - cambiar `camera_type` y confirmar persistencia (incluye actualización de `config_camara.json` como antes).

## Riesgos conocidos

- Si `init_admin_camera_routes(...)` no se llama antes de registrar el Blueprint, las rutas no quedan registradas.
- Cualquier referencia antigua a `url_for("admin_dashboard")`/`url_for("admin_camera")`/`url_for("api_test_connection")` debe usar el prefijo `admin_camera.`.

## Pendiente

- Refactor posterior (si se desea): mover lógica compartida de configuración a un servicio dedicado, sin tocar endpoints.

