# Apoyo para Capítulo 3 — Metodología y Desarrollo

*Texto de apoyo redactado en tercera persona, estilo formal de tesis. Los resultados concretos deben completarse con los valores reales obtenidos durante las pruebas.*

---

## 3.1 Metodología de desarrollo

El desarrollo del sistema SIRAN siguió una metodología incremental iterativa, en la que cada módulo funcional fue implementado, probado de forma aislada e integrado progresivamente al sistema. Esta aproximación permitió verificar el funcionamiento de cada componente antes de proceder a la integración con los módulos siguientes, reduciendo el riesgo de fallos en la integración final.

El ciclo de desarrollo comprendió las siguientes etapas por cada módulo: análisis de requerimientos, diseño de la solución, implementación, prueba unitaria informal y documentación de la interfaz pública del módulo.

---

## 3.2 Análisis de requerimientos

### Requerimientos funcionales

| ID | Requerimiento |
|---|---|
| RF-01 | El sistema debe capturar y procesar el stream de video de una cámara IP en tiempo real vía RTSP |
| RF-02 | El sistema debe aplicar inferencia de un modelo YOLO para detectar aeronaves no tripuladas en el video |
| RF-03 | El sistema debe mostrar el video anotado con bounding boxes al operador en tiempo real |
| RF-04 | El sistema debe controlar una cámara PTZ vía ONVIF para seguir automáticamente el objetivo detectado |
| RF-05 | El sistema debe ejecutar un modo de patrullaje autónomo de la cámara |
| RF-06 | El sistema debe permitir el control manual de la cámara PTZ desde la interfaz web |
| RF-07 | El sistema debe permitir el análisis manual de imágenes y videos subidos por el operador |
| RF-08 | El sistema debe registrar eventos de detección con evidencias visuales y timestamps |
| RF-09 | El sistema debe mantener telemetría de rendimiento del sistema |
| RF-10 | El sistema debe permitir la exportación de eventos de detección en formato estructurado |
| RF-11 | El sistema debe gestionar un dataset de imágenes para el entrenamiento del modelo |
| RF-12 | El sistema debe tener una interfaz web con autenticación y control de roles |
| RF-13 | El sistema debe permitir la configuración de parámetros de detección sin reiniciar el servicio |

### Requerimientos no funcionales

| ID | Requerimiento |
|---|---|
| RNF-01 | La latencia del stream de video al operador debe ser inferior a 500 ms en red local |
| RNF-02 | La inferencia YOLO debe completarse en menos de 50 ms en hardware con GPU (objetivo) |
| RNF-03 | El sistema debe recuperarse automáticamente de interrupciones en el stream RTSP |
| RNF-04 | El sistema debe operar de forma continua sin requerir reinicios para cambios de configuración |
| RNF-05 | El sistema debe estar disponible en red local mediante navegador web estándar |
| RNF-06 | El sistema no debe exponer credenciales de configuración en la interfaz web |
| RNF-07 | El sistema debe funcionar con GPU NVIDIA o en modo CPU (fallback automático) |

---

## 3.3 Diseño de la arquitectura

El sistema fue diseñado con una arquitectura cliente-servidor de proceso único, donde el servidor Python (Flask) actúa como orquestador de todos los subsistemas. La decisión de arquitectura monolítica responde al alcance de prototipo: simplifica el despliegue, elimina la necesidad de infraestructura adicional (brokers de mensajes, contenedores separados) y facilita la depuración durante el desarrollo.

Los componentes de largo ciclo de vida (lector RTSP, procesador de video, worker PTZ, escritor de métricas) se implementan como hilos daemon con colas de comunicación (`queue.Queue`), lo que evita bloquear el loop de solicitudes HTTP de Flask.

Para la persistencia, se utilizaron dos bases de datos SQLite separadas: una gestionada por Flask-SQLAlchemy para usuarios y configuración (acceso frecuente, esquema relacional), y otra de acceso directo con WAL journal para telemetría de alta frecuencia (miles de registros por sesión).

---

## 3.4 Herramientas y entorno de desarrollo

El desarrollo fue realizado en entorno Windows con Python 3.11, utilizando un entorno virtual (`venv_new`) para el aislamiento de dependencias. El control de versiones se gestionó mediante Git con repositorio en GitHub.

Las dependencias principales utilizadas se listan en el archivo `requirements.txt` del repositorio. Las herramientas de desarrollo incluyen: Visual Studio Code como editor, Git como sistema de control de versiones, y el navegador web para validación de la interfaz.

---

## 3.5 Desarrollo del módulo de captura y procesamiento de video en vivo

La captura del stream RTSP se implementó mediante la clase `RTSPLatestFrameReader`, que ejecuta un hilo dedicado en modo `daemon`. El hilo lee continuamente de `cv2.VideoCapture(rtsp_url)` y almacena únicamente el frame más reciente en un buffer de tamaño 1. Esta estrategia garantiza que el procesador de inferencia siempre trabaje con el frame más actualizado, evitando el crecimiento indefinido del buffer en caso de que la inferencia sea más lenta que la captura.

El procesador de video en vivo (`LiveVideoProcessor`) extrae el frame del buffer, aplica la inferencia YOLO, dibuja los bounding boxes y codifica el frame como JPEG para su entrega al cliente. Los frames se sirven mediante el protocolo MJPEG (`multipart/x-mixed-replace`) a través de la ruta `/video_feed`.

---

## 3.6 Desarrollo del módulo de detección con YOLO

El modelo YOLO se carga en tiempo de inicio del servidor mediante la función `load_yolo_model()`. La función detecta dinámicamente si CUDA está disponible para seleccionar el dispositivo de inferencia (GPU o CPU). La ruta del modelo es configurable por variable de entorno (`YOLO_MODEL_PATH`), con fallback a un archivo por defecto.

La inferencia se aplica a cada frame extraído del stream RTSP. Los resultados incluyen las coordenadas del bounding box en píxeles, la clase del objeto detectado y la confianza de la detección. Solo se procesan detecciones con confianza superior al umbral configurado.

Para mitigar detecciones ruidosas (aves u otros objetos con semejanza visual superficial al dron), se implementó un contador de persistencia: una detección solo se considera confirmada si el objeto aparece en N frames consecutivos (parámetro `persistence_frames`, configurable).

---

## 3.7 Desarrollo del módulo de control PTZ

El control PTZ se implementó mediante la clase `PTZController`, que encapsula la comunicación ONVIF. Las operaciones implementadas son `continuous_move(x, y, zoom, duration_s)` y `stop()`.

El worker PTZ (`PTZWorker`) ejecuta en un hilo daemon y procesa comandos de una cola (`queue.Queue`). Esto desacopla la generación de comandos (hilo de inferencia o solicitud HTTP) de su ejecución (hilo de comunicación ONVIF), evitando bloqueos.

Para el tracking automático, el sistema calcula el desplazamiento proporcional del centro del bounding box respecto al centro del frame, normalizado al rango [-1, 1] para cada eje. Si el desplazamiento supera la tolerancia configurada (`PTZ_TOLERANCE_FRAC`), se encola un comando de movimiento correctivo con velocidad proporcional al error.

El proceso de autodiscovery ONVIF, ejecutado al inicio y tras cambios de configuración, determina si la cámara reporta servicios PTZ. Solo si este resultado es positivo se habilitan las rutas de control PTZ.

---

## 3.8 Desarrollo del módulo de análisis manual

El análisis manual sigue un patrón de procesamiento asíncrono con polling: la solicitud HTTP retorna inmediatamente con un `job_id`, y el procesamiento real ocurre en un hilo separado. El cliente consulta periódicamente el endpoint `/video_progress?job_id=<id>` para obtener el estado y el resultado final.

Para imágenes estáticas, el proceso aplica YOLO a la imagen completa y guarda el resultado anotado como JPEG. Para videos, el proceso itera frame a frame, aplica YOLO a cada frame, escribe el resultado en un archivo de video y mantiene un heap de los 10 frames con mayor confianza para exportarlos como galería.

La compatibilidad del video resultante con navegadores web se aborda mediante transcodificación FFmpeg (libx264 + yuv420p + faststart). Si FFmpeg no está disponible, el video raw se ofrece para descarga directa.

---

## 3.9 Modelo de datos

**Base de datos `instance/app.db` (Flask-SQLAlchemy):**

- Tabla `user`: id, username, password_hash, role
- Tabla `camera_config`: id, camera_type, rtsp_url, rtsp_username, rtsp_password, onvif_host, onvif_port, onvif_username, onvif_password

**Base de datos `detections.db` (SQLite directo):**

- Tabla `inference_frames`: id, timestamp, source, inference_ms, frame_w, frame_h, detections_json, confirmed, camera_mode
- Tabla `detection_events`: id, started_at, ended_at, max_confidence, detection_count, best_bbox_text, best_evidence_path, status, source, created_at, updated_at

---

## 3.10 Dataset

El dataset de entrenamiento del modelo YOLO fue construido mediante recolección de imágenes de aeronaves no tripuladas en diversas condiciones (distancia, fondo, iluminación). El sistema SIRAN incluye un módulo de gestión de dataset que facilita la recolección incremental de nuevas imágenes durante la operación del sistema, clasificadas manualmente por el administrador como positivas (contienen un dron) o negativas (falsos positivos).

Las imágenes clasificadas se organizan en la estructura de directorios requerida por Ultralytics YOLO para el reentrenamiento. El proceso de reentrenamiento en sí se ejecuta de forma separada (fuera del sistema SIRAN, mediante los scripts de Ultralytics).

---

## 3.11 Cámara

Las pruebas del sistema se realizaron utilizando una cámara IP con soporte RTSP y ONVIF. El tipo de cámara (PTZ o fija) se configura desde la interfaz de administración. El sistema incluye un proceso de autodiscovery que detecta las capacidades PTZ de la cámara conectada, independientemente del tipo configurado manualmente.

---

## 3.12 Interfaz de usuario

La interfaz web fue desarrollada en HTML5, CSS3 y JavaScript puro (sin frameworks de frontend), con un tema visual oscuro y acentos verde neón. La interfaz se adapta dinámicamente al rol del usuario autenticado: el operador accede al dashboard con stream, controles y análisis; el administrador accede al panel de configuración y gestión de dataset.

El joystick PTZ se implementó mediante el Canvas API de HTML5. La comunicación con el backend utiliza la Fetch API para solicitudes JSON. El stream de video se entrega mediante el protocolo MJPEG nativo del navegador.
