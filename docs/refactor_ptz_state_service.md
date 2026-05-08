# Refactor: servicio de estado PTZ (automatización)

Fecha: 2026-05-07

## Qué se movió

Desde `app.py` se centralizó el estado de automatización PTZ en un servicio dedicado:

- `auto_tracking_enabled` (getter/setter)
- `inspection_mode_enabled` (getter/setter)
- `tracking_target_state` + lock
- actualización/limpieza/lectura del objetivo de tracking

## Dónde quedó

- Servicio: `src/services/ptz_state_service.py`
  - `PTZStateService`

## Cómo se integra (compatibilidad gradual)

En `app.py` se crea:

- `ptz_state_service = PTZStateService()`

y se dejan aliases/wrappers temporales para no romper dependencias existentes:

- `state_lock = ptz_state_service.state_lock` (ahora es `RLock` para evitar deadlocks con patrones existentes)
- `tracking_target_lock = ptz_state_service.tracking_target_lock`
- `tracking_target_state = ptz_state_service.tracking_target_state`
- `get_auto_tracking_enabled()`, `set_auto_tracking_enabled(value)`
- `get_inspection_mode_enabled()`, `set_inspection_mode_enabled(value)`
- `_update_tracking_target(payload)` (wrapper)
- `_get_tracking_target_snapshot()` (wrapper)

Esto permite que rutas/blueprints/workers sigan operando sin cambios grandes.

## Qué NO se movió (pendiente)

Este refactor no mueve ni cambia:

- workers (`PTZCommandWorker`, tracking/inspection workers)
- lógica interna de tracking automático e inspección automática
- endpoints (no se movieron rutas aquí)

## Logs conservados

- Se conserva el log `[TRACKING_TARGET]` dentro de `PTZStateService.update_tracking_target(...)`.

## Cómo probar

1. Arrancar:
   - `py app.py`
2. Login operador:
   - toggles de `tracking` e `inspección` siguen funcionando (`/api/auto_tracking`, `/api/inspection_mode`).
3. PTZ stop central:
   - `POST /api/ptz_stop` con `disable_tracking=true` debe desactivar tracking y limpiar target.
4. Confirmar tracking:
   - cuando hay objetivo, debe seguir apareciendo log `[TRACKING_TARGET]`.

## Riesgos conocidos

- `state_lock` pasó a ser `RLock` para evitar deadlocks por patrones existentes de “lock externo + setter”.
- Aún hay acceso directo a `tracking_target_state` en algunos módulos; queda pendiente encapsularlo por completo en un refactor posterior.

