# Plan de Pruebas Funcionales — SIRAN

## PF-01: Inicio de sesión válido

| Campo | Detalle |
|---|---|
| **Objetivo** | Verificar que el sistema autentica correctamente a un usuario válido |
| **Procedimiento** | 1. Navegar a `http://localhost:5000` 2. Ingresar usuario `operador` y contraseña `operador123` 3. Presionar "Iniciar sesión" |
| **Resultado esperado** | Redirección al dashboard principal con la pestaña "En Vivo" activa |
| **Evidencia sugerida** | Captura de pantalla del dashboard tras login exitoso |
| **Captura recomendada** | `cap_01_login_exitoso.png` |
| **Criterio de aceptación** | La página carga el stream y el menú de operador sin errores |

---

## PF-02: Inicio de sesión inválido

| Campo | Detalle |
|---|---|
| **Objetivo** | Verificar que el sistema rechaza credenciales incorrectas |
| **Procedimiento** | 1. Ingresar usuario o contraseña incorrectos 2. Presionar "Iniciar sesión" |
| **Resultado esperado** | Mensaje de error "Credenciales inválidas" sin redireccionamiento |
| **Evidencia sugerida** | Captura del mensaje de error |
| **Criterio de aceptación** | El sistema no redirige ni expone información del sistema |

---

## PF-03: Carga de imagen para análisis

| Campo | Detalle |
|---|---|
| **Objetivo** | Verificar que el análisis manual de imagen funciona correctamente |
| **Procedimiento** | 1. Iniciar sesión como operador 2. Ir a pestaña "Análisis Manual" 3. Seleccionar una imagen JPG con un dron visible 4. Presionar "Analizar" |
| **Resultado esperado** | La imagen resultante se muestra con bounding boxes sobre el dron; se reporta confianza > 0.6 |
| **Evidencia sugerida** | Captura de la imagen analizada con bounding box visible |
| **Captura recomendada** | `cap_03_analisis_imagen_resultado.png` |
| **Criterio de aceptación** | La imagen de resultado existe en `static/results/`, el JSON incluye `result_url` y `detections_count >= 1` |

---

## PF-04: Carga de video para análisis

| Campo | Detalle |
|---|---|
| **Objetivo** | Verificar el análisis manual de video con inferencia frame a frame |
| **Procedimiento** | 1. Iniciar sesión como operador 2. Seleccionar un video MP4 corto (5-15 segundos) 3. Iniciar análisis 4. Esperar a que el progreso llegue a 100% |
| **Resultado esperado** | Se genera `result_<job_id>_raw.mp4` con detecciones anotadas; si FFmpeg disponible, también `result_<job_id>_browser.mp4` |
| **Evidencia sugerida** | Captura del video reproducido en el navegador con bounding boxes |
| **Captura recomendada** | `cap_04_analisis_video_resultado.png` |
| **Criterio de aceptación** | `/video_progress` devuelve `result_video_playable: true` (con FFmpeg) o `false` con `video_output_warning` explicativo |

---

## PF-05: Stream de video en vivo

| Campo | Detalle |
|---|---|
| **Objetivo** | Verificar que el stream RTSP se muestra con detecciones en tiempo real |
| **Procedimiento** | 1. Conectar cámara IP configurada 2. Iniciar sesión como operador 3. Navegar a pestaña "En Vivo" |
| **Resultado esperado** | El stream muestra video en tiempo real con bounding boxes cuando se detecta un objeto |
| **Evidencia sugerida** | Captura del stream con detección activa y badge de estado |
| **Captura recomendada** | `cap_05_stream_en_vivo_con_deteccion.png` |
| **Criterio de aceptación** | El stream se actualiza continuamente, los bounding boxes se dibujan con confianza visible |

---

## PF-06: Control PTZ manual

| Campo | Detalle |
|---|---|
| **Objetivo** | Verificar que el joystick PTZ mueve la cámara en la dirección indicada |
| **Procedimiento** | 1. Configurar cámara PTZ con ONVIF 2. Iniciar sesión como operador 3. Usar el joystick para mover la cámara arriba/abajo/izquierda/derecha |
| **Resultado esperado** | La cámara se mueve suavemente en la dirección indicada y se detiene al soltar el joystick |
| **Evidencia sugerida** | Video o secuencia de capturas mostrando el movimiento de la cámara |
| **Captura recomendada** | `cap_06_ptz_manual_activo.png` |
| **Criterio de aceptación** | `POST /ptz_move` devuelve `{ok: true}` y la cámara responde físicamente |

---

## PF-07: Tracking automático

| Campo | Detalle |
|---|---|
| **Objetivo** | Verificar que el sistema sigue automáticamente el dron detectado |
| **Procedimiento** | 1. Activar tracking automático desde el toggle 2. Mover el dron frente a la cámara 3. Observar si la cámara corrige su posición para mantener el dron centrado |
| **Resultado esperado** | La cámara se mueve para mantener el bounding box del dron cerca del centro del frame |
| **Evidencia sugerida** | Video mostrando el tracking activo |
| **Captura recomendada** | `cap_07_tracking_automatico.png` |
| **Criterio de aceptación** | El dron permanece en el área central del frame durante al menos 5 segundos de movimiento |

---

## PF-08: Inspección automática (patrullaje)

| Campo | Detalle |
|---|---|
| **Objetivo** | Verificar que la cámara ejecuta el barrido automático cuando la inspección está activa |
| **Procedimiento** | 1. Activar modo "Inspección automática" 2. Observar el movimiento de la cámara durante 30 segundos |
| **Resultado esperado** | La cámara ejecuta un barrido horizontal continuo de forma autónoma |
| **Captura recomendada** | `cap_08_inspeccion_automatica.png` |
| **Criterio de aceptación** | `POST /api/inspection_mode {enabled: true}` devuelve `{enabled: true}` y la cámara inicia el barrido |

---

## PF-09: Generación de eventos de detección

| Campo | Detalle |
|---|---|
| **Objetivo** | Verificar que las detecciones se agrupan correctamente en eventos |
| **Procedimiento** | 1. Pasar un dron frente a la cámara durante 5-10 segundos 2. Consultar `GET /api/recent_detection_events` |
| **Resultado esperado** | Se registra al menos un evento con `status='closed'`, confianza máxima, conteo de detecciones y timestamps |
| **Captura recomendada** | `cap_09_eventos_deteccion.png` |
| **Criterio de aceptación** | El evento aparece en la API con todos los campos correctos |

---

## PF-10: Generación de evidencias visuales

| Campo | Detalle |
|---|---|
| **Objetivo** | Verificar que se generan archivos de evidencia cuando hay detección |
| **Procedimiento** | 1. Exponer un dron a la cámara 2. Revisar la carpeta `static/evidence/` |
| **Resultado esperado** | Aparecen archivos JPG con el formato `evidence_<timestamp>_conf<NN>.jpg` |
| **Criterio de aceptación** | Las imágenes contienen el frame con la detección y el bounding box |

---

## PF-11: Clasificación de imágenes en dataset

| Campo | Detalle |
|---|---|
| **Objetivo** | Verificar que el administrador puede clasificar imágenes del dataset |
| **Procedimiento** | 1. Iniciar sesión como admin 2. Abrir sección Dataset 3. Clasificar una imagen como "positivo" |
| **Resultado esperado** | La imagen se mueve a `dataset_entrenamiento/pending/images/` |
| **Criterio de aceptación** | `POST /api/classify_image` devuelve éxito y el archivo se mueve correctamente |

---

## PF-12: Exportación de eventos CSV

| Campo | Detalle |
|---|---|
| **Objetivo** | Verificar que la exportación de eventos funciona |
| **Procedimiento** | 1. Iniciar sesión como admin 2. Navegar a `GET /api/export_detection_events.csv` |
| **Resultado esperado** | Se descarga un archivo CSV con los campos: id, started_at, ended_at, max_confidence, detection_count, status, source |
| **Criterio de aceptación** | El CSV es legible, tiene encabezados correctos y datos correspondientes a los eventos registrados |

---

## PF-13: Compatibilidad de cámara ONVIF

| Campo | Detalle |
|---|---|
| **Objetivo** | Verificar que el sistema detecta correctamente si la cámara soporta PTZ |
| **Procedimiento** | 1. Configurar host, puerto, usuario y contraseña ONVIF 2. Presionar "Probar conexión" |
| **Resultado esperado** | Respuesta `{status: "success", is_ptz: true/false}` en menos de 6 segundos |
| **Criterio de aceptación** | El resultado es consistente con el hardware real de la cámara |

---

## PF-14: Rendimiento básico de inferencia

| Campo | Detalle |
|---|---|
| **Objetivo** | Medir la latencia de inferencia YOLO en el hardware disponible |
| **Procedimiento** | 1. Iniciar el servidor con GPU disponible 2. Activar stream RTSP 3. Observar la consola para registros `[METRICS]` con `inference_ms` |
| **Resultado esperado** | Inferencia en GPU: < 50 ms por frame. En CPU: variable según hardware. |
| **Evidencia sugerida** | Captura de consola mostrando `inference_ms` |
| **Captura recomendada** | `cap_14_yolo_cuda_consola.png` |
| **Criterio de aceptación** | El stream RTSP no se congela; la latencia de inferencia es tolerable para el caso de uso |
