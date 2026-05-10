# Refactor: `ptz_capability_service` (capacidad PTZ / readiness / probe ONVIF)

## Objetivo
Reducir `app.py` extrayendo la lógica de:
- capacidad PTZ descubierta por ONVIF (`probe_onvif_ptz_capability`);
- estado `is_ptz_capable` / `camera_source_mode`;
- readiness para PTZ manual / automatización (`is_ptz_ready_for_manual`, `is_ptz_ready_for_automation`);
- logs controlados `[PTZ_READY]` y cache anti-spam;
- estado auxiliar del último probe ONVIF.

Sin cambiar endpoints, rutas, UI, workers ni comportamiento funcional.

## Qué se creó
- `src/services/ptz_capability_service.py`
  - `PTZCapabilityService`

## Qué se movió al servicio
La lógica que vivía en `app.py` ahora vive en métodos del servicio:
- `set_ptz_capable(...)`
- `ptz_discovered_capable()`
- `should_log_ptz_ready()` / `log_ptz_ready(...)`
- `is_ptz_ready_for_manual()` / `is_ptz_ready_for_automation()`
- `probe_onvif_ptz_capability()`
- `get_camera_source_mode()`
- `get_onvif_probe_status()`

## Wrappers conservados en `app.py` (compatibilidad)
Para no romper dependencias existentes (Blueprints y workers que importan/inyectan estas funciones por nombre), `app.py` conserva wrappers:
- `_set_ptz_capable(...)` → delega a `ptz_capability_service.set_ptz_capable(...)` y sincroniza variables globales.
- `_ptz_discovered_capable()` → delega al servicio.
- `is_ptz_ready_for_manual()` / `is_ptz_ready_for_automation()` → delegan al servicio.
- `_probe_onvif_ptz_capability()` → mantiene `with app.app_context(): ...` y delega al servicio.
- `_get_camera_source_mode()` → delega al servicio.

También se mantiene compatibilidad con variables globales usadas en otros bloques:
- `is_ptz_capable`
- `camera_source_mode`
- `_onvif_last_probe_at`
- `_onvif_last_probe_error`
- `_last_ptz_ready_manual` / `_last_ptz_ready_automation`

## Manejo de `app.app_context()`
El servicio **no** importa `app.py`.
Si `get_or_create_camera_config()` requiere contexto Flask/DB, el wrapper `_probe_onvif_ptz_capability()` en `app.py` lo provee con:
- `with app.app_context(): ptz_capability_service.probe_onvif_ptz_capability()`

## Comportamiento conservado
- `set_ptz_capable(False)` desactiva tracking/inspección **solo** si la cámara no está configurada como PTZ.
- `camera_source_mode` pasa a `"ptz"` si la cámara es PTZ por descubrimiento o por configuración, si no `"fixed"`.
- `current_detection_state["camera_source_mode"]` se mantiene sincronizado.
- Readiness manual/automation: `ready = is_camera_configured_ptz() or ptz_discovered_capable()`.
- Probe ONVIF:
  - valida host y credenciales;
  - normaliza puerto (si `554` se trata como RTSP y se intenta `80/8000/8080`);
  - usa `ONVIFCamera` importado dentro de la función;
  - prueba `GetCapabilities` y fallback con `GetServiceCapabilities`;
  - registra error en `onvif_last_probe_error` si falla.

## Pruebas agregadas (sin hardware real)
- `tests/test_ptz_capability_service.py`
  - stubs/mocks, sin conexión ONVIF real.
  - cubre: `set_ptz_capable`, readiness, errores por host/credenciales faltantes, normalización de puerto.

## Validación
- `py scripts/check_project.py`

## Prueba manual recomendada
1. `py scripts/run_dev.py`
2. Login operador → verificar dashboard.
3. Probar `PTZ manual`, `tracking automático` e `inspección automática`.
4. Login admin → `\/admin/camera` y prueba de conexión/ONVIF/PTZ según configuración.

## Pendientes / riesgos conocidos
- No se prueba ONVIF real en CI/tests (hardware/credenciales no disponibles). El comportamiento se conserva copiando la lógica existente y probando rutas de error y estados internos con stubs.

