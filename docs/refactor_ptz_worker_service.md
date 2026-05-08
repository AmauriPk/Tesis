# Refactor: PTZCommandWorker a servicio

Fecha: 2026-05-08

## Qué se movió

Desde `app.py` se extrajo a un servicio dedicado el worker de comandos PTZ:

- `PTZCommandWorker`
- Cola interna de comandos (`enqueue_move`, `enqueue_direction`, `enqueue_stop`)
- Construcción del controlador ONVIF/PTZ dentro del hilo
- Logs del worker (`[PTZ_QUEUE]`, `[PTZ_WORKER]`, `[PTZ_CFG]`, `[ONVIF]`, etc.)

## Dónde quedó

- Servicio: `src/services/ptz_worker_service.py`
  - `PTZCommandWorker`

## Interfaz pública conservada

La clase conserva los mismos métodos públicos usados por el sistema:

- `start()`
- `enqueue_move(...)`
- `enqueue_direction(...)`
- `enqueue_stop()`

## Dependencias (inyección desde app.py)

Para evitar importar `app.py`, `PTZCommandWorker` recibe en su constructor:

- `app` (solo para `app.app_context()` dentro del hilo)
- `get_or_create_camera_config`
- `normalized_onvif_port`
- `PTZController` (clase existente; no se movió)

## Cambios en app.py

- `app.py` ahora importa `PTZCommandWorker` desde `src/services/ptz_worker_service`.
- Se removieron de `app.py`:
  - `def _ptz_vector(...)`
  - `class PTZCommandWorker`
- Se conserva la creación/arranque de `ptz_worker` (misma variable global, misma inicialización).

## Qué NO se movió (pendiente)

- `TrackingPTZWorker`
- `InspectionPatrolWorker`
- rutas Flask (`/ptz_move`, `/api/ptz_stop`, `/api/auto_tracking`, `/api/inspection_mode`)
- `LiveVideoProcessor`

## Cómo probar

1. Arrancar:
   - `py app.py`
2. Login operador:
   - joystick PTZ → debe mover (usa `ptz_worker.enqueue_move(...)`/`enqueue_direction(...)` vía endpoints ya existentes).
   - STOP central → debe detener (usa `ptz_worker.enqueue_stop()`).
3. Activar tracking / inspección:
   - deben seguir usando `ptz_worker` sin cambios.

## Riesgos conocidos

- El worker depende de `app.app_context()` para leer `CameraConfig` desde el hilo; por eso se inyecta `app`.
- Cualquier cambio futuro al contrato de `CameraConfig`/credenciales ONVIF debe seguir siendo compatible con el worker.

