# Refactor: DetectionEventWriter a servicio

Fecha: 2026-05-08

## Qué se movió

Desde `app.py` se extrajo a un servicio dedicado:

- `DetectionEventWriter`
- `_ensure_detection_events_schema(con)`
- `_parse_iso_ts_to_epoch(ts_iso)`
- lógica interna de backfill desde `detections_v2` (método del writer)

Nuevo archivo:
- `src/services/detection_event_service.py`

## Qué se dejó en `app.py`

Para mantener integración y minimizar riesgo:

- Instanciación del writer:
  - `_event_writer = DetectionEventWriter(_get_metrics_db_path_abs(), enabled=..., gap_seconds=...)`
- Wrapper de encolado combinado:
  - `_metrics_enqueue_with_events(record)` (sigue encolando a `_metrics_writer` y `_event_writer`)
- Uso de `_ensure_detection_events_schema` en utilidades existentes (p. ej. `cleanup_old_evidence`).
- Inyección de dependencias hacia `src/routes/events.py` (se siguen pasando `ensure_detection_events_schema` y `parse_iso_ts_to_epoch`).

## Tablas y compatibilidad SQLite

No se cambiaron nombres ni columnas; el servicio usa exactamente:

- Tabla: `detection_events`
- Fuente de backfill: `detections_v2`

Se conserva:
- `PRAGMA journal_mode=WAL`
- `PRAGMA synchronous=NORMAL`
- formato de `best_bbox_text` (texto `"x1,y1,x2,y2"`)
- formato de `best_evidence_path` (path normalizado con `/`)

## Interfaz pública conservada

`DetectionEventWriter` conserva:
- `__init__(db_path, enabled=True, gap_seconds=...)`
- `enqueue(record)`
- `stop(timeout_s=...)`

## Cómo probar

1. Arranque:
   - `py app.py`
2. Generar detecciones (flujo normal).
3. Verificar endpoints:
   - `GET /api/recent_alerts?limit=15`
   - `GET /api/recent_detection_events?limit=15`
   - `GET /api/detection_summary`
   - `GET /api/export_detection_events.csv` (si aplica)
4. Verificar que `admin_dashboard` y dashboard operador siguen funcionando.

## Riesgos conocidos

- El refactor es de ubicación de código; el riesgo principal es un import/orden de inicialización incorrecto. Se validó con `py_compile`.
- No se movió `src/routes/events.py` en este refactor para evitar cambios de comportamiento en endpoints.

