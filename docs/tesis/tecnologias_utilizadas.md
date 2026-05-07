# Tecnologías Utilizadas — SIRAN

## Python

- **Versión:** 3.11+
- **Uso:** lenguaje principal del backend, scripts de procesamiento
- **Justificación:** ecosistema de visión artificial y aprendizaje automático más maduro. Compatibilidad con PyTorch, OpenCV y Ultralytics.

---

## Flask

- **Versión:** 2.3.x
- **Uso:** framework web que sirve la API REST, las plantillas HTML y el stream MJPEG
- **Componentes utilizados:**
  - `Flask-Login` — gestión de autenticación y sesiones
  - `Flask-SQLAlchemy` — ORM para SQLite
  - `Werkzeug` — utilidades de seguridad, manejo de archivos subidos
- **Justificación:** microframework ligero que no impone estructura. Permite integrar código de visión artificial directamente sin capas de abstracción innecesarias para un prototipo.

---

## OpenCV

- **Versión:** 4.8.x
- **Uso:**
  - Captura de frames RTSP (`cv2.VideoCapture`)
  - Redimensionado y conversión de frames (`cv2.resize`, `cv2.cvtColor`)
  - Dibujo de bounding boxes y texto sobre frames (`cv2.rectangle`, `cv2.putText`)
  - Escritura de video anotado (`cv2.VideoWriter`)
  - Lectura de imágenes para análisis manual (`cv2.imread`, `cv2.imwrite`)
  - Codificación JPEG en memoria (`cv2.imencode`)
- **Justificación:** librería de facto para visión artificial en Python. Integración nativa con NumPy.

---

## Ultralytics YOLO

- **Versión:** 8.x / compatible con YOLOv8 y v9
- **Uso:** modelo de detección de objetos en tiempo real. Aplicado a frames del stream RTSP y a imágenes/videos subidos manualmente.
- **Modelo utilizado:** modelo entrenado específicamente para detección de drones (archivo `.pt` generado en entrenamiento previo)
- **Justificación:** YOLO es el estándar de facto para detección en tiempo real. La API de Ultralytics simplifica la carga, inferencia y configuración de parámetros.

---

## PyTorch

- **Versión:** compatible con Ultralytics instalado
- **Uso:** backend de inferencia para YOLO. Permite ejecución en GPU (CUDA) o CPU con la misma API.
- **Justificación:** framework de aprendizaje profundo más usado en investigación. CUDA permite aceleración significativa en GPU NVIDIA.

---

## CUDA

- **Uso:** aceleración de la inferencia YOLO en GPU NVIDIA
- **Selección dinámica:** el sistema detecta en tiempo de ejecución si CUDA está disponible (`torch.cuda.is_available()`); si no, usa CPU automáticamente
- **Justificación:** la inferencia en GPU permite procesar en tiempo real (>15 FPS) sin bloquear el servidor

---

## RTSP (Real Time Streaming Protocol)

- **Uso:** protocolo de transporte para recibir el stream de video de la cámara IP
- **Implementación:** `cv2.VideoCapture(rtsp_url)` en `RTSPLatestFrameReader`
- **Limitaciones:** latencia variable; sensible a pérdida de paquetes; requiere red estable entre servidor y cámara

---

## ONVIF (Open Network Video Interface Forum)

- **Uso:** protocolo estándar de la industria para control de cámaras IP, incluyendo PTZ (Pan-Tilt-Zoom)
- **Librería:** `onvif-zeep` (implementación Python de cliente ONVIF)
- **Operaciones utilizadas:** autodiscovery de servicios PTZ, `ContinuousMove`, `Stop`
- **Justificación:** estándar abierto que permite compatibilidad con múltiples marcas de cámaras (Hikvision, Dahua, Hanwha, etc.)
- **Limitaciones:** no todas las cámaras implementan ONVIF completo; algunas requieren firmware específico

---

## SQLite

- **Uso:** base de datos relacional ligera para:
  - Usuarios del sistema (`instance/app.db` — Flask-SQLAlchemy)
  - Configuración de cámara (`instance/app.db`)
  - Telemetría de frames procesados (`detections.db` — acceso directo)
  - Eventos de detección agrupados (`detections.db`)
- **Justificación:** sin servidor externo, archivo único, adecuado para prototipo de uso local/embebido

---

## HTML5 / CSS3 / JavaScript

- **Uso:** frontend web del sistema
- **Sin frameworks de frontend** (sin React, Vue, etc.): JavaScript vanilla
- **Características utilizadas:**
  - Canvas API para el joystick PTZ
  - Fetch API para comunicación con el backend (JSON)
  - EventSource / polling para actualización del progreso de jobs
  - `<video>` nativo para reproducción de video procesado
- **CSS:** tema oscuro personalizado con acentos verde neón

---

## FFmpeg

- **Uso:** transcodificación del video anotado (raw mp4v/XVID) a H.264 compatible con navegador
- **Resolución dinámica:** el sistema busca FFmpeg en `FFMPEG_BIN`, luego en PATH, luego en imageio_ffmpeg
- **Codecs intentados:** libx264 (preferido), mpeg4 (fallback)
- **Flags:** `-pix_fmt yuv420p -movflags +faststart -an`
- **Comportamiento si no disponible:** el video raw se ofrece para descarga; el flag `result_video_playable` es `false`

---

## imageio-ffmpeg

- **Versión:** 0.5.x
- **Uso:** proveedor de fallback del ejecutable FFmpeg cuando no está instalado en el sistema. Distribuye un binario de FFmpeg portable.
- **Justificación:** permite que el sistema funcione en entornos sin FFmpeg instalado globalmente.

---

## Git / GitHub

- **Uso:** control de versiones, respaldo del código, historial de cambios
- **Repositorio:** `https://github.com/AmauriPk/Tesis`
- **Ramas:** trabajo en rama `main`
- **Pendiente recomendado:** usar ramas de feature para cada módulo nuevo

---

## Entorno virtual Python

- **Carpeta:** `venv_new/`
- **Gestión de dependencias:** `requirements.txt`
- **Instalación:** `pip install -r requirements.txt`
- **Justificación:** aislamiento de dependencias del proyecto respecto al sistema
