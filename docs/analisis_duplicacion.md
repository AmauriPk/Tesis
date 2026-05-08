# Análisis de Duplicación de Lógica — SIRAN

Fecha: 2026-05-07

---

## Tabla de hallazgos

| Área | Archivos involucrados | Duplicación encontrada | Propuesta | Prioridad | Riesgo |
|---|---|---|---|---|---|
| Función `clamp` | `app.py::_clamp` / `system_core.py::clamp` | Lógica idéntica (`max(lo, min(hi, v))`). app.py tiene copia local `_clamp` a pesar de importar `clamp` de system_core. | Eliminar `_clamp` de app.py y usar el `clamp` importado (o alias). Se pasa `_clamp` a `TrackingPTZWorker` — cambiar a `clamp`. | Media | Bajo — solo renombrar y ajustar `_ptz_centering_vector` |
| Función `bbox_offset_norm` | `app.py::_bbox_offset_norm` / `video_processor.py::bbox_offset_norm` | Misma lógica de cálculo de offset normalizado del bbox. | Eliminar la versión de app.py (código muerto) post-defensa. | Baja | Bajo — ninguna la usa |
| Función `ptz_centering_vector` | `app.py::_ptz_centering_vector` / `video_processor.py::ptz_centering_vector` | Similares pero no idénticas (app.py usa control proporcional; video_processor usa zona binaria). Ninguna se usa realmente. | Eliminar ambas post-defensa (código muerto). | Baja | Bajo |
| Patrón JSON payload | `model_params.py`, `dataset.py`, `admin_camera.py`, `automation.py`, `ptz_manual.py` | El bloque `payload = request.get_json(silent=True) or {}` + `if not payload: payload = request.form.to_dict(flat=True)` aparece en 5+ rutas. | Crear helper `_get_request_payload() -> dict` como función interna en cada Blueprint o helper compartido. | Media (post-defensa) | Bajo |
| Bloque PTZ readiness check | `app.py::api_inspection_test_move` / `ptz_manual.py::ptz_move` / `ptz_manual.py::ptz_stop` | El mismo patrón `configured_ptz = is_camera_configured_ptz(); ptz_capable = ptz_discovered_capable(); ready = is_ptz_ready_for_manual()` + log + check aparece 3 veces. | Función helper `_check_ptz_ready()` que retorna (ready, error_response). | Media | Bajo |
| Conexión SQLite con PRAGMAs | `app.py::DetectionEventWriter._connect` / `system_core.py::MetricsDBWriter._connect` / `events.py` | Cada lugar abre `sqlite3.connect` + `PRAGMA journal_mode=WAL` + `PRAGMA synchronous=NORMAL`. | Helper `_open_wal_connection(path)` en un módulo de DB utilities. | Baja (post-defensa) | Bajo |
| Validación de límite de lista | `events.py::api_recent_alerts` / `events.py::api_recent_detection_events` / `dataset.py::api_get_dataset_images` | El patrón `limit = int(limit_raw) if limit_raw else default; limit = max(1, min(cap, limit))` aparece en múltiples endpoints. | Helper `_parse_limit(value, default, max_val)` | Baja | Muy bajo |
| Conversión de path absoluto a relativo para URL web | `events.py::api_recent_alerts` | Lógica de normalización de `image_path` a `image_url` es extensa (~25 líneas). Se replica parcialmente en `api_recent_detection_events`. | Función `_evidence_path_to_url(raw_path, root_path)` | Media | Bajo |
| `env_float`/`env_int` | `system_core.py` / `config.py` (re-exporta) / `app.py` (importa) | Las funciones `env_float` y `env_int` están en system_core, re-exportadas en config.py como `_env_float`, `_env_int`. | Consolidar — ya está hecho vía re-export. Eliminar duplicado si existe. | Ya consolidado | — |
| Lógica de `_unique_dest_path` | `dataset.py` | Solo existe en un lugar. No duplicada. | — | — | — |
| Backfill de detection_events | `app.py::DetectionEventWriter._backfill_from_detections` | Lógica compleja de reconstrucción que duplica parcialmente `_run`. Ambos procesan rows de detections_v2. | Factorizar loop de procesamiento de rows. Post-defensa. | Baja | Medio |
| Lectura de config_camara.json | `camera_state_service.py::leer_config_camara` | Llamada en múltiples lugares: dashboard.py (2 veces), automation.py (indirectamente), app.py. | Ya está centralizado en camera_state_service. Correcto. | Ya consolidado | — |

---

## Notas

- Las duplicaciones más impactantes son el patrón de payload JSON y el bloque PTZ readiness check, por aparecer en muchos archivos.
- La duplicación de `_clamp` es la única que se recomienda corregir ahora (junto a la limpieza de imports).
- No se recomienda refactorizar el bloque PTZ readiness antes de la defensa dado el riesgo de introducir bugs en lógica de seguridad.
