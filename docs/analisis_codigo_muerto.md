# Análisis de Código Muerto — SIRAN

Fecha: 2026-05-07

---

## Tabla de hallazgos

| Archivo | Elemento | Tipo | Evidencia | Recomendación | Riesgo |
|---|---|---|---|---|---|
| `app.py` | `_bbox_offset_norm(frame_w, frame_h, bbox_xyxy)` | Función | Definida en línea ~875. No hay ninguna llamada en app.py ni blueprints. Existe copia equivalente en `video_processor.py::bbox_offset_norm`. | Probable código muerto post-refactor. Documentar como pendiente de eliminar. | Bajo (no se llama) |
| `app.py` | `_ptz_centering_vector(frame_w, frame_h, bbox_xyxy, ...)` | Función | Definida en línea ~897. No se llama en ningún lugar. El tracking real lo hace `tracking_worker_service.py` inline. Existe copia en `video_processor.py`. | Probable código muerto. No eliminar aún (contiene lógica PTZ con comentarios de diseño). Documentar como pendiente. | Bajo |
| `app.py` | `_p_control_speed(error, deadzone, max_speed, k)` | Función | Definida en línea ~964. Solo es usada por `_ptz_centering_vector`, que es muerta. | Código muerto derivado. | Bajo |
| `app.py` | `_select_priority_detection(detection_list)` | Función wrapper | Definida en línea ~1135. Solo llama a `select_priority_detection` de system_core. No se llama desde ningún lugar de app.py ni de blueprints. | Probable código muerto post-refactor. La selección la hace `video_processor.py` directamente. | Bajo |
| `app.py` | `_require_ptz_capable()` | Función helper | Definida en línea ~1268. Llama a `abort(403)` si no es PTZ. No está siendo utilizada en ninguna ruta de app.py ni en blueprints. | Código muerto. Los blueprints hacen su propia verificación. | Bajo |
| `app.py` | `stream_lock = threading.Lock()` | Variable global | Línea ~711. No se usa en ninguna parte del archivo. | Código muerto, probablemente remanente de refactor anterior. Seguro eliminar. | Muy bajo |
| `app.py` | `cleanup_old_evidence(*, dry_run=True)` | Función utilitaria | Definida en línea ~1437. Nunca se llama automáticamente ni hay endpoint que la invoque. Comentario dice "No se ejecuta automáticamente". | Requiere revisión manual. Podría convertirse en endpoint admin o cron. No eliminar aún. | Requiere revisión |
| `app.py` | Variable global `camera_source_mode = "fixed"` | Variable | Línea ~713. Usada directamente en lambdas y `_set_ptz_capable`. Se actualiza pero es una variable suelta, no protegida por lock propio. | Revisar. Actualmente protegida por `state_lock` en `_set_ptz_capable`. Mantener. | Requiere revisión |
| `src/services/camera_state_service.py` | `set_configured_camera_type(camera_type)` | Función | Importada en app.py pero nunca llamada en app.py. En el código las escrituras se hacen vía `guardar_config_camara` directamente. | Probable código muerto en app.py (import). La función es válida en el servicio. Eliminar solo el import de app.py. | Bajo |
| `src/video_processor.py` | `_apply_min_ptz_speed(value, min_speed, max_speed)` | Función | Línea ~191 en video_processor.py. No se llama dentro de `video_processor.py`. El tracking_worker tiene su propia versión `_apply_min` inline. | Probable código muerto. Revisar si se usa por import externo. | Requiere revisión |
| `src/video_processor.py` | `bbox_offset_norm(frame_w, frame_h, bbox_xyxy)` | Función | No se llama en ningún lugar dentro de video_processor.py ni blueprints. La versión en app.py tampoco se usa. | Probable código muerto. Podría haberse planeado para tracking pero nunca se integró. | Bajo |
| `src/video_processor.py` | `ptz_centering_vector(frame_w, frame_h, bbox_xyxy, ...)` | Función | No se llama en ningún lugar. El tracking_worker_service implementa su propia lógica inline. | Probable código muerto. No eliminar hasta después de la defensa. | Bajo |
| `src/system_core.py` | `graceful_shutdown_handler(stop_signals)` | Función | No se llama en ningún lugar del proyecto (buscado en app.py, services, routes). | Probable código muerto de diseño inicial. | Bajo |
| `src/system_core.py` | `should_allow_ptz_move(*, is_ptz_capable)` | Función | Solo llamada por `assert_ptz_capable`. No se llama desde ningún Blueprint ni app.py. | Probable código muerto derivado. | Bajo |
| `src/system_core.py` | `assert_ptz_capable(*, is_ptz_capable)` | Función | No se llama en ningún lugar del proyecto. | Probable código muerto. | Bajo |
| `src/system_core.py` | `safe_join_path(*parts)` | Función | No se llama en ningún lugar. La función `_safe_join` en app.py es la que se usa. | Probable código muerto. | Bajo |
| `src/system_core.py` | `validate_bbox(bbox)` | Función | No se llama en ningún lugar. | Probable código muerto. | Bajo |
| `src/system_core.py` | `normalize_url_with_credentials(...)` | Función | No se llama en ningún lugar del proyecto (la URL RTSP se construye en `CameraConfig.effective_rtsp_url()`). | Probable código muerto. | Bajo |
| `config.py` | `PTZ_CONFIG` dict | Variable | Definido y exportado en config.py. No se importa ni usa en app.py ni services. | Código muerto. Los valores de PTZ se leen directamente de `os.environ` en los workers. | Bajo |
| `config.py` | `VISION_MODEL_PARAMS` dict | Variable | Definido en config.py. Los params se inicializan directamente en app.py desde `_env_float`/`_env_int`. | Código muerto / duplicado. `MODEL_PARAMS` en app.py es la fuente de verdad en runtime. | Bajo |
| `config.py` | `PERSISTENCE_CONFIG` dict | Variable | Definido en config.py pero no se usa en app.py. | Código muerto. | Bajo |
| `analysis.py` | `is_valid_video_file` (import) | Import | Importado desde video_export_service pero nunca llamado en analysis.py. | Import muerto. Seguro eliminar. | Muy bajo |

---

## Clasificación resumen

| Clasificación | Elementos |
|---|---|
| Seguro de eliminar (solo imports) | `set_configured_camera_type` en app.py, `is_valid_video_file` en analysis.py |
| Probable código muerto | `_bbox_offset_norm`, `_ptz_centering_vector`, `_p_control_speed`, `_select_priority_detection`, `_require_ptz_capable`, `stream_lock`, `graceful_shutdown_handler`, `should_allow_ptz_move`, `assert_ptz_capable`, `safe_join_path`, `validate_bbox`, `normalize_url_with_credentials`, `PTZ_CONFIG`, `VISION_MODEL_PARAMS`, `PERSISTENCE_CONFIG`, `_apply_min_ptz_speed`, `bbox_offset_norm` en video_processor, `ptz_centering_vector` en video_processor |
| Requiere revisión manual | `cleanup_old_evidence` (podría ser útil como endpoint futuro), `camera_source_mode` (mutable global, riesgo de concurrencia) |
| No eliminar | Todo lo que sea función/clase viva usada por threads o workers activos |

---

## Notas importantes

- Las funciones `_bbox_offset_norm`, `_ptz_centering_vector`, `_p_control_speed` en `app.py` son código que quedó huérfano después de que `tracking_worker_service.py` asumió el control del tracking.
- Las funciones de `system_core.py` (`graceful_shutdown_handler`, `should_allow_ptz_move`, `assert_ptz_capable`, `safe_join_path`, `validate_bbox`, `normalize_url_with_credentials`) parecen ser de una API pública planeada que nunca se integró plenamente.
- `cleanup_old_evidence` podría activarse como endpoint `/api/admin/cleanup_evidence` en el futuro, lo que la haría útil. No eliminar.
