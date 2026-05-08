# Refactor: TrackingPTZWorker a servicio

Fecha: 2026-05-08

## Qué se movió

Desde `app.py` se extrajo a un servicio dedicado el worker de tracking automático PTZ:

- `TrackingPTZWorker`
- lectura del objetivo (`get_tracking_target_snapshot`)
- lógica de pérdida de objetivo (TTL)
- conversión de bbox → comandos PTZ (`enqueue_move`/`enqueue_stop`)
- logs del tracking (`[TRACKING_WORKER]`)

## Dónde quedó

- Servicio: `src/services/tracking_worker_service.py`
  - `TrackingPTZWorker`

## Interfaz pública conservada

- `start()`

## Dependencias (inyección desde app.py)

Para evitar importar `app.py`, el constructor recibe:

- `state_lock`
- `ptz_worker` (instancia de `PTZCommandWorker`, ya refactorizada)
- `get_auto_tracking_enabled`
- `is_ptz_ready_for_automation`
- `get_tracking_target_snapshot` (wrapper hacia `PTZStateService`)
- `clamp` (callable `_clamp`)

## Cambios en app.py

- `app.py` ahora importa `TrackingPTZWorker` desde `src/services/tracking_worker_service`.
- Se eliminó la clase previa `_TrackingPTZWorker` de `app.py`.
- Se conserva el arranque del worker:
  - `tracking_worker = TrackingPTZWorker(...)`
  - `tracking_worker.start()`
- Nota: se corrigió el orden de inicialización en `app.py` para crear `ptz_worker` antes de inicializar workers o registrar Blueprints que lo reciben por inyección de dependencias.
- Nota: se corrigió el orden de inicialización en `app.py` para definir `is_ptz_ready_for_automation` antes de crear `TrackingPTZWorker` o registrar Blueprints que la reciben por inyección.

## Qué NO se movió (pendiente)

- `InspectionPatrolWorker`
- `LiveVideoProcessor`
- rutas Flask (`/api/auto_tracking`, `/api/inspection_mode`, `/ptz_move`, `/api/ptz_stop`)
- lógica de detección YOLO (solo consume bbox/estado generado)

## Cómo probar

1. Arrancar:
   - `py app.py`
2. Login operador.
3. Activar tracking:
   - `POST /api/auto_tracking` con `{ "enabled": true }`
4. Confirmar:
   - al detectar objetivo, deben aparecer logs `[TRACKING_WORKER] move ...`
   - si se pierde objetivo, debe enviar stop con log `stop reason=target_lost`.
5. STOP central:
   - `POST /api/ptz_stop` con `disable_tracking=true` debe desactivar tracking y no reanudar.
6. Verificar que inspección sigue funcionando (sin refactor en este paso).

## Riesgos conocidos

- El worker depende de `get_tracking_target_snapshot` para leer bbox/frame_w/frame_h; si el payload cambia, el tracking puede no emitir comandos.
- La lógica de seguimiento no se modificó; el cambio es únicamente de ubicación del código.
