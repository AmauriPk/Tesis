# Apoyo para Capítulo 4 — Resultados

*Este documento proporciona estructura y guía para la redacción del Capítulo 4. Los valores numéricos marcados con [COMPLETAR] deben ser sustituidos con los resultados reales obtenidos durante las pruebas.*

---

## 4.1 Resultados de detección

### 4.1.1 Inferencia en tiempo real

Se realizaron pruebas de inferencia sobre el stream de video en vivo con el hardware disponible. Los resultados obtenidos fueron los siguientes:

| Métrica | GPU (CUDA) | CPU (fallback) |
|---|---|---|
| Tiempo promedio de inferencia (ms) | [COMPLETAR] | [COMPLETAR] |
| FPS promedio procesados | [COMPLETAR] | [COMPLETAR] |
| Uso de memoria GPU/RAM | [COMPLETAR] | [COMPLETAR] |

*Captura recomendada: consola mostrando `[METRICS]` con valores de `inference_ms` durante operación normal.*

### 4.1.2 Confianza de detección

Durante las sesiones de prueba, las detecciones sobre el dron de entrenamiento presentaron los siguientes valores de confianza:

| Condición | Confianza promedio | Confianza máxima observada |
|---|---|---|
| Dron a ~5 m | [COMPLETAR] | [COMPLETAR] |
| Dron a ~10 m | [COMPLETAR] | [COMPLETAR] |
| Con fondo complejo | [COMPLETAR] | [COMPLETAR] |

---

## 4.2 Resultados de análisis de imagen

Se analizaron [COMPLETAR] imágenes de prueba (N con dron, N sin dron). Los resultados fueron:

| Categoría | Cantidad | Detecciones correctas | Falsos positivos | No detectados |
|---|---|---|---|---|
| Imágenes con dron | [N] | [N] | — | [N] |
| Imágenes sin dron | [N] | — | [N] | — |

*Captura recomendada: imagen de análisis con bounding box claramente visible sobre el dron.*

---

## 4.3 Resultados de análisis de video

Se procesaron [COMPLETAR] videos de prueba. Los parámetros promedio observados fueron:

| Métrica | Valor |
|---|---|
| Frames procesados por minuto de video | [COMPLETAR] |
| Tiempo total de procesamiento (video de 30s) | [COMPLETAR] |
| Detecciones por video en promedio | [COMPLETAR] |
| Confianza promedio en video | [COMPLETAR] |
| Videos con `result_video_playable: true` | [N/N] |

*Captura recomendada: video reproducido en navegador con bounding boxes y controles de reproducción visibles.*

---

## 4.4 Resultados de control PTZ

Las pruebas de control PTZ manual y automático se realizaron con la cámara [COMPLETAR - modelo/marca]:

| Prueba | Resultado |
|---|---|
| Tiempo de respuesta del joystick (local) | [COMPLETAR] ms |
| Detección de capacidad PTZ por ONVIF | Exitosa / [COMPLETAR] ms |
| Centrado en objetivo (tracking activo) | [COMPLETAR - descripción cualitativa] |
| Pérdida de tracking al salir del frame | Observada / No observada |

*Captura recomendada: frame del stream con dron detectado y cámara centrada.*

---

## 4.5 Resultados de tracking automático

El modo de tracking automático fue evaluado en [COMPLETAR] sesiones de prueba:

- El sistema mantuvo el tracking activo durante un promedio de [COMPLETAR] segundos por sesión
- La cámara respondió al movimiento del dron con una latencia observada de aproximadamente [COMPLETAR] ms
- En [COMPLETAR] de los casos, el tracking se recuperó después de oclusión temporal breve (<2 s)
- En [COMPLETAR] de los casos, el tracking se perdió por salida del campo de visión

*Observaciones:* [COMPLETAR con observaciones cualitativas del comportamiento del tracking]

---

## 4.6 Resultados de inspección automática

El modo de inspección (patrullaje) ejecutó barridos continuos de [COMPLETAR] segundos de duración. Se observó que:

- La cámara completó el ciclo de barrido sin interrupciones en [COMPLETAR/N] intentos
- Al detectar un dron durante el barrido, el tracking intervino correctamente en [COMPLETAR/N] casos
- La velocidad de barrido configurada (PTZ_SWEEP_SPEED = [COMPLETAR]) resultó adecuada para la cobertura del área de prueba

---

## 4.7 Resultados de eventos y evidencias

Durante las sesiones de prueba se generaron los siguientes datos:

| Tipo de dato | Cantidad total |
|---|---|
| Eventos de detección registrados | [COMPLETAR] |
| Imágenes de evidencia generadas | [COMPLETAR] |
| Tamaño promedio por imagen de evidencia | [COMPLETAR] KB |
| Espacio total consumido por evidencias | [COMPLETAR] MB |

Los eventos mostraron agrupación temporal correcta: detecciones separadas por más de 3 segundos generaron eventos independientes, mientras que detecciones continuas se agruparon en un único evento.

---

## 4.8 Resultados de gestión de dataset

El módulo de dataset permitió clasificar [COMPLETAR] imágenes durante las sesiones de prueba:

| Clasificación | Cantidad |
|---|---|
| Positivas (con dron) | [COMPLETAR] |
| Negativas (sin dron) | [COMPLETAR] |
| Revertidas | [COMPLETAR] |

Las imágenes clasificadas quedaron disponibles para el proceso de reentrenamiento del modelo YOLO.

---

## 4.9 Limitaciones observadas durante las pruebas

1. **Iluminación:** en condiciones de contraluz intenso, la confianza de detección disminuyó significativamente. *[COMPLETAR con valores observados]*

2. **Distancia:** por encima de [COMPLETAR] metros de distancia, el dron ocupaba un área de bounding box inferior a [COMPLETAR] píxeles, reduciendo la confianza a valores por debajo del umbral.

3. **FFmpeg:** en el entorno de prueba, FFmpeg fue resuelto mediante `imageio_ffmpeg`. La transcodificación de videos de 30 segundos tomó aproximadamente [COMPLETAR] segundos adicionales.

4. **Latencia PTZ:** la latencia entre la detección del error de posición y el inicio del movimiento de la cámara fue de aproximadamente [COMPLETAR] ms, lo que puede causar sobrecompensación a velocidades de tracking altas.

---

## 4.10 Interpretación de resultados

Los resultados obtenidos permiten concluir que el sistema SIRAN cumple con los objetivos de un prototipo funcional de detección y seguimiento de aeronaves no tripuladas mediante visión artificial:

1. La inferencia YOLO en tiempo real es viable con GPU, produciendo latencias dentro del rango aceptable para la aplicación.
2. El tracking automático PTZ mantiene el objetivo centrado en condiciones de movimiento moderado, aunque con las limitaciones de latencia del hardware.
3. La integración RTSP-YOLO-ONVIF-interfaz web funciona de forma cohesiva en un único sistema.
4. El módulo de registro de eventos proporciona un historial auditable de las detecciones.

---

## 4.11 Tablas sugeridas para el documento

1. Tabla de especificaciones del hardware de prueba (CPU, GPU, RAM, OS)
2. Tabla de parámetros de configuración utilizados durante las pruebas
3. Tabla comparativa de tiempos de inferencia GPU vs CPU
4. Tabla de eventos de detección por sesión de prueba
5. Tabla de resultados del análisis de imágenes (TP, FP, FN)

---

## 4.12 Figuras sugeridas para el documento

1. Captura del dashboard en operación normal con stream y detección activa
2. Imagen analizada con bounding box visible sobre el dron
3. Video procesado mostrado en el navegador con controles de reproducción
4. Panel de alertas recientes con evidencias visuales
5. Panel de eventos de detección con timestamps
6. Vista del panel de administración con configuración RTSP/ONVIF (sin credenciales)
7. Vista del gestor de dataset con imágenes clasificadas
8. Captura de consola mostrando carga del modelo YOLO en CUDA
9. Gráfica de distribución de confianza de detecciones (si se generan suficientes datos)

---

## 4.13 Capturas que debe tomar

Ver el archivo `docs/tesis/capturas_necesarias.md` para la lista completa de capturas recomendadas, su propósito y cómo tomarlas.

---

## 4.14 Cómo presentar resultados sin exagerar

- Describir los resultados como obtenidos en "condiciones controladas de laboratorio"
- Indicar explícitamente las condiciones de prueba (distancia, iluminación, hardware)
- No generalizar a condiciones no probadas
- Usar frases como "se observó", "los resultados indican", "en las pruebas realizadas" en lugar de afirmaciones absolutas
- Reconocer las limitaciones observadas con honestidad técnica
- Comparar con el estado esperado de un prototipo, no con sistemas comerciales
