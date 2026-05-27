# Manual Técnico del Sistema SIRAN
**Sistema de Identificación y Rastreo de Aeronaves No Tripuladas**

> Documento elaborado como Apéndice Técnico de Tesis de Grado.
> Describe la arquitectura, instalación, configuración y operación del sistema.

---

## Tabla de Contenidos

1. [Descripción del Sistema](#1-descripción-del-sistema)
2. [Requisitos del Sistema](#2-requisitos-del-sistema)
3. [Instalación y Configuración Inicial](#3-instalación-y-configuración-inicial)
4. [Variables de Entorno](#4-variables-de-entorno)
5. [Estructura de Archivos del Proyecto](#5-estructura-de-archivos-del-proyecto)
6. [Módulos del Sistema](#6-módulos-del-sistema)
7. [API REST — Referencia de Endpoints](#7-api-rest--referencia-de-endpoints)
8. [Panel de Administración](#8-panel-de-administración)
9. [Modelo de Roles y Seguridad](#9-modelo-de-roles-y-seguridad)
10. [Ajuste de Parámetros del Modelo](#10-ajuste-de-parámetros-del-modelo)
11. [Control PTZ — Configuración y Operación](#11-control-ptz--configuración-y-operación)
12. [Gestión de Evidencias y Dataset](#12-gestión-de-evidencias-y-dataset)
13. [Diagnóstico y Resolución de Problemas](#13-diagnóstico-y-resolución-de-problemas)
14. [Requisitos No Funcionales Implementados](#14-requisitos-no-funcionales-implementados)

---

## 1. Descripción del Sistema

SIRAN es una aplicación web en tiempo real para la detección y rastreo automático de aeronaves no tripuladas (UAVs/drones). Integra:

- **Ingesta de video**: captura continua desde cámaras IP (protocolo RTSP).
- **Inferencia de visión**: modelo YOLOv8/v9 entrenado para la clase RPAS.
- **Rastreo multi-objeto**: algoritmo SORT simplificado con asignación húngara e IoU.
- **Control PTZ automático**: movimiento de cámara para mantener el objetivo encuadrado (control proporcional).
- **Interfaz web**: dashboard en vivo con feed MJPEG, alertas, histórico y configuración.
- **Persistencia**: SQLite WAL con métricas por frame, detecciones y eventos agrupados.

### 1.1 Requisitos Funcionales Implementados

| Código | Descripción |
|--------|-------------|
| RF-01 | Conexión a cámara IP por RTSP en < 5 s con reconexión automática |
| RF-02 | Detección de UAVs en tiempo real con YOLOv8/v9 |
| RF-03 | Tracking multi-objeto con IDs persistentes entre frames |
| RF-04 | Control automático PTZ para centrar al objetivo detectado |
| RF-05 | Dashboard web con feed MJPEG y estado del sistema en tiempo real |
| RF-06 | Historial de detecciones con evidencia fotográfica |
| RF-07 | Análisis offline de imágenes y videos subidos |
| RF-08 | Gestión de dataset para reentrenamiento del modelo |
| RF-09 | Autenticación con roles (Admin / Operador) |
| RF-10 | Configuración de cámara desde la interfaz web |

### 1.2 Requisitos Operacionales (RO)

| Código | Descripción |
|--------|-------------|
| RO-03 | Zona de tolerancia central ±15%: no mover PTZ si el objetivo ya está centrado |
| RO-04 | TTL de objetivo = 3 s; readquisición activa de 8 pasos si se pierde el target |
| RO-05 | Control proporcional: `pan = k_pan × error_x`, `tilt = -k_tilt × error_y` |
| RO-06 | Continuidad IoU: verificar solapamiento ≥ 0.50 entre frames consecutivos para evitar saltos |

---

## 2. Requisitos del Sistema

### 2.1 Hardware

| Componente | Mínimo | Recomendado |
|------------|--------|-------------|
| CPU | Intel i5 / AMD Ryzen 5 (4 núcleos) | Intel i7 / Ryzen 7 (8 núcleos) |
| RAM | 8 GB | 16 GB |
| GPU | NVIDIA GTX 1060 (CUDA 11+) | NVIDIA RTX 3060 o superior |
| Almacenamiento | 20 GB libres | 100 GB SSD |
| Red | 100 Mbps (para RTSP H.264) | Gigabit Ethernet |

> **Nota:** El sistema puede funcionar en CPU (`YOLO_DEVICE=cpu`) pero la latencia de inferencia aumentará significativamente (~10× respecto a GPU).

### 2.2 Software

| Dependencia | Versión probada |
|-------------|-----------------|
| Python | 3.10 – 3.12 |
| CUDA Toolkit | 11.8 / 12.1 |
| FFmpeg | 6.x (opcional, para exportación de video) |
| OpenCV | 4.8+ |
| Ultralytics | 8.x |
| Flask | 3.x |

### 2.3 Cámara

- Protocolo de ingesta: **RTSP** (H.264 o MJPEG).
- Control PTZ (opcional): **ONVIF Profile S** — protocolo SOAP sobre HTTP/TCP.
- Resolución recomendada: 1280×720 (720p) o superior.

---

## 3. Instalación y Configuración Inicial

### 3.1 Clonar y Preparar Entorno

```bash
git clone <repositorio> siran
cd siran
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate
pip install -r requirements.txt
```

### 3.2 Generar Clave de Cifrado

Las credenciales de cámara (RTSP/ONVIF) se almacenan cifradas con Fernet:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copiar el resultado y asignarlo a la variable `SIRAN_ENCRYPT_KEY` en el archivo `.env` o en el entorno.

> **Advertencia crítica:** Si se cambia `SIRAN_ENCRYPT_KEY` después de haber guardado credenciales, éstas no podrán descifrarse. Mantener la clave en un lugar seguro y persistente.

### 3.3 Configurar Variables de Entorno

Crear un archivo `.env` en la raíz del proyecto (o exportar las variables en la shell):

```dotenv
# Cámara
RTSP_URL=rtsp://192.168.1.100:554/stream1
RTSP_USERNAME=admin
RTSP_PASSWORD=contraseña_rtsp

# Cifrado
SIRAN_ENCRYPT_KEY=<clave_fernet_generada>

# ONVIF PTZ (opcional)
ONVIF_HOST=192.168.1.100
ONVIF_PORT=80
ONVIF_USERNAME=admin
ONVIF_PASSWORD=contraseña_onvif

# Modelo YOLO
YOLO_MODEL_PATH=runs/detect/weights/best.pt
YOLO_DEVICE=cuda:0
YOLO_CONFIDENCE=0.8

# Flask
FLASK_PORT=5000
FLASK_HOST=0.0.0.0
FLASK_SECRET_KEY=<cadena_aleatoria_larga>
```

### 3.4 Inicializar la Base de Datos

Al primer arranque, Flask-SQLAlchemy crea `app.db` automáticamente junto con el usuario administrador por defecto:

- **Usuario:** `admin`
- **Contraseña:** `admin123` *(cambiar inmediatamente en producción)*

```bash
flask run
# o con gunicorn en producción:
gunicorn -w 1 -b 0.0.0.0:5000 --timeout 120 app:app
```

> El sistema usa un único worker (`-w 1`) porque el estado se mantiene en memoria. Escalar horizontalmente requiere externalizar el estado a Redis o similar.

### 3.5 Acceder a la Interfaz

Abrir `http://localhost:5000` en el navegador. Iniciar sesión con las credenciales de administrador.

---

## 4. Variables de Entorno

### 4.1 Cámara y Video

| Variable | Default | Descripción |
|----------|---------|-------------|
| `RTSP_URL` | `"0"` | URL RTSP completa o índice de webcam (`0`, `1`...) |
| `RTSP_USERNAME` | `usuario` | Usuario de autenticación RTSP |
| `RTSP_PASSWORD` | `password` | Contraseña RTSP |
| `RTSP_TIMEOUT` | `5` | Timeout de conexión RTSP en segundos |
| `RTSP_BUFFER_SIZE` | `1` | Buffer de OpenCV (1 = drop frames para baja latencia) |
| `VIDEO_WIDTH` | `1280` | Resolución de procesamiento (ancho) |
| `VIDEO_HEIGHT` | `720` | Resolución de procesamiento (alto) |
| `VIDEO_FPS` | `30` | FPS objetivo del stream |
| `JPEG_QUALITY` | `80` | Calidad de compresión JPEG del stream MJPEG (0-100) |
| `INFERENCE_INTERVAL` | `1` | Ejecutar YOLO cada N frames (1 = todos) |

### 4.2 Modelo YOLO

| Variable | Default | Descripción |
|----------|---------|-------------|
| `YOLO_MODEL_PATH` | `runs/detect/weights/best.pt` | Ruta al modelo `.pt` entrenado |
| `YOLO_DEVICE` | `cuda:0` | Dispositivo de inferencia (`cuda:0`, `cpu`) |
| `YOLO_CONFIDENCE` | `0.8` | Umbral mínimo de confianza |
| `YOLO_VERBOSE` | `false` | Mostrar output de Ultralytics en consola |
| `IOU_CLAMP_MIN` | `0.10` | Mínimo IoU para NMS (deduplicación) |
| `IOU_CLAMP_MAX` | `0.95` | Máximo IoU para NMS |

### 4.3 Control PTZ

| Variable | Default | Descripción |
|----------|---------|-------------|
| `ONVIF_HOST` | `""` | IP/hostname de la cámara PTZ |
| `ONVIF_PORT` | `80` | Puerto ONVIF (no confundir con RTSP 554) |
| `PTZ_TRACKING_TARGET_TTL` | `3.0` | Segundos hasta perder objetivo (RO-04) |
| `PTZ_TRACKING_TOLERANCE` | `0.15` | Zona central sin movimiento ±15% (RO-03) |
| `PTZ_K_PAN` | `0.8` | Ganancia proporcional de pan (RO-05) |
| `PTZ_K_TILT` | `0.8` | Ganancia proporcional de tilt (RO-05) |
| `PTZ_TRACKING_MAX_SPEED` | `0.50` | Velocidad máxima PTZ (0.0 – 1.0) |
| `PTZ_TRACKING_MIN_SPEED` | `0.12` | Velocidad mínima PTZ |
| `PTZ_INVERT_PAN` | `false` | Invertir eje de pan (hardware-specific) |
| `PTZ_INVERT_TILT` | `false` | Invertir eje de tilt |
| `PTZ_REACQ_ENABLED` | `true` | Activar readquisición activa tras pérdida |
| `PTZ_REACQ_DURATION_S` | `3.0` | Duración total del barrido de readquisición |
| `PTZ_INSPECTION_IDLE_S` | `10.0` | Segundos sin detección para activar patrullaje |
| `PTZ_INSPECTION_MODE` | `sweep` | Modo: `sweep` (izq↔der) o `continuous_360` |
| `PTZ_INSPECTION_SPEED` | `0.45` | Velocidad de patrullaje |
| `PTZ_INSPECTION_CONTINUOUS_360` | `false` | Activar rotación continua en modo 360° |

### 4.4 Tracker SORT

| Variable | Default | Descripción |
|----------|---------|-------------|
| `TRACKER_IOU_THRESHOLD` | `0.30` | IoU mínimo para asociar detección a track |
| `TRACKER_MAX_MISSES` | `3` | Frames sin match antes de eliminar track |
| `TRACKER_MIN_HITS` | `1` | Hits mínimos para confirmar un track nuevo |

### 4.5 Seguridad y Sesiones

| Variable | Default | Descripción |
|----------|---------|-------------|
| `SIRAN_ENCRYPT_KEY` | `""` | Clave Fernet para credenciales (crítico) |
| `FLASK_SECRET_KEY` | auto | Clave de firma de cookies/sesiones |
| `LOGIN_MAX_ATTEMPTS` | `5` | Intentos fallidos antes de bloquear IP |
| `LOGIN_LOCKOUT_SECONDS` | `60` | Segundos de bloqueo tras exceder intentos |
| `SESSION_IDLE_TIMEOUT_SECONDS` | `900` | Segundos de inactividad para expirar sesión |

### 4.6 Almacenamiento

| Variable | Default | Descripción |
|----------|---------|-------------|
| `SQLITE_DB_PATH` | `detections.db` | Ruta a la base de datos de detecciones |
| `EVIDENCE_DIR` | `static/evidence` | Directorio para imágenes de evidencia |
| `EVIDENCE_MIN_CONFIDENCE` | `0.85` | Confianza mínima para guardar evidencia |
| `EVIDENCE_COOLDOWN_SECONDS` | `5.0` | Cooldown entre guardados de evidencia |
| `EVENT_GAP_SECONDS` | `3.0` | Brecha máxima para agrupar frames en un evento |
| `FFMPEG_BIN` | `""` | Ruta a ffmpeg (si no está en PATH) |

---

## 5. Estructura de Archivos del Proyecto

```
siran/
├── app.py                          # Punto de entrada Flask
├── config.py                       # Configuración global (variables de entorno)
├── requirements.txt
├── instance/
│   ├── app.db                      # SQLite: usuarios y config de cámara
│   └── .secret_key                 # Clave de sesión auto-generada
├── src/
│   ├── system_core.py              # Modelos ORM, PTZController, FrameRecord, utilidades
│   ├── video_processor.py          # Pipeline de video: RTSP → YOLO → MJPEG
│   ├── services/
│   │   ├── bootstrap_service.py    # Arranque: logging, secret key, usuarios
│   │   ├── camera_config_service.py # CRUD de configuración de cámara
│   │   ├── camera_state_service.py  # Persistencia de tipo de cámara (json)
│   │   ├── crypto_service.py        # Cifrado Fernet de credenciales
│   │   ├── detection_event_service.py # Agrupación de detecciones en eventos
│   │   ├── inspection_patrol_service.py # Patrullaje PTZ automático
│   │   ├── model_params_service.py  # Parámetros ajustables del modelo en caliente
│   │   ├── ptz_service.py           # Estado PTZ (flags + objetivo de tracking)
│   │   ├── ptz_worker_service.py    # Cola asíncrona de comandos ONVIF PTZ
│   │   ├── session_security_service.py # Seguridad de sesiones (boot_id, idle)
│   │   ├── tracker_service.py       # Tracker SORT simplificado (IoU + Hungarian)
│   │   ├── tracking_worker_service.py # Control proporcional de seguimiento PTZ
│   │   ├── video_export_service.py  # Exportación de video (OpenCV + FFmpeg)
│   │   └── yolo_model_service.py    # Carga del modelo YOLO
│   └── routes/
│       ├── __init__.py             # Helper get_dep() para inyección de dependencias
│       ├── admin_camera.py         # Configuración y prueba de cámara
│       ├── analysis.py             # Análisis offline asíncrono (imagen/video)
│       ├── auth.py                 # Login/logout con rate limiting
│       ├── automation.py           # Activar/desactivar tracking e inspección
│       ├── dashboard.py            # Feed MJPEG, métricas en vivo e historial
│       ├── dataset.py              # Recolección y clasificación de dataset
│       ├── events.py               # Eventos de detección, alertas, exportación CSV
│       ├── media.py                # Servicio seguro de archivos estáticos/evidencia
│       ├── model_params.py         # Actualización de parámetros del modelo
│       └── ptz_manual.py           # Joystick PTZ manual
├── static/
│   ├── evidence/                   # Imágenes de evidencia guardadas en tiempo real
│   ├── results/                    # Resultados de análisis offline
│   └── top_detections/             # Frames con mayor confianza (análisis)
├── templates/                      # Plantillas Jinja2
├── detections.db                   # SQLite WAL: métricas, detecciones, eventos
├── uploads/                        # Archivos subidos para análisis
├── dataset_recoleccion/            # Dataset anotado en la interfaz
│   └── limpias/                    # Imágenes reclasificadas como negativas
└── dataset_entrenamiento/
    ├── train/images/               # Imágenes negativas para reentrenamiento
    └── pending/images/             # Detecciones pendientes de validación
```

---

## 6. Módulos del Sistema

### 6.1 `src/system_core.py`

Núcleo compartido por todos los módulos. Contiene:

- **`User`**: Modelo ORM de usuario (roles: `admin`, `operator`).
- **`CameraConfig`**: Modelo ORM con credenciales cifradas y `effective_rtsp_url()` para construir la URL con credenciales embebidas.
- **`PTZController`**: Controlador ONVIF lazy-connect. Envía `ContinuousMove` y `Stop`. Se reconecta con Zeep si la conexión falla.
- **`FrameRecord`**: `frozen dataclass` — unidad de información por frame. Campos: `timestamp_iso`, `source`, `inference_ms`, `frame_w/h`, `detections`, `confirmed`, `camera_mode`.
- **`MetricsDBWriter`**: Cola (`maxsize=2000`) + hilo daemon. Persiste `FrameRecord` en `inference_frames` y `detections_v2`.
- **`iou_pair(a, b)`**: IoU entre dos bboxes xyxy.
- **`iou_matrix(tracks, dets)`**: Matriz IoU NxM (NumPy).
- **`select_priority_detection(dets)`**: Selecciona la detección de mayor área (regla de enjambre).
- **`clamp(x, lo, hi)`**: Restricción de valor a rango.
- **`_open_db(path)`**: Abre SQLite en modo WAL con `PRAGMA busy_timeout=5000` para acceso concurrente seguro.

### 6.2 `src/video_processor.py`

Pipeline completo de procesamiento de video:

- **`RTSPLatestFrameReader`**: Hilo daemon que lee frames de `cv2.VideoCapture` y conserva solo el último (drop-frame). Se reconecta automáticamente en caso de pérdida de señal.
- **`DetectionPersistence`**: Exige `N` frames consecutivos con detección para confirmar. Mitiga falsas alarmas por pájaros u objetos efímeros.
- **`LiveVideoProcessor`**: Hilo daemon principal. En cada frame: redimensiona, ejecuta YOLO, deduplicación IoU, SORT tracker, persistencia, guarda evidencia, actualiza el objetivo de tracking para el worker PTZ, publica JPEG para MJPEG.
- **`draw_detections(frame, results)`**: Dibuja bounding boxes y retorna lista de detecciones normalizadas.
- **`dedupe_overlapping_detections(dets, iou_threshold)`**: NMS simplificado por IoU para eliminar cajas redundantes.

### 6.3 `src/services/tracking_worker_service.py`

- **`TrackingPTZWorker`**: Hilo daemon que lee el objetivo del `PTZStateService`, calcula el error de posición en el frame (`error_x`, `error_y`) y envía comandos de movimiento proporcional al `PTZCommandWorker`.
  - Tolerancia central ±15% (RO-03): si el objetivo ya está centrado, envía STOP.
  - TTL del objetivo 3 s (RO-04): si el objetivo es demasiado antiguo, inicia readquisición.
  - Control proporcional (RO-05): `pan = k_pan × error_x`, `tilt = -k_tilt × error_y`.
  - Continuidad IoU (RO-06): verifica que el bbox actual solape ≥ 0.50 con el anterior.

- **`ReacquisitionPattern`**: Ejecuta 8 pasos de barrido angular ±15° para recuperar el objetivo perdido.

### 6.4 `src/services/detection_event_service.py`

Agrupa los `FrameRecord` confirmados en "eventos de detección":

- Un evento agrupa todas las detecciones con separación ≤ `EVENT_GAP_SECONDS` (default 3 s).
- Cuando el gap se supera, el evento se cierra con `status='closed'` y sus métricas finales (`max_confidence`, `detection_count`, `best_bbox_text`, `best_evidence_path`).
- En el primer arranque realiza un **backfill** reconstruyendo eventos a partir de las filas existentes en `detections_v2`.

---

## 7. API REST — Referencia de Endpoints

### 7.1 Autenticación (`/auth`)

| Método | Ruta | Descripción | Rol requerido |
|--------|------|-------------|---------------|
| GET/POST | `/login` | Formulario de login con rate limiting por IP | Público |
| GET | `/logout` | Cierra la sesión activa | Autenticado |

### 7.2 Dashboard (`/`)

| Método | Ruta | Descripción | Rol |
|--------|------|-------------|-----|
| GET | `/` | Dashboard principal con feed MJPEG | Operador+ |
| GET | `/video_feed` | Stream MJPEG (`multipart/x-mixed-replace`) | Operador+ |
| GET | `/api/live_metrics` | JSON con FPS, confianza, estado de cámara | Operador+ |
| GET | `/api/historical_metrics` | JSON con historial de detecciones | Operador+ |
| GET | `/api/camera_status` | Estado de conexión de la cámara | Operador+ |

### 7.3 Control PTZ Manual (`/ptz`)

| Método | Ruta | Descripción | Rol |
|--------|------|-------------|-----|
| POST | `/ptz_move` | Mover cámara en dirección (`up/down/left/right`) | Operador+ |
| POST | `/api/ptz_stop` | Detener movimiento PTZ (desactiva tracking) | Operador+ |

### 7.4 Automatización (`/api`)

| Método | Ruta | Descripción | Rol |
|--------|------|-------------|-----|
| GET | `/api/auto_tracking` | Estado del tracking automático | Operador+ |
| POST | `/api/auto_tracking` | Activar/desactivar tracking | Operador+ |
| GET | `/api/inspection_mode` | Estado del modo inspección | Operador+ |
| POST | `/api/inspection_mode` | Activar/desactivar inspección | Operador+ |

**Body POST:**
```json
{"enabled": true}
```

### 7.5 Configuración de Cámara (`/admin`)

| Método | Ruta | Descripción | Rol |
|--------|------|-------------|-----|
| GET/POST | `/admin/camera` | Ver/guardar configuración de cámara | Admin |
| POST | `/api/admin/test_connection` | Probar conexión RTSP+ONVIF | Admin |
| GET | `/api/admin/snapshot` | Capturar snapshot del stream actual | Admin |
| POST | `/api/admin/detect_ptz` | Forzar redescubrimiento ONVIF PTZ | Admin |

### 7.6 Parámetros del Modelo (`/api`)

| Método | Ruta | Descripción | Rol |
|--------|------|-------------|-----|
| GET | `/api/model_params` | Obtener parámetros actuales | Admin |
| POST | `/api/update_model_params` | Actualizar parámetros en caliente | Admin |

**Parámetros actualizables:**
```json
{
  "confidence_threshold": 0.8,
  "iou_threshold": 0.45,
  "persistence_frames": 3
}
```

### 7.7 Eventos y Alertas (`/api`)

| Método | Ruta | Descripción | Rol |
|--------|------|-------------|-----|
| GET | `/api/recent_alerts` | Últimas imágenes de evidencia | Operador+ |
| GET | `/api/recent_detection_events` | Últimos eventos de detección | Operador+ |
| GET | `/api/export_detections_csv` | Exportar detecciones en CSV | Admin |
| POST | `/api/cleanup_detections` | Limpiar detecciones antiguas | Admin |

### 7.8 Análisis Offline (`/analysis`)

| Método | Ruta | Descripción | Rol |
|--------|------|-------------|-----|
| POST | `/api/analysis/upload` | Subir imagen/video para análisis | Operador+ |
| POST | `/api/analysis/start` | Iniciar análisis de archivo subido | Operador+ |
| GET | `/api/analysis/status/<job_id>` | Consultar estado del análisis | Operador+ |
| GET | `/api/analysis/result/<job_id>` | Obtener resultado del análisis | Operador+ |

### 7.9 Dataset (`/dataset`)

| Método | Ruta | Descripción | Rol |
|--------|------|-------------|-----|
| GET | `/dataset` | Listar imágenes del dataset | Admin |
| POST | `/api/dataset/classify` | Clasificar imagen (positiva/negativa) | Admin |
| POST | `/api/dataset/revert` | Revertir clasificación | Admin |
| DELETE | `/api/dataset/delete` | Eliminar imagen del dataset | Admin |

### 7.10 Media (`/media`)

| Método | Ruta | Descripción | Rol |
|--------|------|-------------|-----|
| GET | `/media/<path>` | Servir archivos de evidencia/resultados | Operador+ |

Todas las rutas de media están protegidas contra path traversal mediante `_safe_join()`.

---

## 8. Panel de Administración

### 8.1 Configuración de Cámara

En `/admin/camera` el administrador configura:

1. **URL RTSP**: URL completa de la cámara IP (p.ej. `rtsp://192.168.1.100:554/stream1`).
2. **Credenciales RTSP**: usuario y contraseña (se cifran con Fernet antes de guardar).
3. **Host ONVIF**: IP para control PTZ.
4. **Puerto ONVIF**: Generalmente 80 u 8080 (no 554, que es RTSP).
5. **Credenciales ONVIF**: pueden ser las mismas que RTSP.
6. **Tipo de cámara**: `fija` o `PTZ` (afecta la visibilidad del joystick en la UI).

Tras guardar, el sistema ejecuta automáticamente el redescubrimiento ONVIF en segundo plano.

### 8.2 Ajuste de Parámetros

En `/admin/model_params` (o via API) el administrador puede ajustar en caliente:

- **Umbral de confianza** (`confidence_threshold`): cuánto de seguro debe estar el modelo para reportar una detección. Rango: 0.10 – 0.99.
- **Umbral IoU NMS** (`iou_threshold`): eliminar cajas solapadas. Rango: 0.10 – 0.95.
- **Frames de persistencia** (`persistence_frames`): N frames consecutivos para confirmar detección. Rango: 1 – 20.

Los cambios toman efecto en el siguiente frame de inferencia, sin reiniciar el servidor.

---

## 9. Modelo de Roles y Seguridad

### 9.1 Roles

| Rol | Capacidades |
|-----|-------------|
| `admin` | Acceso total: configurar cámara, ajustar modelo, gestionar dataset, ver histórico, exportar datos |
| `operator` | Ver dashboard, controlar joystick PTZ, activar/desactivar tracking, ver alertas y análisis |

### 9.2 Mecanismos de Seguridad

| Mecanismo | Descripción |
|-----------|-------------|
| Cifrado de credenciales | Fernet (AES-128-CBC + HMAC-SHA256) — clave `SIRAN_ENCRYPT_KEY` |
| Sesiones no persistentes | `SESSION_PERMANENT = False` — las sesiones no sobreviven al cierre del navegador |
| Idle timeout | Sesiones expiradas por inactividad (default 900 s = 15 min) |
| Boot ID | Sesiones de arranques anteriores invalidadas automáticamente |
| Rate limiting de login | Bloqueo de IP tras 5 intentos fallidos (configurable) |
| Cabeceras HTTP | X-Frame-Options, X-Content-Type-Options, CSP, Referrer-Policy |
| Path traversal | `_safe_join()` valida que los paths de archivos permanezcan en el directorio permitido |

### 9.3 Cambio de Contraseña del Administrador

No existe ruta web para cambio de contraseña en esta versión. Modificar directamente en la base de datos:

```python
# En python shell con contexto de Flask:
from app import app, db
from src.system_core import User
with app.app_context():
    u = User.query.filter_by(username='admin').first()
    u.set_password('nueva_contraseña_segura')
    db.session.commit()
```

---

## 10. Ajuste de Parámetros del Modelo

### 10.1 Configuración del Modelo YOLO

El sistema carga el modelo al arrancar desde `YOLO_MODEL_PATH`. Para usar un modelo reentrenado:

1. Entrenar con Ultralytics: `yolo train data=dataset.yaml model=yolov8s.pt epochs=100`.
2. Copiar `runs/detect/trainX/weights/best.pt` a la ruta configurada.
3. Reiniciar el servidor (el modelo se carga en memoria solo al arranque).

### 10.2 Ajuste Fino en Tiempo de Ejecución

Sin reiniciar el servidor, desde el Panel Admin:

| Parámetro | Efecto de aumentar | Efecto de disminuir |
|-----------|-------------------|---------------------|
| `confidence_threshold` | Menos falsas alarmas, más misses | Más detecciones, más falsos positivos |
| `iou_threshold` NMS | Menos supresión de cajas duplicadas | Más supresión (puede eliminar objetos reales cercanos) |
| `persistence_frames` | Más robusto contra aves/efímeros, más latencia de alarma | Alarmas más rápidas, más sensible a ruido |

### 10.3 Ejemplo: Mitigar Falsas Alarmas por Aves

```
confidence_threshold  →  0.85 (subir desde 0.80)
persistence_frames    →  5    (subir desde 3)
```

---

## 11. Control PTZ — Configuración y Operación

### 11.1 Verificar Compatibilidad ONVIF

1. Ir a `/admin/camera`.
2. Rellenar host, puerto, usuario y contraseña ONVIF.
3. Hacer clic en **"Detectar PTZ"**.
4. El sistema prueba puertos 80, 8000 y 8080 automáticamente.
5. Si tiene éxito, el joystick aparece en el dashboard y los botones de tracking/inspección se habilitan.

### 11.2 Calibración del Control Proporcional

Si la cámara persiste el objetivo pero tiene movimientos bruscos o inestables, ajustar las ganancias:

```dotenv
PTZ_K_PAN=0.6     # reducir para movimientos más suaves
PTZ_K_TILT=0.6
PTZ_TRACKING_MIN_SPEED=0.10
PTZ_TRACKING_MAX_SPEED=0.40
```

Si la cámara subgira (no alcanza a centrar el objetivo):
```dotenv
PTZ_K_PAN=1.0
PTZ_K_TILT=1.0
```

### 11.3 Inversión de Ejes

Algunas cámaras tienen el sentido de pan/tilt invertido respecto al estándar ONVIF:

```dotenv
PTZ_INVERT_PAN=true
PTZ_INVERT_TILT=false
```

### 11.4 Modo de Inspección

Activar desde el dashboard (botón "Modo Inspección") o via API:
```bash
curl -X POST http://localhost:5000/api/inspection_mode \
     -H "Content-Type: application/json" \
     -d '{"enabled": true}'
```

Para inspección 360° continua:
```dotenv
PTZ_INSPECTION_MODE=continuous_360
PTZ_INSPECTION_CONTINUOUS_360=true
PTZ_INSPECTION_SPEED=0.3
```

---

## 12. Gestión de Evidencias y Dataset

### 12.1 Evidencias en Tiempo Real

El sistema guarda automáticamente imágenes de evidencia en `static/evidence/` cuando se detecta un UAV con confianza ≥ `EVIDENCE_MIN_CONFIDENCE` (0.85). El nombre del archivo incluye timestamp y porcentaje de confianza: `evidence_20240115_143022_123456_conf92.jpg`.

Límites configurables:
- `EVIDENCE_MAX_FILES=500`: máximo de archivos en el directorio.
- `EVIDENCE_MAX_AGE_DAYS=30`: eliminar evidencias con más de N días.
- `EVIDENCE_COOLDOWN_SECONDS=5.0`: cooldown entre guardados para no saturar el disco.

### 12.2 Recolección de Dataset

El módulo `/dataset` permite:
1. Ver las imágenes capturadas durante la detección en vivo.
2. Clasificarlas como **positivas** (UAV confirmado) o **negativas** (falsa alarma: pájaro, insecto, etc.).
3. Las positivas van a `dataset_entrenamiento/pending/images/` para revisión.
4. Las negativas van a `dataset_entrenamiento/train/images/` como ejemplos de fondo.

Este flujo alimenta el ciclo de **mejora continua** del modelo.

### 12.3 Exportación de Datos

Desde `/api/export_detections_csv` (rol Admin) se descarga un CSV con:
```
id, timestamp, confidence, x1, y1, x2, y2, class_name, track_id, confirmed, source, camera_mode, image_path
```

---

## 13. Diagnóstico y Resolución de Problemas

### 13.1 El stream de video no aparece

1. Verificar la URL RTSP en `/admin/camera`.
2. Comprobar que la cámara sea accesible desde el servidor: `ping <ip_cámara>`.
3. Probar la URL RTSP con VLC: `Medios > Abrir URL de red > rtsp://...`.
4. Revisar los logs: `logs/siran.log` — buscar `RTSP reconnecting` o `open failed`.

### 13.2 No se detectan drones

1. Verificar que el modelo está cargado: log al arranque `YOLO model loaded`.
2. Bajar el umbral de confianza temporalmente: `YOLO_CONFIDENCE=0.5`.
3. Verificar el dispositivo de inferencia: `YOLO_DEVICE=cpu` si no hay GPU.
4. Comprobar que el modelo tenga la clase RPAS (revisar `model.names`).

### 13.3 El PTZ no responde

1. Verificar conexión: `/admin/camera > Detectar PTZ`.
2. Comprobar que el puerto ONVIF no sea 554 (ese es RTSP).
3. Probar con puerto 8080 si el 80 falla.
4. En desarrollo sin cámara PTZ real: `DEBUG_PTZ_READY=true` simula PTZ como listo (solo para pruebas).

### 13.4 El sistema es lento / baja FPS

1. Usar GPU: `YOLO_DEVICE=cuda:0`.
2. Aumentar el intervalo de inferencia: `INFERENCE_INTERVAL=2` (inferir en 1 de cada 2 frames).
3. Reducir la resolución: `VIDEO_WIDTH=640 VIDEO_HEIGHT=480`.
4. Reducir la calidad JPEG del stream: `JPEG_QUALITY=60`.

### 13.5 Sesión expira constantemente

Aumentar el idle timeout:
```dotenv
SESSION_IDLE_TIMEOUT_SECONDS=3600
```

### 13.6 Credenciales no se pueden descifrar

Ocurre si `SIRAN_ENCRYPT_KEY` cambió. Solución:
1. Reconfigurar las credenciales de cámara desde el Panel Admin (las reencriptará con la clave actual).
2. O restaurar la clave original.

### 13.7 Revisar Logs

```bash
# Logs en tiempo real
tail -f logs/siran.log

# Solo errores
grep ERROR logs/siran.log

# Activar debug PTZ
DEBUG_PTZ_READY=true flask run
```

---

## 14. Requisitos No Funcionales Implementados

| Código | Requisito | Implementación |
|--------|-----------|----------------|
| RNF-01 | Latencia de detección < 500 ms | GPU CUDA, inference_interval ajustable, drop-frame en RTSPLatestFrameReader |
| RNF-02 | Disponibilidad 24/7 | Hilos daemon con reconexión automática RTSP; atexit para shutdown ordenado |
| RNF-03 | Persistencia de datos históricos | SQLite WAL; MetricsDBWriter + DetectionEventWriter asíncronos |
| RNF-04 | Escalabilidad de configuración | Variables de entorno con defaults explícitos; ajuste en caliente de ModelParamsService |
| RNF-05 | Seguridad de acceso | Roles RBAC, Fernet, idle timeout, boot ID, CSP headers, rate limiting |
| RNF-06 | Trazabilidad de detecciones | FrameRecord con track_id (SORT), timestamp ISO, evidencia fotográfica |
| RNF-07 | Portabilidad | Sin dependencias del SO (solo Python + librerías multiplataforma); Windows y Linux probados |

---

*Manual generado automáticamente a partir del código fuente de SIRAN — revisión: mayo 2026.*
