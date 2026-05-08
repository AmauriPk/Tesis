# Refactor: Inspection patrol worker a servicio

Fecha: 2026-05-08

## Qué se movió

Desde `app.py` se extrajo a un servicio dedicado:

- `class _InspectionPatrolWorker` (worker de inspección/patrullaje automático)
- lógica interna de barrido/inspección
- llamadas a `ptz_worker.enqueue_move(...)` / `ptz_worker.enqueue_stop()`
- logs `[INSPECTION_CMD]` y `[INSPECTION_WORKER][ERROR]` (sin cambios)

Nuevo archivo:
- `src/services/inspection_patrol_service.py`

## Interfaz pública conservada

- `start()` (se mantiene el arranque idempotente del hilo)
- Se agregó `stop(timeout_s=...)` como utilidad (no cambia el flujo actual si no se usa).

## Dependencias (inyección desde app.py)

Para evitar importar `app.py`, el worker recibe por constructor:

- `ptz_worker`
- `state_lock`
- `current_detection_state`
- `get_inspection_mode_enabled`, `set_inspection_mode_enabled`
- `get_auto_tracking_enabled`
- `is_ptz_ready_for_automation`
- `tracking_target_is_recent`
- `clamp` (se pasa `_clamp` de `app.py`)

## Qué se dejó en `app.py`

- La instancia global y su arranque:
  - `inspection_worker = _InspectionPatrolWorker(...)`
  - `inspection_worker.start()`
- Rutas y control de modo (`/api/inspection_mode`) permanecen en `src/routes/automation.py` (sin cambios).

## Cómo probar

1. `py app.py`
2. Login operador → dashboard.
3. Activar inspección automática:
   - `POST /api/inspection_mode` con `{ "enabled": true }`
4. Confirmar logs `[INSPECTION_CMD]` y que la cámara se mueve.
5. Desactivar inspección:
   - `POST /api/inspection_mode` con `{ "enabled": false }`
6. Verificar STOP y que PTZ manual / tracking automático siguen funcionando.

## Riesgos conocidos

- El cambio es de ubicación de código; el riesgo principal es un error de inyección/import. Se validó con `py_compile`.
- No se movieron rutas ni workers de tracking/PTZ, por lo que el comportamiento esperado debe ser idéntico.

