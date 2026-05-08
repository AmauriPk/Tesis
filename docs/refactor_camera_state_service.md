# Refactor: servicio de estado de cámara/PTZ

Fecha: 2026-05-07

## Qué se movió

Desde `app.py` se extrajeron a un servicio dedicado las funciones de configuración persistida de cámara (archivo `config_camara.json`):

- `_camera_cfg_path`
- `guardar_config_camara(is_ptz: bool)`
- `leer_config_camara() -> bool`
- `get_configured_camera_type() -> str`
- `set_configured_camera_type(camera_type: str) -> str`
- `is_camera_configured_ptz() -> bool`

## Dónde quedó

- Servicio: `src/services/camera_state_service.py`
  - Requiere inicialización: `init_camera_state_service(root_path=app.root_path)`

## Cambios en app.py

- `app.py` ahora importa esas funciones desde `src/services/camera_state_service`.
- `app.py` llama `init_camera_state_service(root_path=app.root_path)` inmediatamente después de crear `app = Flask(__name__)`.
- Se eliminaron de `app.py` las definiciones duplicadas de esos helpers.

## Qué quedó pendiente en app.py (por seguridad)

No se movieron en este refactor (dependen de más estado global/locks y flujo ONVIF):

- `_ptz_discovered_capable`
- `is_ptz_ready_for_manual`
- `is_ptz_ready_for_automation`
- lógica/estado de auto-discovery ONVIF (`_probe_onvif_ptz_capability`, `_set_ptz_capable`, etc.)
- `camera_source_mode` y estados asociados

Estas funciones ahora siguen usando `leer_config_camara()` / `is_camera_configured_ptz()` importadas del servicio, manteniendo la misma fuente de verdad.

## Cómo probar

1. Arrancar:
   - `py app.py`
2. Login admin:
   - abrir `/admin_dashboard`
   - cambiar tipo fija/PTZ y guardar (debe persistir en `config_camara.json`).
3. Verificar lectura:
   - `GET /api/get_camera_status` debe reflejar `"ptz"` o `"fixed"` según el archivo.
4. Login operador:
   - `GET /api/camera_status` responde `200`.
   - PTZ manual (`/ptz_move`, `/api/ptz_stop`) y automatización (`/api/auto_tracking`, `/api/inspection_mode`) siguen funcionando igual.

## Riesgos conocidos

- Si `init_camera_state_service(...)` no se llama, el servicio no puede resolver la ruta del archivo y fallará (por eso se inicializa al crear la app).
- No se movió aún el estado ONVIF/PTZ descubierto; queda para un refactor posterior.

