# Refactor: `camera_config_service` (CameraConfig en DB)

## Objetivo
Reducir `app.py` extrayendo la lógica de configuración persistida de cámara (tabla `CameraConfig`) a un servicio dedicado, sin cambiar comportamiento ni endpoints.

Este refactor **no** toca `config_camara.json` (eso sigue en `src/services/camera_state_service.py`).

## Qué se movió
Se creó el servicio:
- `src/services/camera_config_service.py`

Incluye:
- `CameraConfigService.sync_onvif_config_from_env(cfg)`
- `CameraConfigService.normalized_onvif_port(port)`
- `CameraConfigService.get_or_create_camera_config()`

## Qué quedó en `app.py` (wrappers de compatibilidad)
Para no romper Blueprints/workers que ya inyectan dependencias por nombre, `app.py` conserva wrappers con los mismos nombres:
- `sync_onvif_config_from_env(cfg)`
- `_normalized_onvif_port(port)`
- `get_or_create_camera_config()`

Internamente delegan a una instancia:
- `camera_config_service = CameraConfigService(db=db, CameraConfig=CameraConfig, rtsp_config=RTSP_CONFIG, onvif_config=ONVIF_CONFIG)`

## Comportamiento conservado
- Si existe un registro `CameraConfig` en DB, se devuelve y se completa ONVIF **solo si campos están vacíos**.
- No se sobreescriben valores persistidos existentes.
- Si `cfg.onvif_port` está vacío, se completa desde `ONVIF_CONFIG["port"]` o `80`.
- `normalized_onvif_port(554)` devuelve `80` (evita confusión con RTSP).
- Si no existe `CameraConfig`, se crea con defaults:
  - `camera_type="fixed"`
  - RTSP desde `RTSP_CONFIG` (`url/username/password`)
  - ONVIF desde `ONVIF_CONFIG` (`host/port/username/password`)

## Diferencia con `camera_state_service`
- `camera_state_service`: estado simple en archivo `config_camara.json` (PTZ/fija) y helpers de lectura/escritura de ese JSON.
- `camera_config_service`: configuración persistida en DB (tabla `CameraConfig`) para RTSP/ONVIF (host/puerto/credenciales/URL).

## Pruebas agregadas
- `tests/test_camera_config_service.py`
  - Pruebas con stubs (sin DB real) para:
    - `normalized_onvif_port`
    - `sync_onvif_config_from_env` (no sobreescribe y completa vacíos)
    - `get_or_create_camera_config` (crea defaults / devuelve existente)

## Cómo validar
- Ejecutar: `py scripts/check_project.py`
- Prueba manual recomendada (sin cambiar nada del backend):
  - Login admin
  - Abrir `\/admin_dashboard` y `\/admin/camera`
  - Guardar configuración de cámara y verificar que persiste igual que antes

## Riesgos conocidos / pendiente
- La prueba de integración con una DB real (SQLAlchemy + modelo real `CameraConfig`) se deja pendiente para no introducir complejidad/riesgo en esta etapa.

