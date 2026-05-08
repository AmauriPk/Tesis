# Pruebas básicas de servicios (pytest)

## Servicios cubiertos

- `src/services/camera_state_service.py`
- `src/services/ptz_state_service.py`
- `src/services/media_service.py`
- `src/services/model_params_service.py`

## Qué cubre cada suite

- `tests/test_camera_state_service.py`
  - Inicialización con `tmp_path` (sin tocar `config_camara.json` real).
  - Lectura por defecto (False si no existe).
  - Escritura/lectura (True/False).
  - Normalización de tipo (`set_configured_camera_type`).
  - Manejo de JSON corrupto (retorna False sin romper).
- `tests/test_ptz_state_service.py`
  - Flags `auto_tracking_enabled` y `inspection_mode_enabled`.
  - Estado inicial del objetivo de tracking.
  - `update_tracking_target`, `clear_tracking_target`.
  - Snapshot como copia (mutaciones no afectan al estado).
  - Payload inválido no revienta.
- `tests/test_media_service.py`
  - Normalización de paths relativos.
  - Bloqueo de path traversal (`..`).
  - `safe_join` no permite escapar del `base_dir`.
- `tests/test_model_params_service.py`
  - Shape de parámetros y copia en `get_model_params`.
  - `update_model_params` actualiza y normaliza `persistence_frames` mínimo a 1.
  - `get_detection_persistence_frames` respeta env var y fallback seguro.

## Cómo ejecutar

- Ejecutar tests:
  - `py -m pytest tests`

## Qué NO se probó todavía

- Rutas Flask / Blueprints (intencionalmente fuera de este paso).
- Integración con YOLO, RTSP, ONVIF/PTZ, `LiveVideoProcessor`.
- Workers (`PTZCommandWorker`, `TrackingPTZWorker`, `InspectionPatrolWorker`).

## Recomendaciones futuras

- Agregar tests de integración para endpoints (solo smoke-tests) usando `FlaskClient`, sin tocar hardware real.
- Agregar tests de sanitización de URLs/paths en flujos de evidencias (events + media route) cuando se estabilice post-defensa.

