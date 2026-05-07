# Refactor: rutas de análisis manual a Blueprint

Fecha: 2026-05-07

## Qué se movió

Desde `app.py` se movieron a un Blueprint separado las rutas y helpers **exclusivos** del análisis manual (upload de imagen/video + polling de progreso):

- `POST /upload_detect`
- `GET /video_progress`

También se movió el estado interno de jobs (antes global en `app.py`) para no mezclarlo con tracking/PTZ/inspección automática:

- `job_lock`
- `progress_by_job`
- `result_by_job`

Los helpers que ahora viven junto a esas rutas (en el mismo módulo) son:

- `_set_job_progress`
- `_set_job_result`
- `_run_detection_job`
- `_process_image_and_persist`
- `_persist_top_detections_images`
- `_process_video_and_persist`

## Endpoints conservados (sin cambios)

Se conservaron exactamente las mismas URLs y métodos:

- `POST /upload_detect`
- `GET /video_progress`

El Blueprint se registra **sin prefijo** (`url_prefix=None`) para no cambiar rutas.

## Dónde quedó

- Blueprint: `src/routes/analysis.py`
  - `analysis_bp = Blueprint("analysis", __name__)`
  - `init_analysis_routes(**deps)` para inyección de dependencias y evitar imports circulares con `app.py`.

## Dependencias inyectadas (desde app.py)

`src/routes/analysis.py` no importa `app.py`. En su lugar, `app.py` llama:

- `init_analysis_routes(...)` con:
  - `app` (para `app.config` y `app.root_path`)
  - `yolo_model`
  - `VIDEO_CONFIG`
  - `YOLO_CONFIG`
  - `allowed_file`
  - `get_model_params`
  - `state_lock`
  - `get_camera_source_mode` (callable; evita congelar el valor de `camera_source_mode`)
  - `metrics_writer` (para telemetría de frames de upload de imagen)
  - `role_required` (decorador RBAC, para conservar protección exacta)

Luego registra:

- `app.register_blueprint(analysis_bp)`

## Cómo probar (imagen)

1. Arrancar la app:
   - `py app.py`
2. Iniciar sesión con un usuario con rol `operator` (igual que antes).
3. En la UI, subir una imagen y ejecutar análisis manual.
4. Verificar:
   - el request a `POST /upload_detect` responde con `job_id`
   - el polling a `GET /video_progress?job_id=...` devuelve progreso y luego el JSON final
   - el resultado se escribe en `static/results/` (imagen)

## Cómo probar (video)

1. Arrancar la app:
   - `py app.py`
2. Iniciar sesión con rol `operator`.
3. Subir un video (mp4/avi/mov) y ejecutar análisis manual.
4. Verificar:
   - `POST /upload_detect` devuelve `job_id` y `analysis_root`
   - `GET /video_progress?job_id=...` avanza `progress` y termina con `done=true`
   - se generan archivos en `static/results/`:
     - `result_<job_id>_raw.mp4`
     - `result_<job_id>_browser.mp4` (si FFmpeg está disponible)
   - se generan top detections (base64 en JSON y persistencia en dataset `limpias/` y `con_bounding_box/`)

## Contrato JSON esperado (sin cambios)

En resultados finales de video se conserva:

- `result_type`
- `result_url`
- `result_video_url`
- `result_video_raw_url`
- `result_video_mime`
- `result_video_playable`
- `video_output_warning`
- `top_detections` (si aplica)

## Riesgos conocidos

- Si `init_analysis_routes(...)` no se llama antes de registrar el Blueprint, las rutas no quedarían configuradas.
- La telemetría del upload de imagen depende de `metrics_writer` y del callable `get_camera_source_mode`.

## Pendiente

- Consolidar helpers reutilizables (si en el futuro otras rutas necesitan lógica compartida) en módulos de servicios, manteniendo este Blueprint delgado.

