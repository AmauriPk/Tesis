# Arquitectura del Sistema SIRAN
**Sistema de Identificación y Rastreo de Aeronaves No Tripuladas**

---

## 1. Visión General

SIRAN es una aplicación web en tiempo real construida con Flask que ingiere video de una cámara IP (RTSP), ejecuta un modelo YOLOv8 para detectar aeronaves no tripuladas (UAVs/drones), rastrea los objetivos con un algoritmo SORT simplificado y, si la cámara es PTZ, mueve automáticamente la cámara para mantener el objetivo encuadrado.

El sistema sigue una arquitectura de **capas con hilos daemon**, donde cada capa tiene una responsabilidad única y se comunica con la siguiente a través de colas o estructuras protegidas por locks.

---

## 2. Diagrama de Componentes

```
╔══════════════════════════════════════════════════════════════════════╗
║  NAVEGADOR / CLIENTE                                                  ║
║  ┌────────────────┐  ┌────────────────┐  ┌──────────────────────┐   ║
║  │  Dashboard UI  │  │ Joystick PTZ   │  │ Admin / Config       │   ║
║  │  (MJPEG feed)  │  │  (JS fetch)    │  │ (settings, analysis) │   ║
║  └───────┬────────┘  └──────┬─────────┘  └──────────┬───────────┘   ║
╚══════════╪═══════════════════╪════════════════════════╪══════════════╝
           │ HTTP/MJPEG        │ HTTP JSON              │ HTTP JSON
           ▼                   ▼                        ▼
╔══════════════════════════════════════════════════════════════════════╗
║  CAPA DE RUTAS (Flask Blueprints — request threads)                   ║
║  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  ║
║  │dashboard │ │ptz_manual│ │automation│ │admin_cam │ │  auth    │  ║
║  ├──────────┤ ├──────────┤ ├──────────┤ ├──────────┤ ├──────────┤  ║
║  │ analysis │ │  events  │ │  media   │ │ dataset  │ │model_pars│  ║
║  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘  ║
╚══════════════════════════════════════════════════════════════════════╝
           │ deps inyectadas en init_X_routes()
           ▼
╔══════════════════════════════════════════════════════════════════════╗
║  CAPA DE SERVICIOS (singletons, estado compartido)                    ║
║                                                                       ║
║  ┌──────────────────┐    ┌─────────────────────┐                     ║
║  │ PTZStateService  │    │ PTZCapabilityService │                     ║
║  │ (flags + target) │    │ (ONVIF probe)        │                     ║
║  └────────┬─────────┘    └──────────────────────┘                    ║
║           │ target_lock                                               ║
║  ┌────────▼──────────────────────────────────────────────────────┐   ║
║  │ ModelParamsService  │ SessionSecurityService │ CameraConfig…  │   ║
║  └───────────────────────────────────────────────────────────────┘   ║
╚══════════════════════════════════════════════════════════════════════╝
           │
           ▼
╔══════════════════════════════════════════════════════════════════════╗
║  CAPA DE WORKERS (hilos daemon — procesamiento asíncrono)             ║
║                                                                       ║
║  ┌───────────────────┐  ┌──────────────────┐  ┌──────────────────┐  ║
║  │RTSPLatestFrame    │  │ LiveVideoProcessor│  │ MetricsDBWriter  │  ║
║  │Reader             │  │ (inferencia YOLO) │  │ (queue → SQLite) │  ║
║  │(drop-frame hilo)  │  │ SORT Tracker      │  └──────────────────┘  ║
║  └────────┬──────────┘  └────────┬──────────┘  ┌──────────────────┐  ║
║           │ frame np.ndarray     │ confirmed    │ DetectionEvent   │  ║
║           └──────────────────────┘              │ Writer           │  ║
║                                                  └──────────────────┘  ║
║  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐   ║
║  │ PTZCommandWorker │◄─│ TrackingPTZWorker│  │ InspectionPatrol │   ║
║  │ (cola ONVIF PTZ) │  │ (control prop.)  │  │ Worker (barrido) │   ║
║  └──────────────────┘  └──────────────────┘  └──────────────────┘   ║
╚══════════════════════════════════════════════════════════════════════╝
           │
           ▼
╔══════════════════════════════════════════════════════════════════════╗
║  CAPA DE PERSISTENCIA                                                 ║
║                                                                       ║
║  ┌──────────────────────┐      ┌──────────────────────────────────┐  ║
║  │     app.db           │      │         detections.db            │  ║
║  │  (SQLAlchemy ORM)    │      │       (SQLite WAL directo)       │  ║
║  │  · users             │      │  · inference_frames              │  ║
║  │  · camera_config     │      │  · detections_v2                 │  ║
║  └──────────────────────┘      │  · detection_events              │  ║
║                                └──────────────────────────────────┘  ║
╚══════════════════════════════════════════════════════════════════════╝
           │
           ▼
╔══════════════════════════════════════════════════════════════════════╗
║  HARDWARE / RED                                                       ║
║  ┌──────────────────────┐      ┌──────────────────────────────────┐  ║
║  │  Cámara IP (RTSP)    │      │  Cámara PTZ (ONVIF/TCP)          │  ║
║  │  H.264 / MJPEG       │      │  pan · tilt · zoom               │  ║
║  └──────────────────────┘      └──────────────────────────────────┘  ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## 3. Módulos del Sistema

### 3.1 Punto de Entrada (`app.py`)

Crea la aplicación Flask, instancia **todos los servicios y workers** en orden correcto (dependencias primero), registra los 10 blueprints con inyección de dependencias explícita (`init_X_routes(**deps)`) y registra un handler `atexit` para shutdown ordenado.

Hooks globales:
- `before_request → _volatile_sessions`: invalida sesiones inactivas o de arranques anteriores.
- `after_request → set_security_headers`: añade cabeceras de seguridad HTTP (X-Frame-Options, CSP, etc.).

### 3.2 Configuración (`config.py`)

Fuente de verdad de toda la configuración. Lee variables de entorno con valores por defecto. Expone diccionarios tipados:

| Diccionario | Propósito |
|---|---|
| `RTSP_CONFIG` | URL, timeout y buffer RTSP |
| `ONVIF_CONFIG` | Host, puerto, credenciales ONVIF |
| `YOLO_CONFIG` | Ruta del modelo, dispositivo, umbral de confianza |
| `PTZ_CONFIG` | Ganancias de tracking, tolerancia, inspección |
| `STORAGE_CONFIG` | Rutas de DB, evidencia, dataset |
| `SECURITY_CONFIG` | Clave Fernet, idle timeout, flags debug |
| `TRACKER_CONFIG` | IoU threshold, max_misses, min_hits |
| `APP_CONFIG` | URL de DB, métricas habilitadas |
| `FLASK_CONFIG` | Debug, max_content_length |
| `VIDEO_CONFIG` | Resolución, FPS, intervalo de inferencia |

### 3.3 Núcleo del Sistema (`src/system_core.py`)

Contiene todas las clases y utilidades compartidas:

- **Modelos ORM**: `User` (admin/operator), `CameraConfig` (credenciales cifradas).
- **`PTZController`**: Controlador ONVIF lazy-connect; envía `ContinuousMove` y `Stop` a la cámara.
- **`FrameRecord`**: `frozen dataclass` — moneda de intercambio entre el hilo de video y los escritores de DB.
- **`MetricsDBWriter`**: Worker con cola que persiste `inference_frames` y `detections_v2` en lotes.
- **`iou_pair` / `iou_matrix`**: Cálculo de Intersección sobre Unión (IoU) para SORT y deduplicación.
- **`clamp`, `select_priority_detection`**: Utilidades matemáticas compartidas.
- **`_open_db`**: Abre SQLite con `WAL + PRAGMA journal_mode` para acceso concurrente seguro.

---

## 4. Pipeline de Video e Inferencia

```
[Cámara RTSP]
      │  stream H.264
      ▼
[RTSPLatestFrameReader] ──── hilo daemon ────►  _frame (np.ndarray, lock)
      │                                               │
      │                                               ▼
      │                              [LiveVideoProcessor] ── hilo daemon
      │                                    │
      │                        ┌───────────┼────────────────────────┐
      │                        │           │                        │
      │                  cv2.resize   YOLO.predict()          overlay_fps()
      │                        │           │
      │                        │     draw_detections()
      │                        │     dedupe_overlapping_detections()  (IoU NMS)
      │                        │     SORTTracker.update()            (IoU Hungarian)
      │                        │     DetectionPersistence.update()   (N frames)
      │                        │           │
      │                        │     ┌─────┴──────────────────────────┐
      │                        │     │  confirmed=True                │
      │                        │     ▼                                ▼
      │                        │  _save_evidence()        _update_tracking_target()
      │                        │     │                         │
      │                        │     └──────► detections/      │
      │                        │              evidence_*.jpg   ▼
      │                        │                         [PTZStateService]
      │                        │                              │
      │                  cv2.imencode(.jpg)                   ▼
      │                        │                    [TrackingPTZWorker]
      │                        ▼                         (control prop.)
      │               _latest_jpeg (lock)                     │
      │                        │                              ▼
      │                        ▼                    [PTZCommandWorker]
      │               mjpeg_generator()              (cola ONVIF PTZ)
      │                        │                              │
      │                        ▼                              ▼
      │               Cliente MJPEG                    [Cámara PTZ]
      │
      └──── FrameRecord ──► [MetricsDBWriter] ──► detections.db
                         └──► [DetectionEventWriter] ──► detection_events
```

### 4.1 Confirmación por Persistencia (Mitigación de aves)

`DetectionPersistence` exige `N` frames consecutivos con detección antes de marcar `confirmed=True`. El valor de `N` se ajusta en caliente desde `ModelParamsService` (Panel Admin) sin reiniciar el sistema.

### 4.2 Tracker SORT Simplificado

`SORTTracker` (en `src/services/tracker_service.py`) asigna IDs persistentes a detecciones entre frames usando la asignación húngara (`scipy.optimize.linear_sum_assignment`) sobre una matriz de costos `1 - IoU`. Sin filtro de Kalman. Se reinicia automáticamente al detectar reconexión RTSP para evitar IDs obsoletos.

---

## 5. Control PTZ Automático

### 5.1 Flujo de Control

```
LiveVideoProcessor
    │  update_tracking_target({bbox, frame_w, frame_h, ...})
    ▼
PTZStateService.tracking_target_state  (dict protegido por Lock)
    │
    ▼
TrackingPTZWorker  (hilo daemon, poll cada command_interval=0.35 s)
    │
    ├─ 1. ¿target reciente? (TTL=3 s, RO-04)
    ├─ 2. ¿bbox en zona de tolerancia ±15%? (RO-03) → STOP si sí
    ├─ 3. Calcular error_x = cx/W - 0.5,  error_y = cy/H - 0.5
    ├─ 4. pan_cmd  =  k_pan  * error_x    (RO-05)
    │     tilt_cmd = -k_tilt * error_y
    ├─ 5. Aplicar inversión de ejes (PTZ_INVERT_PAN/TILT)
    └─ 6. enqueue_move(x=pan_cmd, y=tilt_cmd, source="tracking")
              │
              ▼
         PTZCommandWorker  (cola maxsize=80, rate-limit 200 ms)
              │
              ▼
         PTZController.continuous_move(x, y, duration_s)
              │
              ▼
         Cámara PTZ (ONVIF/TCP)
```

### 5.2 Readquisición Activa (RO-04)

Cuando el objetivo se pierde (TTL expirado), `ReacquisitionPattern` ejecuta un barrido de 8 pasos angulares (±15°) durante `PTZ_REACQ_DURATION_S=3 s` antes de ceder el control al modo de inspección.

### 5.3 Modo de Inspección / Patrullaje

`_InspectionPatrolWorker` toma control cuando no hay detección confirmada durante `PTZ_INSPECTION_IDLE_S=10 s`. Soporta dos modos:

| Modo | Comportamiento |
|---|---|
| `sweep` (default) | Barrido izquierda ↔ derecha alternado |
| `continuous_360` | Rotación continua en un solo sentido |

Se interrumpe inmediatamente cuando `TrackingPTZWorker` detecta un objetivo activo.

---

## 6. Modelo de Hilos

| Hilo | Clase | Función | Período |
|---|---|---|---|
| RTSP reader | `RTSPLatestFrameReader` | Lee frames, mantiene solo el último | Continuo (cap.read) |
| Video processor | `LiveVideoProcessor` | Inferencia YOLO + tracker + MJPEG | Continuo (frame disponible) |
| Metrics writer | `MetricsDBWriter` | Escribe inference_frames / detections_v2 | Cola (timeout 0.2 s) |
| Event writer | `DetectionEventWriter` | Agrupa detecciones en eventos | Cola (timeout 0.25 s) |
| PTZ command | `PTZCommandWorker` | Ejecuta comandos ONVIF PTZ | Cola (timeout 0.2 s) |
| PTZ tracking | `TrackingPTZWorker` | Control proporcional de seguimiento | sleep 0.05 s |
| PTZ inspection | `_InspectionPatrolWorker` | Patrullaje automático en reposo | sleep 0.25 s |

Todos los hilos son **daemons** (se destruyen cuando termina el proceso principal) y se detienen de forma ordenada mediante `threading.Event._stop` con timeout en `atexit`.

---

## 7. Modelo de Seguridad

### 7.1 Autenticación y Sesiones

- Flask-Login con roles `admin` / `operator`.
- Decorador `role_required(*roles)` aplicado en cada ruta sensible.
- Sesiones no persistentes (`SESSION_PERMANENT = False`).
- **Idle timeout**: sesiones expiradas por inactividad (configurable vía `SECURITY_CONFIG["idle_timeout"]`).
- **Boot ID**: cada arranque del servidor genera un UUID efímero; las sesiones de arranques anteriores se invalidan automáticamente en `before_request`.

### 7.2 Cifrado de Credenciales

Las credenciales RTSP/ONVIF (usuario, contraseña) se almacenan cifradas en `app.db` usando Fernet (AES-128-CBC + HMAC-SHA256). La clave se provee vía variable de entorno `SIRAN_ENCRYPT_KEY`. Si no está configurada, el sistema arranca en modo degradado (credenciales en claro con warning).

### 7.3 Cabeceras HTTP de Seguridad

Añadidas en `after_request` a todas las respuestas:
- `X-Frame-Options: DENY` — previene clickjacking.
- `X-Content-Type-Options: nosniff` — previene MIME sniffing.
- `Content-Security-Policy` — restringe fuentes de scripts/estilos/imágenes a `'self'`.

### 7.4 Prevención de Path Traversal

`_safe_join()` y `_safe_rel_path()` en `src/routes/media.py` validan que las rutas solicitadas permanezcan dentro del directorio raíz permitido antes de servir o recibir cualquier archivo.

### 7.5 Rate Limiting de Login

`src/routes/auth.py` mantiene un diccionario en memoria `_login_attempts` con contador por IP. Tras `MAX_ATTEMPTS` fallos se bloquea la IP durante `LOCKOUT_SECONDS`.

---

## 8. Modelo de Datos

### 8.1 `app.db` — SQLAlchemy (SQLite)

```
users
  ├── id          INTEGER PK
  ├── username    TEXT UNIQUE NOT NULL
  ├── password    TEXT NOT NULL   (hash bcrypt)
  └── role        TEXT            ('admin' | 'operator')

camera_config
  ├── id               INTEGER PK
  ├── rtsp_url         TEXT
  ├── rtsp_username    TEXT        (cifrado Fernet)
  ├── rtsp_password    TEXT        (cifrado Fernet)
  ├── onvif_host       TEXT
  ├── onvif_port       INTEGER
  ├── onvif_username   TEXT        (cifrado Fernet)
  ├── onvif_password   TEXT        (cifrado Fernet)
  └── camera_type      TEXT        ('fixed' | 'ptz')
```

### 8.2 `detections.db` — SQLite WAL (acceso directo)

```
inference_frames
  ├── id            INTEGER PK AUTOINCREMENT
  ├── timestamp     TEXT           (ISO-8601)
  ├── source        TEXT           ('rtsp' | 'analysis')
  ├── inference_ms  REAL
  ├── frame_w       INTEGER
  ├── frame_h       INTEGER
  └── camera_mode   TEXT

detections_v2
  ├── id            INTEGER PK AUTOINCREMENT
  ├── frame_id      INTEGER FK → inference_frames.id
  ├── timestamp     TEXT
  ├── confidence    REAL
  ├── x1,y1,x2,y2  INTEGER        (bounding box xyxy)
  ├── class_name    TEXT
  ├── track_id      INTEGER        (SORT ID)
  ├── confirmed     INTEGER        (0/1)
  ├── source        TEXT
  ├── camera_mode   TEXT
  └── image_path    TEXT           (ruta relativa evidencia .jpg)

detection_events
  ├── id                   INTEGER PK AUTOINCREMENT
  ├── started_at           TEXT
  ├── ended_at             TEXT
  ├── max_confidence       REAL
  ├── detection_count      INTEGER
  ├── best_bbox_text       TEXT    ('x1,y1,x2,y2')
  ├── best_evidence_path   TEXT
  ├── status               TEXT    ('open' | 'closed')
  ├── source               TEXT
  ├── created_at           TEXT
  └── updated_at           TEXT
```

---

## 9. Inyección de Dependencias

SIRAN no usa un framework de DI. Cada blueprint recibe sus dependencias en el momento de registro:

```python
init_dashboard_routes(
    bp=dashboard_bp,
    live_processor=live_processor,
    detection_state=current_detection_state,
    state_lock=state_lock,
    get_camera_mode=...,
    metrics_db_path=...,
)
```

Dentro de cada blueprint, `get_dep(deps, key)` (en `src/routes/__init__.py`) resuelve la dependencia o lanza `RuntimeError` con un mensaje explícito si falta, haciendo los errores de configuración detectables en arranque.

---

## 10. Flujo de Análisis Asíncrono (Imágenes / Video)

Las rutas `/api/analysis/upload` y `/api/analysis/start` en `src/routes/analysis.py` ejecutan inferencia YOLO sobre archivos subidos en un hilo separado por trabajo (`job_id`). El cliente consulta `/api/analysis/status/<job_id>` hasta recibir `status: done`. Los N frames con mayor confianza se guardan en `static/top_detections/`.

---

## 11. Dependencias Externas Clave

| Paquete | Uso |
|---|---|
| `flask` / `flask-login` | Framework web + autenticación |
| `flask-sqlalchemy` | ORM para `app.db` |
| `ultralytics` | Modelo YOLO (YOLOv8/v9) |
| `opencv-python` | Captura RTSP, dibujo, encode JPEG |
| `onvif-zeep` | Control PTZ vía ONVIF (SOAP/WSDL) |
| `scipy` | `linear_sum_assignment` para SORT |
| `numpy` | Cálculos matriciales (IoU, frames) |
| `cryptography` | Fernet para cifrado de credenciales |
| `torch` | Aceleración GPU (CUDA) para YOLO |

---

## 12. Variables de Entorno Principales

| Variable | Default | Descripción |
|---|---|---|
| `RTSP_URL` | `"0"` | URL RTSP o índice de webcam local |
| `YOLO_MODEL_PATH` | `runs/detect/weights/best.pt` | Ruta al modelo `.pt` entrenado |
| `YOLO_CONFIDENCE` | `0.8` | Umbral de confianza de detección |
| `SIRAN_ENCRYPT_KEY` | `""` | Clave Fernet para credenciales |
| `ONVIF_HOST` | `""` | IP/hostname de la cámara PTZ |
| `ONVIF_PORT` | `80` | Puerto ONVIF (no RTSP) |
| `PTZ_TRACKING_TARGET_TTL` | `3.0` | Segundos antes de perder objetivo (RO-04) |
| `PTZ_TRACKING_TOLERANCE` | `0.15` | Zona central ±15% sin movimiento (RO-03) |
| `PTZ_K_PAN` / `PTZ_K_TILT` | `0.8` | Ganancia del control proporcional (RO-05) |
| `FLASK_SECRET_KEY` | auto-generado | Clave de firma de sesiones Flask |
| `EVENT_GAP_SECONDS` | `3.0` | Brecha máxima entre frames del mismo evento |

---

*Documento generado automáticamente a partir del código fuente — actualizar al incorporar nuevos módulos.*
