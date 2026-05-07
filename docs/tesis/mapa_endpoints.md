# Mapa de Endpoints Flask — SIRAN

*Endpoints extraídos directamente del código fuente de `app.py`. No se inventaron endpoints.*

---

## Autenticación

| Ruta | Método | Rol | Propósito | Entrada | Salida | Módulo | Observaciones |
|---|---|---|---|---|---|---|---|
| `/login` | GET, POST | — | Formulario de autenticación | POST: `username`, `password` | Redirect / HTML | app.py:1796 | Redirige a `/?tab=live` si exitoso |
| `/logout` | GET | Autenticado | Cierre de sesión | — | Redirect a `/login` | app.py:1820 | — |

---

## Interfaz de usuario

| Ruta | Método | Rol | Propósito | Entrada | Salida | Módulo | Observaciones |
|---|---|---|---|---|---|---|---|
| `/` | GET | operator | Dashboard principal del operador | `?tab=live|manual` | HTML | app.py:1846 | Admin es redirigido a `/admin_dashboard` |
| `/admin_dashboard` | GET | admin | Dashboard del administrador | — | HTML | app.py:1867 | — |

---

## Configuración de cámara (Admin)

| Ruta | Método | Rol | Propósito | Entrada | Salida | Módulo | Observaciones |
|---|---|---|---|---|---|---|---|
| `/admin/camera` | GET, POST | admin | Editar configuración RTSP/ONVIF | POST: `camera_type`, `rtsp_url`, `rtsp_username`, `rtsp_password`, `onvif_host`, `onvif_port`, `onvif_username`, `onvif_password` | Redirect | app.py:1876 | Persiste en SQLite y JSON |
| `/admin/camera/test` | POST | admin | Prueba rápida conexión ONVIF | Form: credenciales ONVIF | Redirect | app.py:1910 | — |
| `/api/test_connection` | POST | admin | Test ONVIF con timeout + snapshot RTSP | JSON: `host`, `port`, `username`, `password`, `rtsp_url`, `rtsp_username`, `rtsp_password` | JSON: `{status, is_ptz, snapshot_b64, warning}` | app.py:2056 | Timeout: 6s ONVIF, 7s RTSP |
| `/api/update_model_params` | POST | admin | Actualizar parámetros YOLO en caliente | JSON: `confidence_threshold`, `iou_threshold`, `persistence_frames` | JSON: `{success}` | app.py:2145 | Sin reinicio del servidor |

---

## Stream y detección en vivo

| Ruta | Método | Rol | Propósito | Entrada | Salida | Módulo | Observaciones |
|---|---|---|---|---|---|---|---|
| `/video_feed` | GET | operator | Stream MJPEG anotado | — | `multipart/x-mixed-replace` | app.py:3229 | Requiere cámara RTSP activa |
| `/detection_status` | GET | operator | Estado resumido de detección | — | JSON: estado actual | app.py:3240 | Para badge/UI |
| `/api/camera_status` | GET | operator | Tipo de cámara (PTZ/fija) + estado RTSP | — | JSON: `{camera_type, configured_is_ptz, rtsp}` | app.py:3248 | — |
| `/api/get_camera_status` | GET | Autenticado | Tipo de cámara desde archivo JSON | — | JSON: `{camera_type, configured_is_ptz}` | app.py:3278 | Fuente: `config_camara.json` |

---

## Control PTZ

| Ruta | Método | Rol | Propósito | Entrada | Salida | Módulo | Observaciones |
|---|---|---|---|---|---|---|---|
| `/ptz_move` | POST | operator | Movimiento PTZ (joystick/vector) | JSON: `{direction}` o `{x, y, zoom, duration_s}` | JSON: `{ok}` | app.py:3401 | 403 si no es cámara PTZ |
| `/api/ptz_stop` | POST | operator | Detener PTZ | JSON: `{source, disable_tracking}` | JSON: `{ok, auto_tracking_enabled}` | app.py:3453 | Stop manual desactiva tracking |
| `/api/inspection_test_move` | POST | operator | Movimiento de prueba directo (diagnóstico) | — | JSON: `{ok}` | app.py:3496 | Sin pasar por cola del worker |

---

## Tracking e inspección automática

| Ruta | Método | Rol | Propósito | Entrada | Salida | Módulo | Observaciones |
|---|---|---|---|---|---|---|---|
| `/api/auto_tracking` | GET, POST | operator | Leer o actualizar flag de tracking automático | POST JSON: `{enabled}` | JSON: `{enabled}` | app.py:3290 | Solo efectivo si PTZ disponible |
| `/api/inspection_mode` | GET, POST | operator | Leer o actualizar modo de inspección | POST JSON: `{enabled}` | JSON: `{enabled}` | app.py:3320 | Solo efectivo si PTZ disponible |

---

## Análisis manual (imagen/video)

| Ruta | Método | Rol | Propósito | Entrada | Salida | Módulo | Observaciones |
|---|---|---|---|---|---|---|---|
| `/upload_detect` | POST | operator | Encolar job de análisis de imagen/video | Form-data: `file` | JSON: `{success, job_id, analysis_root}` | app.py:3549 | Lanza hilo asíncrono |
| `/video_progress` | GET | operator | Consultar progreso/resultado de un job | `?job_id=<id>` | JSON: `{progress, status, done, result_video_url, result_video_playable, ...}` | app.py:3530 | Polling desde frontend |

---

## Eventos y alertas

| Ruta | Método | Rol | Propósito | Entrada | Salida | Módulo | Observaciones |
|---|---|---|---|---|---|---|---|
| `/api/recent_alerts` | GET | Autenticado | Últimas N evidencias visuales | `?limit=N` | JSON: lista de alertas con imagen base64 | app.py:2177 | Para panel de alertas recientes |
| `/api/recent_detection_events` | GET | Autenticado | Últimos N eventos de detección agrupados | `?limit=N&since=<iso>` | JSON: lista de eventos | app.py:2363 | — |
| `/api/export_detection_events.csv` | GET | admin | Exportar eventos como CSV | `?since=<iso>&until=<iso>` | CSV file | app.py:2441 | — |
| `/api/detection_summary` | GET | Autenticado | Resumen estadístico de detecciones | — | JSON: `{total_events, total_detections, avg_confidence, ...}` | app.py:2515 | — |

---

## Gestión de dataset (Admin)

| Ruta | Método | Rol | Propósito | Entrada | Salida | Módulo | Observaciones |
|---|---|---|---|---|---|---|---|
| `/api/get_dataset_images` | GET | admin | Listar imágenes del dataset recolectado | `?folder=<path>` | JSON: lista de imágenes | app.py:2938 | — |
| `/api/dataset_image` | GET | admin | Obtener imagen individual del dataset | `?path=<rel_path>` | Imagen (bytes) o JSON error | app.py:2959 | — |
| `/api/classify_image` | POST | admin | Clasificar imagen como positivo/negativo | JSON: `{filename, label, source_folder}` | JSON: `{success}` | app.py:3009 | Mueve el archivo físicamente |
| `/api/get_classified_images` | GET | admin | Listar imágenes ya clasificadas | — | JSON: lista | app.py:3108 | — |
| `/api/classified_image` | GET | admin | Obtener imagen clasificada individual | `?path=<rel_path>` | Imagen (bytes) | app.py:3129 | — |
| `/api/revert_classification` | POST | admin | Revertir clasificación de imagen | JSON: `{filename, current_label}` | JSON: `{success}` | app.py:3151 | Mueve imagen de vuelta a inbox |
| `/api/admin/cleanup_test_data` | POST | admin | Limpiar datos de prueba | — | JSON: `{success}` | app.py:2591 | Destructivo; requiere confirmación |

---

## Media / archivos

| Ruta | Método | Rol | Propósito | Entrada | Salida | Módulo | Observaciones |
|---|---|---|---|---|---|---|---|
| `/media/<path:rel_path>` | GET | Autenticado | Servir archivos de evidencia/resultados por ruta relativa | path en URL | Archivo binario | app.py:2883 | Valida que la ruta no salga del proyecto |

---

## Diagnóstico

| Ruta | Método | Rol | Propósito | Entrada | Salida | Módulo | Observaciones |
|---|---|---|---|---|---|---|---|
| `/__diag` | GET | — | Diagnóstico rápido del servidor | — | JSON | app.py:1827 | Solo en `FLASK_DEBUG=True` y localhost |
