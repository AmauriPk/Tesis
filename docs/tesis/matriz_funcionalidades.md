# Matriz de Funcionalidades — SIRAN

| Funcionalidad | Estado | Archivo / Módulo | Evidencia sugerida | Observaciones |
|---|---|---|---|---|
| Autenticación con usuario y contraseña | implementado | `app.py:1796`, `src/system_core.py` (User) | Captura de pantalla de login exitoso | Flask-Login + SQLAlchemy |
| Control de acceso por roles (admin/operator) | implementado | `app.py` (role_required) | Verificar que operador no accede a `/admin_dashboard` | Dos roles implementados |
| Stream de video en vivo (RTSP → MJPEG) | implementado | `src/video_processor.py` (RTSPLatestFrameReader, LiveVideoProcessor) | Captura del stream en navegador | Requiere cámara RTSP |
| Inferencia YOLO en tiempo real | implementado | `app.py` (load_yolo_model), `src/video_processor.py` | Frame con bounding boxes sobre dron | Requiere modelo `.pt` entrenado |
| Selección dinámica de device (GPU/CPU) | implementado | `app.py:253` (load_yolo_model) | Log `[SUCCESS] Modelo YOLO cargado en device=cuda:0` | Fallback a CPU automático |
| Ajuste de parámetros YOLO en caliente | implementado | `app.py:2145` (api_update_model_params) | Panel admin: slider de confianza actualiza sin reiniciar | Sin reinicio del servidor |
| Persistencia de frames N (mitigación de aves) | implementado | `config.py` (VISION_MODEL_PARAMS), `src/video_processor.py` | — | `persistence_frames` configurable |
| Análisis manual de imagen | implementado | `app.py:3638` (_process_image_and_persist) | Imagen con bounding box | JPG/PNG soportado |
| Análisis manual de video | implementado | `app.py:3848` (_process_video_and_persist) | Video anotado en navegador | MP4/AVI/MOV soportado |
| Exportación de video a H.264 (navegador) | implementado | `src/services/video_export_service.py` | `result_video_playable: true` | Requiere FFmpeg; fallback a descarga |
| Top 10 frames de mayor confianza (video) | implementado | `app.py:3880` | Galería de thumbnails en UI | Se guardan en dataset_recoleccion/ |
| Control PTZ manual (joystick) | implementado | `app.py:3401` (ptz_move), `src/system_core.py` (PTZWorker) | Video/captura de cámara moviéndose | Requiere cámara ONVIF PTZ |
| Control PTZ por dirección (up/down/left/right) | implementado | `app.py:3401` | Botones de dirección en UI | — |
| Tracking automático de objetivo | implementado | `app.py` (api_auto_tracking), `src/video_processor.py` | Cámara siguiendo al dron | Requiere PTZ |
| Inspección / patrullaje autónomo | implementado | `app.py:3320` (api_inspection_mode), `src/system_core.py` (PTZWorker) | Cámara ejecutando barrido | Barrido lineal básico |
| Autodiscovery ONVIF (detectar si PTZ) | implementado | `app.py` (_probe_onvif_ptz_capability) | Log de resultado en consola | Se ejecuta al inicio y tras cambios |
| Bloqueo de PTZ en cámara fija | implementado | `app.py:3401` (_require_ptz_capable) | HTTP 403 al intentar mover PTZ en cámara fija | — |
| Registro de eventos de detección agrupados | implementado | `src/system_core.py` (DetectionEventWriter) | JSON de `/api/recent_detection_events` | Agrupados por gap temporal |
| Evidencias visuales por detección | implementado | `src/video_processor.py` (save evidence) | Archivos JPG en `static/evidence/` | Sin política de retención automática |
| Telemetría de frames procesados | implementado | `src/system_core.py` (MetricsDBWriter, FrameRecord) | Tabla `inference_frames` en `detections.db` | Alta frecuencia |
| Exportación de eventos en CSV | implementado | `app.py:2441` (api_export_detection_events_csv) | Archivo CSV descargado | — |
| Resumen estadístico de detecciones | implementado | `app.py:2515` (api_detection_summary) | JSON de la API | — |
| Gestión de dataset (clasificación de imágenes) | implementado | `app.py:3009` (api_classify_image) | Imágenes en `dataset_entrenamiento/` | Positivo/negativo |
| Reversión de clasificación de imagen | implementado | `app.py:3151` (api_revert_classification) | — | — |
| Configuración RTSP/ONVIF desde UI | implementado | `app.py:1876` (admin_camera) | Panel de configuración sin credenciales expuestas | Persiste en SQLite + JSON |
| Test de conexión ONVIF con snapshot | implementado | `app.py:2056` (api_test_connection) | `{status: "success", is_ptz: true/false, snapshot_b64}` | Timeout 6s |
| Sistema de autenticación multirole | implementado | `app.py` (role_required, login_manager) | — | — |
| Servicio de archivos de evidencia/resultados | implementado | `app.py:2883` (/media/<path>) | — | Valida path traversal |
| Limpieza de datos de prueba | implementado | `app.py:2591` (api_admin_cleanup_test_data) | — | Solo admin |
| Reentrenamiento automático del modelo | pendiente | — | — | Se requiere ejecución manual de scripts YOLO |
| Alertas externas (email/SMS/webhook) | pendiente | — | — | No implementado en prototipo actual |
| Soporte para múltiples cámaras | pendiente | — | — | Arquitectura actual soporta 1 cámara |
| Cifrado HTTPS/TLS | pendiente | — | — | No implementado; requiere proxy reverso o certificado SSL |
| Diseño responsive para móvil | parcialmente implementado | `static/style.css` | — | Interfaz funcional en desktop; no optimizada para móvil |
| Tracking predictivo (Kalman) | pendiente | — | — | Tracking actual es reactivo puro |
| Análisis de trayectoria de dron | pendiente | — | — | No implementado |
| Autenticación 2FA | pendiente | — | — | No implementado en prototipo |
| Política de retención de evidencias | pendiente | — | — | Acumulación indefinida actualmente |
| Política de retención de resultados | pendiente | — | — | Acumulación indefinida actualmente |
| Pruebas automatizadas | pendiente | — | — | `pytest` en requirements pero sin tests escritos |
| Documentación OpenAPI/Swagger | pendiente | `docs/tesis/mapa_endpoints.md` | — | Documentado solo en Markdown |
