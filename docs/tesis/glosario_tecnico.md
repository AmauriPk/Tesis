# Glosario Técnico — SIRAN

---

## Visión artificial

Rama de la inteligencia artificial que desarrolla técnicas para que los sistemas computacionales interpreten y comprendan información visual proveniente de imágenes digitales o secuencias de video. Incluye disciplinas como detección de objetos, segmentación de imágenes, reconocimiento de patrones y estimación de poses. En el contexto de SIRAN, la visión artificial es el fundamento tecnológico para la detección automática de aeronaves no tripuladas.

---

## Detección de objetos

Tarea de visión artificial que consiste en identificar y localizar instancias de objetos de una o más clases en una imagen. El resultado incluye: (1) la clase del objeto detectado, (2) la posición y dimensiones del objeto expresadas como bounding box, y (3) la confianza o probabilidad de la detección. SIRAN utiliza detección de objetos para localizar drones en los frames del video.

---

## YOLO (You Only Look Once)

Familia de arquitecturas de redes neuronales convolucionales para detección de objetos en tiempo real. A diferencia de métodos anteriores de dos etapas, YOLO procesa la imagen completa en una sola pasada (forward pass) de la red, lo que permite velocidades de inferencia muy altas. La versión utilizada en SIRAN es YOLOv8/v9 de la librería Ultralytics. El nombre "You Only Look Once" hace referencia a que la imagen se analiza una sola vez para producir las predicciones.

---

## Bounding box

Rectángulo alineado con los ejes que delimita el área ocupada por un objeto detectado en una imagen. Se expresa usualmente como coordenadas `(x1, y1, x2, y2)` de las esquinas opuestas del rectángulo. En SIRAN, los bounding boxes se dibujan sobre los frames del video para indicar la posición de los drones detectados. El área del bounding box se utiliza como criterio de priorización cuando se detectan múltiples objetos.

---

## Confianza (confidence)

Valor numérico en el rango [0, 1] que representa la certeza del modelo de detección de que un objeto particular está presente en el área delimitada por el bounding box. Una confianza de 0.9 indica que el modelo está 90% seguro de su detección. En SIRAN, el umbral de confianza (configurable, por defecto 0.6) determina qué detecciones se muestran y se registran.

---

## Tracking (seguimiento)

Proceso de seguir la posición de un objeto a lo largo del tiempo en una secuencia de imágenes. En SIRAN, el tracking consiste en calcular la posición del dron detectado en cada frame y generar comandos de movimiento PTZ para mantener la cámara centrada sobre el objetivo. El sistema implementa tracking reactivo: la posición de corrección se calcula a partir de la detección más reciente, sin predicción de trayectoria.

---

## PTZ (Pan-Tilt-Zoom)

Tipo de cámara motorizada capaz de rotar horizontalmente (Pan), rotar verticalmente (Tilt) y modificar el nivel de zoom óptico (Zoom) de forma remota. En SIRAN, el control PTZ permite mover la cámara para seguir un dron detectado o para ejecutar un barrido de patrullaje autónomo. El control PTZ se realiza mediante el protocolo ONVIF.

---

## RTSP (Real Time Streaming Protocol)

Protocolo de red para el control de servidores de medios en streaming. RTSP actúa como un "control remoto de red" para transmisiones multimedia. En el contexto de cámaras IP, se usa para iniciar, pausar y controlar el stream de video. Las URLs RTSP tienen el formato `rtsp://usuario:contraseña@IP:puerto/stream`. SIRAN usa RTSP para recibir el video de la cámara IP.

---

## ONVIF (Open Network Video Interface Forum)

Estándar de la industria para la interoperabilidad de productos de seguridad de red (cámaras, grabadores, software). ONVIF define interfaces de servicio web (SOAP/XML) para el descubrimiento, configuración y control de dispositivos. El servicio PTZ de ONVIF permite controlar cámaras Pan-Tilt-Zoom de múltiples fabricantes con la misma API. SIRAN usa ONVIF para controlar la cámara PTZ sin depender del fabricante específico.

---

## Frame

Imagen individual que forma parte de una secuencia de video. Un video de 30 FPS contiene 30 frames por segundo. En SIRAN, el procesamiento de video consiste en aplicar inferencia YOLO a cada frame extraído del stream RTSP. El `RTSPLatestFrameReader` mantiene siempre disponible el frame más reciente de la cámara.

---

## FPS (Frames Per Second)

Medida de la frecuencia de frames en una secuencia de video o en el procesamiento de frames de un sistema de visión artificial. Un video RTSP típico opera a 25-30 FPS. La inferencia YOLO en GPU puede procesar decenas de frames por segundo; en CPU, la velocidad es menor y variable según el hardware. El FPS efectivo del sistema SIRAN depende de la velocidad de inferencia del hardware disponible.

---

## Evento de detección

Unidad lógica que agrupa múltiples detecciones individuales que ocurren en continuidad temporal. En SIRAN, un evento se "abre" con la primera detección confirmada y se "cierra" cuando pasan más de N segundos (configurable, por defecto 3) sin nuevas detecciones. Cada evento registra: timestamp de inicio y fin, confianza máxima, conteo total de detecciones, mejor bounding box y ruta de la mejor evidencia visual. Los eventos son la unidad de análisis operativo.

---

## Evidencia visual

Imagen JPEG guardada automáticamente cuando se confirma una detección durante el stream en vivo. La evidencia contiene el frame completo del video en el momento de la detección, con el timestamp y nivel de confianza incluidos en el nombre del archivo. Las evidencias permiten revisar posteriormente las detecciones que generaron alertas.

---

## Dataset

Conjunto organizado de imágenes etiquetadas utilizado para entrenar y evaluar modelos de aprendizaje automático. En el contexto de SIRAN, el dataset contiene imágenes de aeronaves no tripuladas (clase positiva) e imágenes sin drones o con objetos similares (clase negativa o falsos positivos). La calidad, diversidad y balance del dataset son factores determinantes de la precisión del modelo YOLO resultante.

---

## Inferencia

Proceso de aplicar un modelo de aprendizaje automático ya entrenado para obtener predicciones sobre nuevos datos. En SIRAN, la inferencia es el acto de ejecutar el modelo YOLO sobre un frame de video para obtener las detecciones (clase, bounding box, confianza). La inferencia no modifica el modelo; es un proceso de solo lectura.

---

## CUDA

Plataforma de computación paralela de NVIDIA que permite ejecutar código de propósito general en GPUs NVIDIA. En el contexto de SIRAN, CUDA permite que PyTorch ejecute la inferencia YOLO en la GPU, reduciendo el tiempo de inferencia de cientos de milisegundos (CPU) a decenas de milisegundos (GPU). El sistema detecta automáticamente si CUDA está disponible.

---

## OpenCV

Librería de código abierto para visión artificial y procesamiento de imágenes. Implementada en C++ con bindings para Python. En SIRAN se usa para: captura de streams RTSP, manipulación de frames (resize, convertir colores), dibujar bounding boxes sobre imágenes, escribir videos anotados y codificar frames como JPEG en memoria.

---

## Flask

Microframework web para Python. "Micro" porque no incluye ORM, validación de formularios ni otras herramientas que frameworks más completos incluyen por defecto, pero es extensible mediante plugins. En SIRAN, Flask gestiona las rutas HTTP, la autenticación, las sesiones de usuario y sirve la interfaz web y los streams de video.

---

## Endpoint

Ruta URL expuesta por un servidor web que responde a solicitudes HTTP. Cada endpoint tiene una URL, un método HTTP (GET, POST, etc.) y produce una respuesta. En SIRAN hay más de 30 endpoints que cubren autenticación, control PTZ, análisis, gestión de dataset y telemetría. Ver `docs/tesis/mapa_endpoints.md` para la lista completa.

---

## SQLite

Motor de base de datos relacional que almacena toda la base de datos en un único archivo en disco. No requiere servidor separado, siendo adecuado para aplicaciones embebidas o prototipos. SIRAN usa dos bases de datos SQLite: una para usuarios y configuración (`instance/app.db`), y otra para telemetría de alta frecuencia y eventos de detección (`detections.db`).

---

## FFmpeg

Suite de herramientas de código abierto para procesamiento de audio y video. En SIRAN, FFmpeg se usa para transcodificar el video anotado generado por OpenCV (codec mp4v, no reproducible en navegadores modernos) a un formato H.264 compatible con navegadores web (`-vcodec libx264 -pix_fmt yuv420p -movflags +faststart`). Si FFmpeg no está instalado, los videos solo pueden descargarse, no reproducirse en el navegador.

---

## Prototipo

Versión preliminar de un sistema que implementa las funcionalidades principales para demostrar la viabilidad técnica, pero que no necesariamente cumple con todos los requisitos de un sistema de producción (escalabilidad, seguridad, robustez, documentación completa). SIRAN es clasificado como prototipo porque su validación se realizó en condiciones controladas de laboratorio y no ha sido sometido a pruebas de despliegue en condiciones reales.
