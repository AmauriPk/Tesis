# Refactor: rutas de eventos/alertas a Blueprint

Fecha: 2026-05-07

## Qué se movió

Desde `app.py` se extrajeron a un Blueprint separado las rutas **de eventos, alertas, resumen y exportación**:

- `GET /api/recent_alerts`
- `GET /api/recent_detection_events`
- `GET /api/detection_summary`
- `GET /api/export_detection_events.csv`
- `POST /api/admin/cleanup_test_data`

Se mantuvieron exactamente las mismas URLs, métodos, JSON y protecciones (`login_required` + `role_required(...)`).

## Endpoints conservados (sin cambios)

El Blueprint se registra **sin prefijo**, por lo que se conservan:

- `GET /api/recent_alerts`
- `GET /api/recent_detection_events`
- `GET /api/detection_summary`
- `GET /api/export_detection_events.csv`
- `POST /api/admin/cleanup_test_data`

## Dónde quedó

- Blueprint: `src/routes/events.py`
  - `events_bp = Blueprint("events", __name__)`
  - `init_events_routes(**deps)` para inyección de dependencias y evitar imports circulares con `app.py`.

## Dependencias inyectadas (desde app.py)

`src/routes/events.py` no importa `app.py`. En su lugar `app.py` llama:

- `init_events_routes(...)` con:
  - `app_root_path` (equivalente a `app.root_path`)
  - `storage_config` (equivalente a `STORAGE_CONFIG`, para ubicar `detections.db`)
  - `evidence_dir` (equivalente a `EVIDENCE_DIR`; mantiene override por `EVIDENCE_DIR` env var)
  - `role_required` (decorador RBAC, para conservar protección exacta)
  - `get_metrics_db_path_abs` (callable `_get_metrics_db_path_abs`)
  - `ensure_detection_events_schema` (callable `_ensure_detection_events_schema`)
  - `parse_iso_ts_to_epoch` (callable `_parse_iso_ts_to_epoch`)

Luego registra:

- `app.register_blueprint(events_bp)`

## Helpers movidos vs pendientes

Movidos a `src/routes/events.py`:

- No se movieron helpers globales del writer; solo lógica interna propia de los endpoints.

Pendientes (se mantuvieron en `app.py` por seguridad / acoplamiento):

- `DetectionEventWriter` y su inicialización (`_event_writer`).
- `_get_metrics_db_path_abs`, `_ensure_detection_events_schema`, `_parse_iso_ts_to_epoch` (se usan también por `DetectionEventWriter`).

La lógica del writer puede migrarse después a un servicio dedicado (por ejemplo `src/services/event_service.py`) sin tocar endpoints.

## Cómo probar (eventos recientes)

1. Arrancar la app:
   - `py app.py`
2. Login con rol `operator`.
3. Probar:
   - `GET /api/recent_detection_events?limit=15` → `200` y JSON `{ ok, status, events }`

## Cómo probar (alertas recientes)

1. Login con rol `operator`.
2. Probar:
   - `GET /api/recent_alerts?limit=15` → `200` y JSON con `alerts` (fail-safe: lista vacía si DB no existe).

## Cómo probar (resumen estadístico)

1. Login con rol `operator` o `admin`.
2. Probar:
   - `GET /api/detection_summary` → `200` y campos esperados (conteos y evidencias).

## Cómo probar (exportación CSV)

1. Login con rol `operator` o `admin`.
2. Probar:
   - `GET /api/export_detection_events.csv` → descarga CSV (si DB no existe, retorna solo header).

## Cómo probar (cleanup admin)

1. Login con rol `admin`.
2. Probar preview (no borra nada si no se envían `true` explícitos):
   - `POST /api/admin/cleanup_test_data` con body `{}`.
3. Probar ejecución (con cuidado en ambiente controlado):
   - body con `clear_events`, `clear_raw_detections`, `clear_evidence`.

## Riesgos conocidos

- Si `init_events_routes(...)` no se llama antes de registrar el Blueprint, las rutas no quedan registradas.
- Los helpers de schema/parsing siguen en `app.py` por acoplamiento con `DetectionEventWriter` (pendiente mover a un service en un refactor posterior).

