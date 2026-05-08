# Análisis de Estructura Actual — SIRAN

Fecha: 2026-05-07

---

## 1. Tamaño actual de app.py

**1708 líneas**

Es el archivo más grande del proyecto y sigue siendo el punto central de arranque y orquestación.

---

## 2. Responsabilidades que conserva app.py

### Responsabilidades legítimas de bootstrap (correctas aquí)
- Creación de la instancia Flask y configuración base (secret_key, SESSION, MAX_CONTENT_LENGTH, etc.)
- `init_camera_state_service` (necesita `app.root_path` antes que nada)
- `db.init_app(app)` y `login_manager.init_app(app)`
- `load_yolo_model()` — carga del modelo YOLO
- Inicialización de `PTZStateService`, `PTZCommandWorker`, `TrackingPTZWorker`
- Inicialización de `RTSPLatestFrameReader` y `LiveVideoProcessor`
- Registro de todos los Blueprints vía `init_*_routes` + `app.register_blueprint`
- `with app.app_context(): db.create_all(); bootstrap_users(); _probe_onvif_ptz_capability()`
- `atexit.register(_shutdown_resources)`

### Responsabilidades que deberían separarse (pendiente para post-defensa)
| Elemento | Líneas aprox. | Destino sugerido |
|---|---|---|
| `DetectionEventWriter` (clase completa) | ~350 | `src/services/detection_event_service.py` |
| `_InspectionPatrolWorker` (clase completa) | ~145 | `src/services/inspection_worker_service.py` |
| `get_or_create_camera_config`, `sync_onvif_config_from_env`, `bootstrap_users` | ~60 | `src/services/camera_config_service.py` |
| `_probe_onvif_ptz_capability` y helpers ONVIF | ~90 | `src/services/onvif_service.py` |
| `cleanup_old_evidence` | ~90 | `src/services/evidence_service.py` |
| `_ptz_centering_vector`, `_bbox_offset_norm`, `_p_control_speed` | ~85 | muerto o `src/services/ptz_math.py` |
| MODEL_PARAMS, `get_model_params`, `update_model_params` | ~45 | ya parcialmente en `model_params.py` (duplicado) |
| 3 rutas directas (`/media`, `/api/get_camera_status`, `/api/inspection_test_move`, `/__diag`) | ~80 | blueprints correspondientes |

---

## 3. Módulos ya separados correctamente

| Archivo | Responsabilidad |
|---|---|
| `src/services/video_export_service.py` | VideoWriter, ffmpeg, validación de video |
| `src/services/camera_state_service.py` | Persistencia tipo de cámara (config_camara.json) |
| `src/services/ptz_state_service.py` | Estado de flags PTZ y tracking target (thread-safe) |
| `src/services/ptz_worker_service.py` | Cola de comandos PTZ (un hilo dedicado) |
| `src/services/tracking_worker_service.py` | Worker de tracking automático PTZ |
| `src/routes/analysis.py` | Análisis manual imagen/video |
| `src/routes/events.py` | Alertas y eventos de detección |
| `src/routes/dataset.py` | Gestión del dataset (clasificar, revertir) |
| `src/routes/admin_camera.py` | Configuración de cámara (admin) |
| `src/routes/auth.py` | Login/logout |
| `src/routes/dashboard.py` | Dashboard operador, video_feed, detection_status |
| `src/routes/model_params.py` | Actualización de parámetros YOLO en caliente |
| `src/routes/ptz_manual.py` | Joystick PTZ manual |
| `src/routes/automation.py` | Tracking automático e inspección/patrullaje |

---

## 4. Partes de mayor riesgo

| Área | Riesgo | Motivo |
|---|---|---|
| `DetectionEventWriter._run` + `_backfill_from_detections` | Alto | Hilo daemon + escritura SQLite + lógica compleja |
| `_InspectionPatrolWorker._run` | Alto | Hilo daemon + PTZ + múltiples condiciones de pausa |
| `_probe_onvif_ptz_capability` | Medio | Red + ONVIF + efectos secundarios globales |
| Orden de inicialización en app.py | Medio | Algunos workers arrancan antes del `app_context` DB |
| `DetectionEventWriter._backfill_from_detections` | Medio | Lectura directa SQLite a bajo nivel (no SQLAlchemy) |

---

## 5. Partes duplicadas

| Elemento | Archivos | Detalle |
|---|---|---|
| `_clamp` en app.py | app.py / system_core.py | Función idéntica a `clamp` de system_core |
| `_bbox_offset_norm` en app.py | app.py / video_processor.py | Funciones equivalentes |
| `env_float`/`env_int` | system_core.py / config.py | Re-exportados vía alias |
| Patrón `get_json or form.to_dict` | model_params, dataset, admin_camera, automation | Patrón repetido en 4+ rutas |
| Bloque PTZ readiness check | ptz_manual.py / app.py (api_inspection_test_move) | Código duplicado |

---

## 6. Partes difíciles de mantener

| Área | Motivo |
|---|---|
| `DetectionEventWriter` en app.py | Clase de 350 líneas incrustada en app.py |
| `_InspectionPatrolWorker` en app.py | Clase de 145 líneas incrustada en app.py |
| Wiring de `_deps` en blueprints | Cualquier cambio de nombre rompe silenciosamente con KeyError |
| `_probe_onvif_ptz_capability` | Lógica anidada con fallback de puertos |
| `MODEL_PARAMS` global + lock | Acceso directo a global mutable desde múltiples hilos |

---

## 7. Puntos donde el orden de inicialización puede romperse

| Línea aprox. | Riesgo | Descripción |
|---|---|---|
| 709 | `PTZStateService()` | Debe crearse antes de cualquier Blueprint que use `state_lock` |
| 838 | `init_analysis_routes` | Recibe `state_lock` —  debe estar definido |
| 1255 | `init_admin_camera_routes` | Recibe `_probe_onvif_ptz_capability` — que usa `ptz_state_service` (OK, definido en 709) |
| 1319-1338 | Workers PTZ y tracking | Iniciados antes del `app_context` (OK, no usan DB directamente en init) |
| 1672 | `with app.app_context()` | DB, bootstrap y ONVIF probe — el último usa todos los servicios |
| 1706-1707 | `atexit.register` | Después de `if __name__` — se registra incondicionalmente, correcto |

**Riesgo actual**: el `inspection_worker` y `tracking_worker` arrancan (`.start()`) antes de `app.app_context()`, lo que significa que si el primero llama a algo que necesite DB, podría fallar. Actualmente no lo hace directamente, pero es frágil.
