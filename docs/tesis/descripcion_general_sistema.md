# Descripción General del Sistema — SIRAN

## Nombre del sistema

**SIRAN** — Sistema Integrado de Reconocimiento de Aeronaves No Tripuladas
*(Nombre interno de desarrollo: DEPURA)*

---

## Propósito

SIRAN es un prototipo de sistema de visión artificial diseñado para la detección, seguimiento, análisis y registro de aeronaves no tripuladas (drones/UAS). Integra procesamiento de imágenes y video en tiempo real, control automático de cámara PTZ, persistencia de eventos de detección y gestión de datos para análisis posterior.

---

## Problema que atiende

El incremento en el uso de aeronaves no tripuladas en entornos urbanos y rurales genera necesidades de monitoreo y detección que no pueden ser cubiertas eficientemente por observación humana continua. Los sistemas comerciales de detección de drones son costosos y de difícil adaptación. SIRAN busca demostrar la viabilidad técnica de un sistema basado en visión artificial y hardware accesible que pueda detectar, seguir y registrar la presencia de drones de manera autónoma.

---

## Usuarios del sistema

| Rol | Descripción |
|---|---|
| **Operador** | Usuario principal en campo. Monitorea el video en vivo, analiza imágenes/videos, controla la cámara PTZ, activa/desactiva tracking e inspección automática, revisa alertas y evidencias. |
| **Administrador** | Usuario técnico. Configura la cámara (RTSP/ONVIF), ajusta parámetros del modelo de detección, gestiona el dataset, revisa métricas y exporta eventos. |

---

## Alcance del prototipo

El sistema SIRAN, en su versión actual, abarca:

1. Streaming de video en tiempo real desde cámara IP (RTSP/MJPEG) con inferencia YOLO superpuesta.
2. Detección automática de drones con umbral de confianza configurable.
3. Control PTZ manual (joystick) y automático (tracking del objeto detectado).
4. Modo de inspección/patrullaje automático (barrido angular continuo).
5. Análisis manual de imagen y video (carga por el usuario, inferencia offline).
6. Registro de eventos de detección agrupados con evidencias visuales.
7. Dashboard de métricas de detección.
8. Gestión de dataset para captura y clasificación de imágenes positivas/negativas.
9. Interfaz web segura con autenticación y roles.
10. Exportación de eventos en formato CSV.

---

## Limitaciones

- El sistema es un prototipo de investigación, no un producto de producción.
- La precisión del modelo YOLO depende del dataset de entrenamiento disponible; el desempeño en condiciones no representadas en el dataset puede ser inferior.
- El control PTZ requiere cámara compatible con protocolo ONVIF y credenciales válidas.
- La reproducción de video procesado en navegador depende de la disponibilidad de FFmpeg en el servidor.
- No implementa cifrado de comunicaciones (TLS/HTTPS) en la versión prototipo.
- No incluye sistema de alarmas externas (buzzer, email, SMS).
- El sistema no está diseñado para múltiples cámaras simultáneas.

---

## Tecnologías empleadas

| Capa | Tecnología |
|---|---|
| Backend | Python 3.11+, Flask 2.x, Flask-Login, Flask-SQLAlchemy |
| Visión artificial | OpenCV 4.x, Ultralytics YOLO v8/v9 |
| Aceleración | PyTorch + CUDA (GPU NVIDIA) |
| Streaming | RTSP (cámara), MJPEG (navegador) |
| Control PTZ | ONVIF (protocolo), onvif-zeep (librería Python) |
| Base de datos | SQLite (eventos, usuarios, configuración) |
| Video export | FFmpeg, imageio-ffmpeg |
| Frontend | HTML5, CSS3, JavaScript vanilla |
| Control de versiones | Git / GitHub |

---

## Resumen de funcionamiento

Al iniciar el sistema, SIRAN:
1. Carga el modelo YOLO en GPU (si disponible) o CPU.
2. Establece conexión con la cámara vía RTSP.
3. Inicia el hilo de lectura de frames (`RTSPLatestFrameReader`).
4. Inicia el procesador de video en vivo (`LiveVideoProcessor`) que aplica inferencia YOLO a cada frame.
5. Inicia el worker PTZ (`PTZWorker`) en standby.
6. Sirve la interfaz web en el puerto 5000.

El operador visualiza el stream anotado en tiempo real. Si activa el tracking automático, el sistema calcula la posición del dron detectado en el frame y envía comandos de movimiento al worker PTZ para centrar la cámara sobre el objetivo. Si activa el modo inspección, la cámara ejecuta un barrido programado de forma autónoma.

---

## Aportación general

La aportación del sistema reside en la **integración funcional** de múltiples componentes tecnológicos (detección por IA, control de hardware, análisis offline, registro de eventos y gestión de datos) en un único prototipo operativo. Esto demuestra que es técnicamente factible construir un sistema de estas características con herramientas de código abierto y hardware comercial disponible.

---

## Explicación breve para sinodales

> SIRAN es un sistema software que recibe el video de una cámara IP, aplica un modelo de inteligencia artificial para detectar drones en tiempo real, y puede controlar automáticamente la orientación de la cámara para seguir al objeto detectado. Adicionalmente, permite analizar imágenes y videos de manera manual, registra eventos de detección con evidencias visuales, y ofrece una interfaz de administración para configurar el sistema y gestionar el dataset de imágenes.
