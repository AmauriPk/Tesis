# Aporte de la Tesis — SIRAN

## Aporte tecnológico

El principal aporte tecnológico del presente trabajo es la **integración de múltiples tecnologías heterogéneas en un sistema funcional unificado**:

1. **Visión artificial aplicada:** implementación de un modelo YOLO entrenado específicamente para detección de aeronaves no tripuladas, integrado en un pipeline de procesamiento de video en tiempo real.

2. **Control de hardware mediante protocolos estándar:** integración del protocolo ONVIF para control PTZ, permitiendo que el sistema controle físicamente la orientación de la cámara de forma autónoma.

3. **Procesamiento de video en tiempo real:** arquitectura basada en hilos concurrentes que permite procesar el stream RTSP, aplicar inferencia YOLO y servir el resultado como MJPEG al navegador de forma simultánea y sin bloqueo.

4. **Sistema de seguimiento automático:** algoritmo de tracking reactivo que calcula el desplazamiento del objetivo en el frame y genera comandos de corrección PTZ para mantener el dron centrado.

5. **Pipeline de exportación de video compatible con web:** solución que aborda la brecha entre los codecs de escritura de OpenCV (mp4v) y los formatos reproducibles en navegadores modernos, mediante transcodificación FFmpeg con fallbacks progresivos.

---

## Aporte metodológico

1. **Caracterización del flujo operativo:** el sistema define y documenta los roles de operador y administrador, los flujos de trabajo asociados y las interfaces necesarias para cada uno.

2. **Estrategia de priorización de objetivos:** se propone y documenta una regla de priorización para el tracking en presencia de múltiples drones detectados simultáneamente (selección por área de bounding box — estrategia de enjambre).

3. **Mitigación de detecciones ruidosas:** implementación de persistencia de frames (N frames consecutivos para confirmar una detección), reduciendo el impacto de detecciones falsas aisladas (aves, ruido visual).

4. **Esquema de eventos agrupados:** diseño de un esquema de registro que agrupa detecciones individuales en eventos de duración definida, diferenciando el registro técnico de alta frecuencia del registro de eventos operativos de baja frecuencia.

---

## Aporte práctico

1. **Prototipo funcional operativo:** el sistema puede ser instalado y ejecutado con hardware comercial disponible (cámara IP con soporte RTSP y ONVIF, PC con o sin GPU).

2. **Gestión de dataset para reentrenamiento:** el sistema facilita la recolección y clasificación de imágenes durante su operación normal, generando datos etiquetados para mejorar el modelo YOLO en iteraciones futuras.

3. **Configuración sin reiniciar el servicio:** el sistema permite actualizar parámetros críticos del modelo (umbral de confianza, IoU, persistencia) y configuraciones de cámara (RTSP/ONVIF) sin interrumpir el servicio, lo cual es relevante en escenarios de operación continua.

---

## Utilidad para análisis visual

El sistema produce múltiples tipos de evidencia visual útil para el análisis posterior:

- **Imágenes estáticas anotadas:** frames con bounding boxes, etiqueta del objeto y confianza de detección
- **Videos anotados:** secuencias completas de detección con bounding boxes cuadro a cuadro
- **Evidencias de alta confianza:** imágenes del momento de mayor certeza de cada detección
- **Registro temporal:** timestamps ISO de cada detección con confianza y coordenadas

Esta información puede ser utilizada para análisis de incidentes, validación del modelo y presentación de resultados.

---

## Utilidad para apoyo a la toma de decisiones

El sistema no toma decisiones operativas críticas por sí solo, sino que:

1. **Reduce la carga cognitiva del operador:** en lugar de monitorear el video manualmente, el operador recibe alertas automáticas de detección.
2. **Provee evidencia objetiva:** las imágenes y eventos registrados constituyen evidencia verificable de la presencia de un dron.
3. **Facilita la respuesta temprana:** el sistema alerta en tiempo real, permitiendo al operador tomar decisiones (documentar, alertar, reposicionar la cámara) de forma oportuna.
4. **Mantiene historial auditable:** los eventos de detección quedan registrados con timestamps y evidencias, conformando un historial consultable.

---

## ¿Por qué no es solo aplicar YOLO?

Aplicar YOLO a una imagen es trivial con la API de Ultralytics:

```python
model = YOLO("model.pt")
results = model("imagen.jpg")
```

El valor del presente trabajo reside en lo que rodea a ese llamado:

| Componente | Complejidad que agrega |
|---|---|
| Stream RTSP en tiempo real | Gestión de hilos, reconexión, latencia |
| Control PTZ automático | Protocolo ONVIF, geometría de corrección, velocidad |
| Sistema de tracking | Algoritmo de centrado, tolerancias, saturación de cola |
| Inspección autónoma | Barrido programado, integración con tracking |
| Análisis de video offline | Job queue, progreso, transcodificación FFmpeg |
| Registro de eventos | Esquema de agrupación temporal, SQLite concurrente |
| Gestión de dataset | Clasificación, reversión, estructura de carpetas |
| Interfaz web multirol | Autenticación, roles, interfaz adaptada por usuario |

---

## Diferencia entre modelo de detección y sistema completo

| Modelo YOLO aislado | Sistema SIRAN |
|---|---|
| Requiere proporcionar imágenes manualmente | Captura frames de cámara en tiempo real |
| No controla hardware | Controla cámara PTZ vía ONVIF |
| No persiste resultados | Registra eventos, evidencias y métricas |
| No tiene interfaz de usuario | Tiene interfaz web multirol accesible desde navegador |
| No gestiona dataset | Facilita la recolección y clasificación de datos |
| No puede seguir un objetivo | Implementa tracking automático |

---

## Aportación como prototipo funcional

La aportación del trabajo de tesis es demostrar que, con herramientas de código abierto y hardware comercial accesible, es técnicamente factible construir un sistema integrado de detección y seguimiento de aeronaves no tripuladas que:

1. Opere en tiempo real con el hardware disponible
2. Sea controlable de forma remota desde un navegador web estándar
3. Genere evidencia visual verificable de las detecciones
4. Permita al administrador ajustar el comportamiento del sistema sin interrumpir la operación
5. Produzca datos estructurados para análisis posterior y mejora continua del modelo
