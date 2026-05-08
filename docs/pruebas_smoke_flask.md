# Smoke tests Flask (sin hardware)

## Objetivo

Verificar con `FlaskClient` que el enrutamiento básico funciona y que los Blueprints “ligeros”:

- se pueden registrar sin errores de dependencias,
- protegen rutas con `login_required`,
- no exponen archivos sensibles vía `/media`,
- y que el `url_map` contiene las rutas esperadas.

## Archivo de pruebas

- `tests/test_flask_smoke.py`

## Endpoints cubiertos (smoke)

- `GET /login` (200)
- `POST /login` con usuario inválido (200; no revienta)
- `GET /logout` sin sesión (respuesta controlada; típicamente 302)
- Sin sesión: redirección/control en
  - `GET /`
  - `GET /api/camera_status`
  - `GET /detection_status`
  - `GET /api/recent_alerts`
  - `GET /api/recent_detection_events`
  - `GET /api/detection_summary`
  - `POST /api/update_model_params`
  - `POST /ptz_move`
  - `POST /api/ptz_stop`
  - `GET /api/auto_tracking`
  - `GET /api/inspection_mode`
  - `GET /media/<path>`
- Traversal: `GET /media/../.env` nunca devuelve 200 (con sesión simulada).

## Qué se evitó (por seguridad / dependencias pesadas)

- No se importa `app.py` (para evitar inicialización de YOLO/workers/hardware).
- No se prueba `/video_feed` (stream infinito).
- No se registran `src/routes/admin_camera.py` y `src/routes/analysis.py` en este smoke test:
  - `admin_camera.py` importa `cv2` (dependencia pesada).
  - `analysis.py` suele depender de stack de video/YOLO.

## Cómo ejecutar

- `py -3.11 -m pytest tests`

## Limitaciones

- Estos smoke tests validan el enrutamiento y protección, no la lógica real de hardware/DB.
- Los decorators `role_required(...)` se stubean en el test app para no acoplar a la implementación de RBAC.

## Recomendaciones futuras

- Agregar smoke tests opcionales para `admin_camera`/`analysis` en un job/entorno con dependencias completas (opencv/ultralytics) y con flags que desactiven hardware real.

