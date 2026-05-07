# Arquitectura del Sistema — SIRAN

## Arquitectura general

SIRAN sigue una arquitectura cliente-servidor monolítica de un solo proceso Python, donde el servidor Flask actúa como orquestador central de todos los subsistemas. Los componentes de visión artificial, control de hardware y persistencia se ejecutan en hilos concurrentes supervisados por el proceso principal.

```
┌─────────────────────────────────────────────────────────────────┐
│                        SIRAN — SERVIDOR                         │
│                                                                 │
│  ┌────────────┐   ┌──────────────┐   ┌───────────────────────┐  │
│  │  Flask Web │   │  YOLO Engine │   │  PTZ Worker           │  │
│  │  (puerto   │   │  (GPU/CPU)   │   │  (hilo daemon)        │  │
│  │   5000)    │   │              │   │                       │  │
│  └─────┬──────┘   └──────┬───────┘   └──────────┬────────────┘  │
│        │                 │                      │               │
│  ┌─────▼──────┐   ┌──────▼───────┐   ┌──────────▼────────────┐  │
│  │  SQLite    │   │ Frame Buffer │   │  ONVIF/PTZController  │  │
│  │  (eventos  │   │ (cola RTSP)  │   │  (onvif-zeep)         │  │
│  │  usuarios) │   │              │   │                       │  │
│  └────────────┘   └──────┬───────┘   └───────────────────────┘  │
│                          │                                      │
│                   ┌──────▼───────┐                              │
│                   │ RTSPReader   │                              │
│                   │ (hilo RTSP)  │                              │
│                   └──────────────┘                              │
└─────────────────────────────────────────────────────────────────┘
         ▲                                              ▲
         │ HTTP/MJPEG                                   │ ONVIF
         ▼                                              ▼
┌─────────────────┐                           ┌─────────────────┐
│  Navegador web  │                           │  Cámara IP PTZ  │
│  (Operador/     │                           │  (RTSP + ONVIF) │
│   Admin)        │◄──────── RTSP ────────────┤                 │
└─────────────────┘                           └─────────────────┘
```

---

## Diagrama de componentes (Mermaid)

```mermaid
graph TD
    A[Navegador Web] -->|HTTP GET/POST| B[Flask App - app.py]
    A -->|MJPEG stream| C[/video_feed]
    B --> D[LiveVideoProcessor]
    B --> E[PTZWorker]
    B --> F[SQLite DB]
    B --> G[MetricsDBWriter]
    D --> H[RTSPLatestFrameReader]
    D --> I[YOLO Model]
    H --> J[Cámara IP - RTSP]
    E --> K[PTZController - ONVIF]
    K --> J
    B --> L[VideoExportService]
    L --> M[FFmpeg]
    F --> N[Usuarios]
    F --> O[CameraConfig]
    G --> P[detections.db]
    P --> Q[inference_frames]
    P --> R[detection_events]
```

---

## Backend Flask

**Archivo principal:** `app.py` (~3800 líneas)

Responsabilidades:
- Definición de todas las rutas Flask
- Inicialización del modelo YOLO
- Inicialización del stream RTSP
- Inicialización del worker PTZ
- Gestión de jobs de análisis manual (hilos por job)
- Gestión de configuración de cámara (DB + archivo JSON)
- Control de acceso (roles: admin, operator)

Módulos de soporte:
- `src/system_core.py`: Modelos SQLAlchemy, PTZController, MetricsDBWriter, DetectionEventWriter, utilidades
- `src/video_processor.py`: RTSPLatestFrameReader, LiveVideoProcessor, LiveStreamDeps, draw_detections
- `src/services/video_export_service.py`: create_video_writer, resolve_ffmpeg_bin, make_browser_compatible_mp4, is_valid_video_file

---

## Frontend web

**Plantillas:** `templates/`

| Archivo | Descripción |
|---|---|
| `login.html` | Formulario de autenticación |
| `index.html` | Dashboard principal del operador |
| `admin.html` | Dashboard del administrador |
| `admin_camera.html` | Panel de configuración de cámara RTSP/ONVIF |

**Scripts JavaScript:** `static/`

| Archivo | Descripción |
|---|---|
| `dashboard.js` | Lógica del operador: stream, tracking, inspección, PTZ joystick, análisis manual |
| `admin_dataset.js` | Gestor de dataset: clasificación de imágenes, revisión |
| `admin_camera.js` | Test de conexión ONVIF, snapshot RTSP |
| `admin_model_params.js` | Actualización de parámetros YOLO en caliente |

---

## Modelo YOLO

- **Librería:** Ultralytics (YOLOv8/v9)
- **Carga dinámica:** GPU (`cuda:0`) si disponible; fallback CPU
- **Ruta del modelo:** configurable por variable de entorno `YOLO_MODEL_PATH`
- **Inferencia en vivo:** aplicada a cada frame del stream RTSP (`inference_interval` configurable)
- **Inferencia offline:** aplicada a imágenes/videos subidos por el operador
- **Parámetros ajustables en caliente:** `confidence_threshold`, `iou_threshold`, `persistence_frames`

---

## Stream RTSP

- **Lector de frames:** `RTSPLatestFrameReader` (hilo dedicado, siempre lee el frame más reciente)
- **Procesador en vivo:** `LiveVideoProcessor` (aplica YOLO, dibuja detecciones, sirve MJPEG)
- **Entrega al cliente:** ruta `/video_feed` como `multipart/x-mixed-replace`
- **Buffer:** tamaño 1 (frame más reciente), configurable por `RTSP_BUFFER_SIZE`

---

## ONVIF / PTZ

- **Protocolo:** ONVIF (WS-Discovery / GetServices / PTZ)
- **Librería:** `onvif-zeep`
- **Auto-Discovery:** en inicio y tras cambios de configuración, el sistema detecta si la cámara soporta PTZ
- **PTZController:** clase en `src/system_core.py`, encapsula `continuous_move` y `stop`
- **PTZWorker:** hilo daemon con cola de comandos (move, stop, direction)
- **Priorización de objetivo:** selecciona el bounding box de mayor área (estrategia enjambre: seguir el dron más grande/cercano)

---

## Base de datos SQLite

**Dos archivos SQLite:**

1. `instance/app.db` (Flask-SQLAlchemy)
   - Tabla `user`: usuarios del sistema (admin, operator)
   - Tabla `camera_config`: configuración RTSP/ONVIF persistida

2. `detections.db` (SQLite directo)
   - Tabla `inference_frames`: telemetría de frames procesados (timestamp, fps, detecciones, confianza)
   - Tabla `detection_events`: eventos agrupados (inicio, fin, confianza máxima, conteo, evidencia mejor)

---

## Eventos / Evidencias

- Los frames con detección confirmada generan una imagen de evidencia en `static/evidence/`
- Los eventos se agrupan por continuidad temporal (gap configurable, default 3 segundos)
- La API `/api/recent_alerts` devuelve las últimas N evidencias
- La API `/api/recent_detection_events` devuelve los últimos N eventos agrupados
- Los eventos se exportan vía `/api/export_detection_events.csv`

---

## Gestión de dataset

- Las imágenes capturadas durante análisis se almacenan en `dataset_recoleccion/`
- El administrador puede clasificarlas como positivas (dron) o negativas (falso positivo) desde `/admin_dashboard`
- Las imágenes clasificadas se mueven a `dataset_entrenamiento/train/images/` (negativas) o `dataset_entrenamiento/pending/images/` (pendientes de revisión)
- Las clasificaciones se pueden revertir

---

## Análisis de video procesado

Flujo de análisis manual de video:
1. Operador sube video → `/upload_detect`
2. Se crea job con `job_id` único
3. Hilo worker procesa frame a frame con YOLO
4. Se escribe video anotado (`result_JOB_raw.mp4`)
5. Si FFmpeg disponible: transcodificación a `result_JOB_browser.mp4` (H.264, yuv420p, faststart)
6. El operador consulta progreso vía polling en `/video_progress`
7. Resultado incluye URL de video, URL raw, mime type, playable flag y warning si aplica
