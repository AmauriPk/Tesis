# Limitaciones y Alcances — SIRAN

## ¿Qué SÍ hace el sistema?

- Recibe y procesa el stream de video de una cámara IP en tiempo real (RTSP)
- Aplica inferencia con un modelo YOLO entrenado para detectar drones
- Dibuja bounding boxes sobre los objetos detectados en el frame en vivo
- Controla una cámara PTZ vía ONVIF para seguir automáticamente el objetivo detectado (tracking)
- Ejecuta un barrido de patrullaje autónomo (inspección automática)
- Permite control manual del PTZ mediante joystick virtual
- Analiza imágenes estáticas (JPG/PNG) con inferencia YOLO y guarda el resultado
- Analiza videos (MP4/AVI/MOV) frame a frame y genera video anotado
- Convierte el video anotado a formato compatible con navegador (H.264) si FFmpeg está disponible
- Registra eventos de detección agrupados por continuidad temporal con evidencias visuales
- Mantiene telemetría de frames procesados (timestamp, confianza, dimensiones)
- Expone una interfaz web con autenticación y roles (admin, operador)
- Permite al administrador configurar RTSP/ONVIF sin reiniciar el servidor
- Permite ajustar parámetros del modelo YOLO en caliente (sin reiniciar)
- Permite al administrador gestionar un dataset de imágenes clasificadas
- Exporta eventos de detección en formato CSV

---

## ¿Qué NO hace el sistema?

- No detecta múltiples tipos de aeronaves no tripuladas simultáneamente (el modelo es específico para el dataset de entrenamiento)
- No implementa comunicación segura (HTTPS/TLS) en la versión actual
- No soporta múltiples cámaras simultáneamente (solo una fuente RTSP)
- No emite alertas externas (email, SMS, buzzer físico)
- No tiene módulo de reconocimiento de patrones de vuelo o predicción de trayectorias
- No implementa tracking predictivo (filtro Kalman u otros)
- No reentrana el modelo YOLO de forma automática
- No incluye sistema de backups automáticos
- No implementa expiración de sesión por inactividad
- No implementa autenticación de doble factor (2FA)
- No tiene diseño responsive para dispositivos móviles

---

## Limitaciones por hardware

- La latencia del tracking PTZ depende de la calidad de la conexión de red entre el servidor y la cámara
- En hardware sin GPU NVIDIA, la inferencia YOLO se ejecuta en CPU, lo que puede reducir el FPS del stream
- La precisión del tracking depende del tiempo de respuesta mecánico de la cámara PTZ
- La captura RTSP puede conglar frames si la red tiene pérdida de paquetes
- El procesamiento de video manual es secuencial y puede ser lento en CPU para videos largos

---

## Limitaciones por dataset

- La precisión del modelo YOLO está directamente ligada a la diversidad y calidad del dataset de entrenamiento
- El dataset actual puede no incluir suficientes variaciones de: iluminación, distancia, fondo, tipo de dron, ángulo de visión
- Las detecciones falsas positivas (aves, bolsas, objetos voladores) dependen del balance del dataset
- El modelo no ha sido validado formalmente con un conjunto de pruebas estándar publicado

---

## Limitaciones por iluminación, distancia y calidad de imagen

- La detección puede degradarse significativamente en condiciones de baja iluminación (noche, contraluces)
- A distancias grandes (> 30-50 m dependiendo del hardware), el dron puede ser demasiado pequeño para detectarse
- La calidad del sensor de la cámara afecta directamente la confianza del modelo
- El sistema no implementa mejoras de imagen previas a la inferencia (ecualización de histograma, denoising)

---

## Limitaciones de compatibilidad ONVIF

- No todas las cámaras implementan ONVIF de forma completa o compatible
- Algunas cámaras requieren versiones específicas del firmware para exponer servicios PTZ
- Las credenciales ONVIF pueden diferir de las credenciales RTSP
- El autodiscovery usa un timeout de 6 segundos; cámaras lentas pueden fallar el test
- Algunas cámaras PTZ de bajo costo tienen implementaciones ONVIF parciales o con errores

---

## Limitaciones de reproducción de video y FFmpeg

- Sin FFmpeg instalado en el servidor, los videos procesados no son reproducibles directamente en navegador
- La transcodificación H.264 puede fallar si el sistema no tiene `libx264` disponible (intenta fallback a `mpeg4`)
- Los videos procesados con codec `XVID` o `MJPG` (fallback de OpenCV) no son reproducibles en navegadores modernos sin conversión
- La transcodificación de videos largos puede ser lenta y bloquear el hilo del job

---

## Limitaciones del tracking

- El tracking puede perder el objetivo si el dron sale del campo de visión de la cámara
- Múltiples drones simultáneos: el sistema solo sigue el de mayor área en el frame
- Movimientos bruscos del dron pueden generar sobrecompensación del PTZ
- No hay predicción de posición: si el dron desaparece momentáneamente (oclusión), el tracking se interrumpe

---

## Limitaciones de la inspección automática

- El barrido es lineal simple (izquierda-derecha). No implementa cobertura por zonas, patrones en S o cuadrícula
- La velocidad y duración del barrido son fijas por configuración; no se adaptan al área a cubrir
- Si la cámara llega a un tope mecánico, el comportamiento puede ser impredecible

---

## Alcance como prototipo

SIRAN es un **prototipo funcional de investigación**, no un sistema de producción. Esto implica:

- Las pruebas han sido realizadas en condiciones controladas de laboratorio
- No ha sido validado en despliegue exterior con condiciones meteorológicas adversas
- La seguridad del sistema es básica (suficiente para prototipo, insuficiente para despliegue real)
- El sistema está diseñado para demostrar la viabilidad técnica de la integración de componentes, no para escalar

---

## Mejoras futuras recomendadas

1. Cifrado TLS/HTTPS para comunicaciones web
2. Soporte para múltiples cámaras simultáneas
3. Tracking predictivo (filtro de Kalman o similar)
4. Alertas externas (email, webhook)
5. Diseño responsive para operación desde tableta/móvil
6. Reentrenamiento automático del modelo con nuevas imágenes clasificadas
7. Política de retención automática de evidencias y resultados
8. Exportación de reportes en PDF
9. Autenticación de dos factores para el administrador
10. Módulo de análisis de trayectoria del dron
