# Módulos Funcionales — SIRAN

## 1. Autenticación y control de acceso

**Archivo:** `app.py` (rutas `/login`, `/logout`), `src/system_core.py` (modelo `User`)

**Estado:** Implementado

Implementado con Flask-Login. Los usuarios se almacenan en SQLite (tabla `user`). Se definen dos roles: `admin` y `operator`. El decorador `role_required(*roles)` restringe el acceso a rutas específicas. Las sesiones son volátiles (no persisten al cerrar el navegador).

**Usuarios por defecto:**
- `admin` / `admin123` (contraseña configurable por `DEFAULT_ADMIN_PASSWORD`)
- `operador` / `operador123` (contraseña configurable por `DEFAULT_OPERATOR_PASSWORD`)

**Limitaciones:**
- No implementa 2FA
- Las contraseñas por defecto deben cambiarse en producción
- No implementa expiración de sesión por inactividad

---

## 2. Detección YOLO en vivo

**Archivo:** `app.py` (inicialización), `src/video_processor.py` (LiveVideoProcessor), `src/system_core.py`

**Estado:** Implementado

El modelo YOLO (Ultralytics v8/v9) se carga al inicio del servidor. La inferencia se aplica a cada frame del stream RTSP (o cada N frames según `INFERENCE_INTERVAL`). Los resultados se dibujan sobre el frame con `draw_detections`. La confianza y los bounding boxes se persisten en `inference_frames`.

**Parámetros en caliente:** `confidence_threshold`, `iou_threshold`, `persistence_frames` (ajustables por el administrador sin reiniciar el servidor).

**Priorización:** ante múltiples detecciones, se selecciona el bounding box de mayor área (estrategia de enjambre).

---

## 3. Análisis manual de imagen

**Archivo:** `app.py` (_process_image_and_persist, upload_detect)

**Estado:** Implementado

El operador sube una imagen (JPG/PNG). El servidor aplica YOLO a la imagen, dibuja los bounding boxes y guarda el resultado en `static/results/result_<job_id>.jpg`. El frontend muestra la imagen resultante con conteo de detecciones y confianza promedio.

---

## 4. Análisis manual de video

**Archivo:** `app.py` (_process_video_and_persist), `src/services/video_export_service.py`

**Estado:** Implementado

El operador sube un video (MP4/AVI/MOV). El servidor lo procesa frame a frame con YOLO y genera:
- Un video anotado raw (`result_<job_id>_raw.mp4`) con codec mp4v/XVID/MJPG
- Un video compatible con navegador (`result_<job_id>_browser.mp4`) vía FFmpeg si disponible
- Top 10 frames de mayor confianza (imágenes con y sin bounding box)
- Métricas: frames procesados, total detecciones, confianza promedio

El progreso se consulta por polling desde el frontend.

**Dependencia crítica:** FFmpeg para reproducción en navegador (sin FFmpeg, solo descarga).

---

## 5. Video en vivo (stream MJPEG)

**Archivo:** `src/video_processor.py` (RTSPLatestFrameReader, LiveVideoProcessor)

**Estado:** Implementado

`RTSPLatestFrameReader` mantiene un hilo dedicado que lee frames de la cámara vía RTSP (OpenCV VideoCapture). `LiveVideoProcessor` procesa los frames (inferencia YOLO + dibujo) y los sirve como stream MJPEG. La ruta `/video_feed` usa `Response` con `multipart/x-mixed-replace`.

**Comportamiento ante desconexión:** intento de reconexión automática.

---

## 6. Control PTZ manual

**Archivo:** `app.py` (ptz_move, ptz_stop), `src/system_core.py` (PTZWorker, PTZController)

**Estado:** Implementado

El frontend envía comandos de movimiento (vector `x, y, zoom` o dirección predefinida) a `/ptz_move`. El comando se encola en `PTZWorker`. El worker procesa los comandos secuencialmente y los envía a la cámara vía ONVIF usando `PTZController.continuous_move`. La velocidad máxima está limitada a `PTZ_MAX_SPEED`.

**Bloqueo de seguridad:** si la cámara no está configurada como PTZ o ONVIF no respondió, las rutas PTZ retornan HTTP 403.

---

## 7. Tracking automático

**Archivo:** `app.py` (api_auto_tracking, lógica en LiveVideoProcessor)

**Estado:** Implementado

Cuando el tracking automático está activo, el `LiveVideoProcessor` calcula el desplazamiento del bounding box más grande respecto al centro del frame. Si el desplazamiento supera la tolerancia configurada (`PTZ_TOLERANCE_FRAC`), encola un movimiento correctivo en el `PTZWorker`. Esto centra continuamente la cámara sobre el objeto detectado.

**Limitaciones:**
- Requiere cámara PTZ + ONVIF activo
- No implementa filtrado de posición (Kalman u otro); puede oscilar con detecciones ruidosas
- La latencia ONVIF puede causar sobrecompensación a velocidades altas

---

## 8. Inspección automática (patrullaje)

**Archivo:** `app.py` (api_inspection_mode, lógica en PTZWorker)

**Estado:** Implementado (parcialmente — el barrido usa un sweep angular básico)

El modo de inspección ejecuta un barrido horizontal continuo de la cámara (izquierda-derecha) de forma autónoma. Si durante el barrido se detecta un objetivo, el tracking toma prioridad. La velocidad y duración del barrido son configurables (`PTZ_SWEEP_SPEED`, `PTZ_SWEEP_DURATION_S`, `PTZ_IDLE_S`).

**Limitación:** el barrido es lineal simple, no implementa patrones de cobertura inteligentes.

---

## 9. Eventos de detección

**Archivo:** `src/system_core.py` (DetectionEventWriter), `app.py` (api_recent_detection_events, api_export_detection_events_csv)

**Estado:** Implementado

Las detecciones confirmadas (N frames consecutivos) se agrupan en eventos. Un evento permanece "abierto" mientras las detecciones continúen dentro de un gap temporal (3 segundos por defecto). Al superar el gap, el evento se "cierra". Cada evento registra:
- Inicio y fin (ISO timestamps)
- Confianza máxima
- Conteo total de detecciones en el evento
- Mejor bounding box
- Ruta de mejor evidencia visual

Los eventos se pueden exportar como CSV.

---

## 10. Evidencias visuales

**Archivo:** `app.py` (generación inline en LiveVideoProcessor)

**Estado:** Implementado

Cuando una detección es confirmada, se guarda una imagen JPEG en `static/evidence/` con timestamp y confianza en el nombre de archivo (ej: `evidence_20260506_144404_626485_conf88.jpg`). Las evidencias son accesibles al operador en el panel de alertas recientes. No se borran automáticamente.

**Riesgo:** acumulación indefinida de archivos en `static/evidence/`. No hay política de retención automática.

---

## 11. Gestión de dataset

**Archivo:** `app.py` (api_get_dataset_images, api_classify_image, api_get_classified_images, api_revert_classification)

**Estado:** Implementado

El sistema recolecta automáticamente imágenes durante el análisis de video (frames de mayor confianza, con y sin bounding box). El administrador puede clasificarlas manualmente como positivas o negativas para alimentar el pipeline de reentrenamiento del modelo.

**Pendiente:** automatización del proceso de reentrenamiento (el pipeline de YOLO training debe ejecutarse manualmente fuera del sistema).

---

## 12. Exportación de resultados

**Archivo:** `src/services/video_export_service.py`, `app.py` (api_export_detection_events_csv)

**Estado:** Implementado

- Imágenes de análisis: guardadas en `static/results/`
- Videos anotados: guardados en `static/results/`
- Eventos: exportables como CSV vía `/api/export_detection_events.csv`
- Evidencias: accesibles en `static/evidence/`
- Top detecciones: guardadas en `static/top_detections/` o en `dataset_recoleccion/`

---

## 13. Configuración de cámara

**Archivo:** `app.py` (admin_camera, api_test_connection), `config.py`

**Estado:** Implementado

La configuración RTSP/ONVIF se persiste en SQLite (`camera_config`) y en `config_camara.json` (fuente de verdad local para el tipo PTZ/fija). Las variables de entorno actúan como valores por defecto al crear el registro inicial.

---

## 14. Frontend web

**Archivos:** `templates/`, `static/*.js`, `static/style.css`

**Estado:** Implementado

La interfaz usa HTML5 + JavaScript vanilla (sin framework frontend). El tema visual es verde neón sobre fondo oscuro. El joystick PTZ es un canvas interactivo. El panel de alertas se actualiza por polling. El reproductor de video usa el elemento `<video>` nativo del navegador.

**Pendiente de mejora:** no tiene diseño responsive para móvil; el joystick puede ser difícil de usar en pantallas táctiles.
