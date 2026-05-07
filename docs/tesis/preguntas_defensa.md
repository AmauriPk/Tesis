# Preguntas y Respuestas para Defensa Oral — SIRAN

---

## ¿Por qué YOLO?

**Respuesta:** YOLO (You Only Look Once) es el modelo de detección de objetos con mejor relación entre velocidad de inferencia y precisión en la actualidad. Su versión v8/v9 de Ultralytics permite procesar video en tiempo real con hardware de consumo. Para un sistema que debe detectar drones frame a frame sin introducir latencia perceptible al operador, YOLO es la opción más adecuada. Modelos de mayor precisión como Faster R-CNN tienen latencias incompatibles con el procesamiento en tiempo real.

---

## ¿Por qué Flask?

**Respuesta:** Flask es un microframework Python que no impone estructura rígida. Para un prototipo de investigación que integra código de visión artificial (numpy, opencv, pytorch) con una API REST y un stream MJPEG, Flask permite esa integración directamente sin capas de abstracción innecesarias. Frameworks más pesados como Django agregarían complejidad sin beneficio para este caso de uso.

---

## ¿Por qué RTSP?

**Respuesta:** RTSP (Real Time Streaming Protocol) es el protocolo estándar de la industria para transmisión de video desde cámaras IP. Prácticamente todas las cámaras IP profesionales lo soportan independientemente del fabricante. Usar RTSP desacopla el sistema del fabricante de la cámara y permite intercambiarla sin modificar el código.

---

## ¿Por qué ONVIF?

**Respuesta:** ONVIF (Open Network Video Interface Forum) es el protocolo estándar para control de cámaras IP, incluyendo PTZ. Igual que RTSP, ONVIF garantiza interoperabilidad entre fabricantes. Sin ONVIF, el control PTZ requeriría APIs propietarias distintas para cada fabricante (Hikvision, Dahua, Hanwha), lo que haría el sistema dependiente de una marca específica.

---

## ¿Qué pasa si cambia la cámara?

**Respuesta:** Si la nueva cámara soporta RTSP y ONVIF (que es el caso de la mayoría de cámaras IP profesionales), solo se necesita actualizar la URL RTSP, el host ONVIF y las credenciales en el panel de administración. No se requieren cambios en el código. El sistema incluye un proceso de autodiscovery que detecta si la nueva cámara soporta PTZ.

---

## ¿Funciona con cámaras Dahua?

**Respuesta:** Las cámaras Dahua soportan RTSP y ONVIF, por lo que son compatibles con el sistema. Sin embargo, la compatibilidad ONVIF puede variar según el modelo y versión de firmware. El sistema incluye un botón de "Probar conexión" que verifica la compatibilidad antes de usar el PTZ.

---

## ¿Qué limitaciones tiene el sistema?

**Respuesta:** Las principales limitaciones son: (1) el sistema solo procesa una cámara a la vez; (2) el tracking es reactivo, no predictivo — si el dron sale del frame brevemente, se pierde el seguimiento; (3) la precisión del modelo depende del dataset de entrenamiento; (4) sin FFmpeg instalado, los videos procesados no son reproducibles en navegador; (5) el sistema no implementa cifrado HTTPS, por lo que no es adecuado para despliegue en redes no confiables sin configuración adicional.

---

## ¿Cómo se validó el sistema?

**Respuesta:** La validación del sistema se realizó mediante pruebas funcionales en condiciones controladas de laboratorio: análisis de imágenes y videos de drones, verificación del tracking PTZ, confirmación de la generación de eventos y evidencias, y validación de la exportación de datos. Los resultados se documentaron con capturas de pantalla y registros del sistema. Se reconoce que la validación en condiciones reales (exterior, iluminación variable, distancias mayores) es una limitación del prototipo actual.

---

## ¿Qué métricas se obtuvieron?

**Respuesta:** El sistema registra telemetría de cada frame procesado: tiempo de inferencia en milisegundos, confianza de detección, dimensiones del frame, número de detecciones. Estas métricas se almacenan en SQLite y pueden exportarse. Para la tesis, se presentan métricas de confianza promedio por sesión de análisis, tiempo de inferencia promedio en GPU vs CPU, y conteo de detecciones por tipo de contenido analizado.

---

## ¿Qué aporta el sistema?

**Respuesta:** El aporte principal es la integración funcional de detección por IA, control automático de hardware PTZ, registro de eventos y gestión de evidencias en un único prototipo operativo. Esto demuestra la viabilidad técnica de construir un sistema de estas características con herramientas de código abierto y hardware comercial. La aportación no es el modelo YOLO en sí, sino el sistema completo que lo rodea.

---

## ¿Por qué es un prototipo?

**Respuesta:** Se denomina prototipo porque cumple los objetivos de demostración de viabilidad técnica, pero no está optimizado para producción: no implementa cifrado de comunicaciones, no ha sido sometido a pruebas de carga, no tiene redundancia ni mecanismos de recuperación ante fallos, y solo ha sido validado en condiciones controladas. Esta es la limitación apropiada para un trabajo de tesis de grado.

---

## ¿Qué diferencia tiene con una cámara PTZ comercial con detección integrada?

**Respuesta:** Los sistemas comerciales integran el procesamiento directamente en el firmware de la cámara, lo que los hace más eficientes en latencia pero no configurables para modelos personalizados. SIRAN permite usar cualquier modelo YOLO personalizado entrenado con datos propios, configurar umbrales y parámetros desde la interfaz, y acceder a datos estructurados de detección. Además, al ser software, puede actualizarse el modelo sin reemplazar hardware.

---

## ¿Qué pasa si falla FFmpeg?

**Respuesta:** El sistema tiene un manejo explícito de este caso. Si FFmpeg no está disponible, el video raw generado por OpenCV (mp4v) se ofrece al usuario para descarga directa. La API `/video_progress` devuelve el flag `result_video_playable: false` y el campo `video_output_warning` con un mensaje explicativo. El análisis de detección no se ve afectado; solo la reproducción en navegador se degrada.

---

## ¿Por qué no guardar todas las imágenes de detección?

**Respuesta:** En condiciones normales de operación, con 25-30 FPS y detecciones frecuentes, guardar todas las imágenes consumiría decenas de gigabytes por hora. El sistema implementa dos estrategias: (1) guarda evidencias de frames con detección confirmada (persistencia de N frames consecutivos), lo que filtra detecciones aisladas; (2) en el análisis de video, guarda solo los 10 frames de mayor confianza. Esto balancea la utilidad de la evidencia con el consumo de almacenamiento.

---

## ¿Por qué usar eventos agrupados?

**Respuesta:** Registrar cada frame con detección de forma independiente generaría miles de registros por minuto, dificultando el análisis posterior. El esquema de eventos agrupa las detecciones continuas en un único evento con timestamps de inicio y fin, confianza máxima y conteo total. Esto produce registros operativamente significativos ("el dron estuvo visible de 14:44 a 14:46 con confianza máxima del 88%") en lugar de miles de registros técnicos individuales.

---

## ¿Por qué separar registros técnicos y eventos?

**Respuesta:** Los registros técnicos (`inference_frames`) tienen alta frecuencia y sirven para análisis de rendimiento y trazabilidad técnica. Los eventos de detección (`detection_events`) son de baja frecuencia y sirven para análisis operativo y presentación de resultados. Mezclarlos en una sola tabla haría el análisis operativo ineficiente y los registros técnicos serían difíciles de mantener. Separar ambas tablas permite consultar cada capa de datos de forma independiente.

---

## ¿Por qué usar una cámara PTZ?

**Respuesta:** Una cámara fija solo puede detectar drones dentro de su campo de visión estático. Una cámara PTZ puede seguir al dron una vez detectado, manteniendo la detección activa incluso cuando el dron se mueve fuera del campo de visión inicial. También puede ejecutar barridos autónomos para cubrir un área mayor. Esto amplifica la utilidad del sistema de detección frente a una cámara fija.

---

## ¿Qué tan escalable es el sistema?

**Respuesta:** En su arquitectura actual, el sistema procesa una cámara en un solo proceso Python, lo que limita la escalabilidad horizontal. Para soportar múltiples cámaras, se requeriría una arquitectura de microservicios o al menos procesos separados por cámara. Para el alcance de un prototipo de tesis con una cámara, la arquitectura actual es adecuada y simple de mantener.

---

## ¿Qué se puede mejorar después?

**Respuesta:** Las mejoras más relevantes para una siguiente versión serían: implementar HTTPS para comunicaciones seguras, agregar soporte para múltiples cámaras simultáneas, implementar tracking predictivo con filtro de Kalman, automatizar el reentrenamiento del modelo con las imágenes clasificadas, y desarrollar un módulo de análisis de trayectoria del dron. Para el prototipo actual, el enfoque fue demostrar la integración funcional del sistema completo.
