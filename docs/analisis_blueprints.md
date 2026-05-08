# Análisis de Blueprints e Inyección de Dependencias — SIRAN

Fecha: 2026-05-07

---

## Patrón general

Todos los blueprints usan el mismo patrón de inyección de dependencias vía `_deps`:

```python
_deps: dict[str, Any] = {}
_routes_initialized = False

def init_*_routes(**deps):
    global _deps, _routes_initialized
    _deps = dict(deps or {})
    if _routes_initialized:
        return
    _routes_initialized = True
    ...
```

**Ventaja**: evita imports circulares y desacopla la inicialización.  
**Riesgo**: acceso a `_deps["key"]` levanta `KeyError` silencioso si la clave no se pasa.

---

## Análisis por Blueprint

### `analysis_bp` — `src/routes/analysis.py`

| Verificación | Estado | Detalle |
|---|---|---|
| Usa `_deps` correctamente | ✅ | Todas las claves requeridas están documentadas |
| Puede fallar por KeyError | ⚠️ | `_deps["app"]`, `_deps["yolo_model"]`, `_deps["YOLO_CONFIG"]`, `_deps["allowed_file"]`, `_deps["state_lock"]`, `_deps["get_camera_source_mode"]`, `_deps["metrics_writer"]`, `_deps["get_model_params"]`, `_deps["role_required"]` — todos se pasan en app.py. OK. |
| Dependencias se inicializan antes | ✅ | `init_analysis_routes` se llama en línea ~838, después de que `yolo_model`, `state_lock`, `MODEL_PARAMS`, etc. están definidos |
| Endpoints conservan URLs originales | ✅ | `/video_progress`, `/upload_detect` |
| Templates con url_for correcto | N/A | No renderiza templates |
| Riesgo de endpoint duplicado | ✅ | No |
| Rutas con permisos correctos | ✅ | `role_required("operator")` en todos los endpoints sensibles |

**Hallazgo**: `_deps["YOLO_CONFIG"]["device"]` accede directamente al device de configuración (puede ser "cuda:0" aunque no haya GPU). En `video_processor.py` el device se determina dinámicamente. Inconsistencia menor — no rompe.

---

### `events_bp` — `src/routes/events.py`

| Verificación | Estado | Detalle |
|---|---|---|
| Usa `_deps` correctamente | ✅ | |
| Puede fallar por KeyError | ⚠️ | `_deps["storage_config"]`, `_deps["evidence_dir"]`, `_deps["app_root_path"]` — todos pasados en app.py |
| Dependencias inicializadas antes | ✅ | `init_events_routes` se llama en línea ~852 |
| Endpoints conservan URLs originales | ✅ | `/api/recent_alerts`, `/api/recent_detection_events`, `/api/export_detection_events.csv`, `/api/detection_summary`, `/api/admin/cleanup_test_data` |
| Rutas con permisos correctos | ✅ | `role_required("operator")` o `("operator", "admin")` o `("admin")` |
| Riesgo de endpoint duplicado | ✅ | No |

**Nota**: `import struct` está dentro del cuerpo de la ruta `api_recent_alerts` (línea ~108). Es un import a nivel de función, lo que es correcto pero inusual. Mover al top-level del archivo no cambia funcionalidad.

---

### `auth_bp` — `src/routes/auth.py`

| Verificación | Estado | Detalle |
|---|---|---|
| Usa `_deps` correctamente | ✅ | Solo usa `_deps["User"]` y `_deps["FLASK_CONFIG"]` |
| Puede fallar por KeyError | ⚠️ | Bajo riesgo — solo 2 claves, ambas siempre presentes |
| Dependencias inicializadas antes | ✅ | Llamado en línea ~863 |
| Endpoints | ✅ | `/login`, `/logout` |
| Rutas con permisos correctos | ✅ | `@login_required` en logout |
| `url_for` correcto | ✅ | `url_for("dashboard.index")` y `url_for("auth.login")` — blueprints registrados antes de estos calls |

---

### `admin_camera_bp` — `src/routes/admin_camera.py`

| Verificación | Estado | Detalle |
|---|---|---|
| Usa `_deps` correctamente | ✅ | Extrae dependencias al inicio |
| Puede fallar por KeyError | ⚠️ | `_deps["db"]`, `_deps["PTZController"]`, `_deps["probe_onvif_ptz_capability"]`, etc. Todos pasados. |
| Dependencias inicializadas antes | ✅ | `init_admin_camera_routes` se llama en línea ~1255, después de que `_probe_onvif_ptz_capability` está definida |
| Endpoints | ✅ | `/admin_dashboard`, `/admin/camera`, `/admin/camera/test`, `/api/test_connection` |
| Rutas con permisos correctos | ✅ | Todos `role_required("admin")` |
| `url_for` correcto | ✅ | `url_for("admin_camera.admin_dashboard")` — correcto con prefijo de blueprint |

---

### `dashboard_bp` — `src/routes/dashboard.py`

| Verificación | Estado | Detalle |
|---|---|---|
| Usa `_deps` correctamente | ✅ | |
| Puede fallar por KeyError | ⚠️ | `_deps["get_live_processor"]`, `_deps["get_live_reader"]` son lambdas — acceso lazy, correcto |
| Dependencias inicializadas antes | ⚠️ | `init_dashboard_routes` se llama en línea ~1386, **después** de que `live_processor` y `live_reader` están definidos (líneas ~1348, ~1368). OK. |
| Endpoints | ✅ | `/`, `/video_feed`, `/detection_status`, `/api/camera_status` |
| Rutas con permisos correctos | ✅ | `role_required("operator")` en rutas sensibles |
| `url_for` correcto | ✅ | `url_for("admin_camera.admin_dashboard")`, `url_for("dashboard.index")` |

**Hallazgo importante**: `video_feed` redirige al `mjpeg_generator()` de `live_processor`. Este genera un stream infinito. El `live_processor` arranca **lazily** cuando se llama a `ensure_started()` desde `mjpeg_generator()`. Si nadie accede al video_feed, los hilos no arrancan — lo cual es correcto y eficiente.

---

### `model_params_bp` — `src/routes/model_params.py`

| Verificación | Estado | Detalle |
|---|---|---|
| Usa `_deps` correctamente | ✅ | Solo `role_required` y `update_model_params` |
| Puede fallar por KeyError | ✅ | Bajo riesgo |
| Endpoints | ✅ | `/api/update_model_params` |
| Rutas con permisos correctos | ✅ | `role_required("admin")` |

---

### `ptz_manual_bp` — `src/routes/ptz_manual.py`

| Verificación | Estado | Detalle |
|---|---|---|
| Usa `_deps` correctamente | ✅ | Extrae todas las deps al inicio |
| Puede fallar por KeyError | ⚠️ | Muchas claves. Todas se pasan en app.py. |
| Dependencias inicializadas antes | ✅ | Llamado en línea ~1619, después de `ptz_worker`, `tracking_target_state`, etc. |
| Endpoints | ✅ | `/ptz_move`, `/api/ptz_stop` |
| Rutas con permisos correctos | ✅ | `role_required("operator")` |

**Nota**: `with app.app_context()` dentro del endpoint `ptz_move` (línea ~63). Esto es técnicamente innecesario ya que Flask ya provee contexto de aplicación durante un request normal. No rompe, pero es redundante.

---

### `automation_bp` — `src/routes/automation.py`

| Verificación | Estado | Detalle |
|---|---|---|
| Usa `_deps` correctamente | ✅ | |
| Puede fallar por KeyError | ⚠️ | Claves como `tracking_target_state`, `tracking_target_lock` se pasan pero no se usan en las rutas actuales de automation.py — están en `_deps` pero solo `ptz_worker`, `state_lock`, `is_ptz_ready_for_automation`, los getters/setters se usan. |
| Endpoints | ✅ | `/api/auto_tracking`, `/api/inspection_mode` |
| Rutas con permisos correctos | ✅ | `role_required("operator")` |

---

### `dataset_bp` — `src/routes/dataset.py`

| Verificación | Estado | Detalle |
|---|---|---|
| Usa `_deps` correctamente | ✅ | |
| Puede fallar por KeyError | ⚠️ | `_deps["safe_join"]`, `_deps["dataset_recoleccion_folder"]`, etc. Todos pasados. |
| Dependencias inicializadas antes | ✅ | |
| Endpoints | ✅ | `/api/get_dataset_images`, `/api/dataset_image`, `/api/classify_image`, `/api/get_classified_images`, `/api/classified_image`, `/api/revert_classification` |
| Rutas con permisos correctos | ✅ | Todos `role_required("admin")` |

---

## Hallazgos generales

| Hallazgo | Severidad | Archivo |
|---|---|---|
| `import struct` dentro del cuerpo de una función | Bajo | `events.py` línea ~108 |
| `with app.app_context()` innecesario durante request | Bajo | `ptz_manual.py` línea ~63 |
| `_deps` no tiene tipado estricto — KeyError en runtime si falta clave | Medio | Todos los blueprints |
| `is_camera_configured_ptz` en `automation.py` se pasa en `_deps` pero no se usa en ninguna ruta | Bajo | `automation.py` |
| `tracking_target_state` y `tracking_target_lock` en `automation.py` pasados en `_deps` pero no usados | Bajo | `automation.py` |

---

## Rutas directas que quedan en app.py (no en blueprints)

| Ruta | Descripción | Recomendación |
|---|---|---|
| `GET /media/<path:rel_path>` | Sirve evidencias/frames | Mover a `dashboard_bp` o un `media_bp` post-defensa |
| `GET /api/get_camera_status` | Estado de cámara configurada | Mover a `dashboard_bp` post-defensa |
| `POST /api/inspection_test_move` | Test de movimiento directo | Mover a `ptz_manual_bp` post-defensa |
| `GET /__diag` | Diagnóstico de debug | Mantener en app.py (debug-only) |
