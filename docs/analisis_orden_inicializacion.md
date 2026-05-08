# Análisis de Orden de Inicialización — SIRAN

Fecha: 2026-05-07

---

## Orden actual detectado (app.py)

| Paso | Línea aprox. | Elemento inicializado |
|---|---|---|
| 1 | 97 | `app = Flask(__name__)` + `secret_key` |
| 2 | 100 | `init_camera_state_service(root_path=app.root_path)` |
| 3 | 102-115 | Configuración de app (SQLALCHEMY, SESSION, etc.) |
| 4 | 123-133 | Configuración de UPLOAD/RESULTS/DATASET folders + `os.makedirs` |
| 5 | 136-150 | `EVIDENCE_DIR`, `DATASET_TRAINING_ROOT`, directorios de dataset |
| 6 | 152 | `db.init_app(app)` |
| 7 | 154-156 | `login_manager = LoginManager()` + `init_app(app)` |
| 8 | 158-166 | `@app.before_request` + `load_user` callbacks |
| 9 | 168-190 | Definición de `role_required` + `allowed_file` |
| 10 | 192-303 | Definición de helpers: `sync_onvif_config_from_env`, `_normalized_onvif_port`, `get_or_create_camera_config`, `bootstrap_users` |
| 11 | 275-296 | `load_yolo_model()` definida + `_metrics_writer = MetricsDBWriter(...)` — **MetricsDBWriter arranca su hilo aquí** |
| 12 | 306-334 | Helpers: `_get_metrics_db_path_abs`, `_parse_iso_ts_to_epoch`, `_ensure_detection_events_schema` |
| 13 | 337-691 | Definición de `DetectionEventWriter` clase completa |
| 14 | 693-699 | `_event_writer = DetectionEventWriter(...)` — **hilo de eventos arranca aquí** |
| 15 | 702-704 | `_metrics_enqueue_with_events` helper |
| 16 | 706 | `yolo_model = load_yolo_model()` — **carga GPU aquí** |
| 17 | 709-710 | `ptz_state_service = PTZStateService()` + extracción de `state_lock`, `tracking_target_lock`, `tracking_target_state` |
| 18 | 711 | `stream_lock = threading.Lock()` (variable muerta) |
| 19 | 713-832 | Variables de estado + helpers PTZ (`_update_tracking_target`, `_get_tracking_target_snapshot`, `_tracking_target_is_recent`, `MODEL_PARAMS`, `get_model_params`, `update_model_params`, `DETECTION_PERSISTENCE_FRAMES`, etc.) |
| 20 | 838-850 | `init_analysis_routes(...)` + `app.register_blueprint(analysis_bp)` |
| 21 | 852-861 | `init_events_routes(...)` + `register` |
| 22 | 863-867 | `init_auth_routes(...)` + `register` |
| 23 | 869-873 | `init_model_params_routes(...)` + `register` |
| 24 | 875-988 | Definición de helpers PTZ: `_bbox_offset_norm`, `_ptz_centering_vector`, `_clamp`, `_p_control_speed` (código muerto) |
| 25 | 990-1133 | Definición de `_InspectionPatrolWorker` clase |
| 26 | 1135-1143 | `_select_priority_detection` helper |
| 27 | 1145-1253 | `_set_ptz_capable` + `_probe_onvif_ptz_capability` |
| 28 | 1255-1265 | `init_admin_camera_routes(...)` + `register` |
| 29 | 1267-1316 | `_require_ptz_capable`, `_ptz_discovered_capable`, `_should_log_ptz_ready`, `_log_ptz_ready`, `is_ptz_ready_for_manual`, `is_ptz_ready_for_automation` |
| 30 | 1319-1325 | `ptz_worker = PTZCommandWorker(...)` + `.start()` — **hilo PTZ worker arranca aquí** |
| 31 | 1327-1328 | `inspection_worker = _InspectionPatrolWorker(...)` + `.start()` — **hilo inspección arranca aquí** |
| 32 | 1330-1338 | `tracking_worker = TrackingPTZWorker(...)` + `.start()` — **hilo tracking arranca aquí** |
| 33 | 1341-1346 | `_get_live_rtsp_url` helper |
| 34 | 1348-1352 | `live_reader = RTSPLatestFrameReader(...)` — **NO arranca aquí, arranca lazy en video_feed** |
| 35 | 1354-1359 | `live_deps = LiveStreamDeps(...)` |
| 36 | 1361-1366 | `_ptz_tracking_move` helper |
| 37 | 1368-1384 | `live_processor = LiveVideoProcessor(...)` — **NO arranca aquí, arranca lazy** |
| 38 | 1386-1396 | `init_dashboard_routes(...)` + `register` |
| 39 | 1398-1414 | Ruta `/__diag` directamente en app |
| 40 | 1417-1559 | Helpers: `_safe_rel_path`, `cleanup_old_evidence`, `_safe_join` |
| 41 | 1561-1570 | `init_dataset_routes(...)` + `register` |
| 42 | 1572-1587 | Ruta `/media` directamente en app |
| 43 | 1590-1600 | Ruta `/api/get_camera_status` directamente en app |
| 44 | 1602-1616 | `init_automation_routes(...)` + `register` |
| 45 | 1619-1635 | `init_ptz_manual_routes(...)` + `register` |
| 46 | 1637-1669 | Ruta `/api/inspection_test_move` directamente en app |
| 47 | 1672-1680 | **`with app.app_context()`**: `db.create_all()`, `get_or_create_camera_config()`, `guardar_config_camara()`, `bootstrap_users()`, `_probe_onvif_ptz_capability()` |
| 48 | 1682-1690 | `if __name__ == "__main__": app.run(...)` |
| 49 | 1692-1707 | `_shutdown_resources` + `atexit.register` |

---

## Orden recomendado vs. actual

El orden actual es **funcional** pero tiene algunas fragilidades documentadas:

| # | Problema | Riesgo | Corrección sugerida |
|---|---|---|---|
| 1 | `_metrics_writer` y `_event_writer` se crean (y arrancan sus hilos) antes de que `app.app_context()` esté disponible. Estos hilos usan SQLite directo (no SQLAlchemy), así que es OK. Pero si algún cambio futuro intentara usar `db.session` desde esos hilos, fallaría. | Bajo actual, medio futuro | Documentar explícitamente que estos hilos no deben usar SQLAlchemy |
| 2 | `MetricsDBWriter` arranca en línea ~293, antes de que `load_yolo_model()` (línea 706). Si el modelo tarda mucho en cargar, el writer ya está activo esperando records que nunca llegan. No es bug, pero el orden puede confundir. | Muy bajo | Reordenar: cargar YOLO, luego crear writers (post-defensa) |
| 3 | `inspection_worker` y `tracking_worker` arrancan (líneas 1327-1338) antes de `init_dashboard_routes` (línea 1386). Estos workers llaman a `is_ptz_ready_for_automation()` y `get_auto_tracking_enabled()` — ambas definidas antes. OK. Pero hay 0.25s de sleep entre iteraciones, por lo que si el primer tick corre antes de que `live_processor` esté definido, no importa (no usan live_processor). | Muy bajo | No cambiar |
| 4 | `init_admin_camera_routes` (línea 1255) recibe `probe_onvif_ptz_capability` como dep. Esta función usa `state_lock` (definido en línea 710) y `get_or_create_camera_config` (definida en línea ~236). Orden correcto. | OK | — |
| 5 | `_probe_onvif_ptz_capability()` se llama dentro de `with app.app_context()` al final (línea 1680). Si esta función falla/tarda, retrasa el primer request. | Bajo | Mover a un hilo separado post-arranque (post-defensa) |

---

## Riesgos actuales

| Riesgo | Descripción | Severidad |
|---|---|---|
| Hilos daemon sin app_context | `_event_writer`, `_metrics_writer`, `ptz_worker`, `inspection_worker`, `tracking_worker` corren fuera del contexto de Flask. No usan `db.session` directamente, así que está bien. | Bajo |
| `_probe_onvif_ptz_capability` en app_context bloqueante | Si hay timeout ONVIF al arranque, el servidor tarda en responder el primer request. | Medio |
| `bootstrap_users` usa DB | Se llama dentro de `app.app_context()` — correcto. | OK |
| `guardar_config_camara` falla silenciosamente | En el bloque `try/except: pass` del inicializador. Log agregado. | Bajo tras corrección |

---

## Correcciones aplicadas

- Log agregado en el bloque `except Exception: pass` de `guardar_config_camara` en el bloque de init.
- Sin cambios estructurales al orden (demasiado riesgo pre-defensa).
