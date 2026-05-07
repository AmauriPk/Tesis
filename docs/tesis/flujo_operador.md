# Flujo del Operador — SIRAN

## Rol

El operador es el usuario principal en campo. Tiene acceso al dashboard principal (`/`) y puede:
- Visualizar el stream de video en vivo
- Activar/desactivar tracking automático
- Activar/desactivar modo de inspección (patrullaje)
- Controlar la cámara PTZ manualmente (joystick)
- Analizar imágenes y videos de forma manual
- Revisar alertas recientes y evidencias
- Detener el PTZ

No puede modificar configuraciones de cámara ni parámetros del modelo YOLO (esas son tareas del administrador).

---

## Flujo 1: Inicio de sesión

1. El operador navega a `http://<servidor>:5000`
2. El sistema redirige a `/login`
3. El operador ingresa usuario y contraseña
4. Flask-Login valida credenciales contra la tabla `user` en SQLite
5. Si válido: redirige a `/?tab=live` (dashboard, pestaña de video en vivo)
6. Si inválido: muestra mensaje "Credenciales inválidas"

**Credenciales por defecto:** usuario `operador`, contraseña `operador123` (configurable por variable de entorno `DEFAULT_OPERATOR_PASSWORD`)

---

## Flujo 2: Visualización del stream en vivo

1. El dashboard carga la pestaña "En Vivo" por defecto
2. El frontend solicita `/video_feed` (stream MJPEG)
3. La cámara RTSP está siendo leída por `RTSPLatestFrameReader` en un hilo separado
4. Cada frame es procesado por `LiveVideoProcessor` (aplica YOLO, dibuja bounding boxes)
5. Los frames se sirven como `multipart/x-mixed-replace` al navegador
6. El operador ve el video con detecciones superpuestas en tiempo real

Si la cámara no está disponible, el stream muestra un frame de error o queda congelado.

---

## Flujo 3: Detección en vivo

1. Mientras el stream está activo, YOLO aplica inferencia a cada frame (o cada N frames, según `INFERENCE_INTERVAL`)
2. Las detecciones con confianza ≥ umbral configurado se dibujan con bounding box en el frame
3. El frontend consulta `/detection_status` periódicamente para actualizar el badge de estado
4. Si hay detección confirmada (persistencia de N frames consecutivos), se genera:
   - Un registro en `inference_frames` (telemetría)
   - Una imagen de evidencia en `static/evidence/`
   - Se actualiza o crea un evento en `detection_events`
5. El panel de alertas recientes se actualiza mostrando las últimas evidencias

---

## Flujo 4: Control manual PTZ (joystick)

*Solo disponible si la cámara está configurada como PTZ y ONVIF está activo.*

1. El operador usa el joystick virtual en la interfaz para indicar dirección
2. El frontend envía `POST /ptz_move` con payload `{x, y, zoom, duration_s}`
3. Flask verifica que la cámara sea PTZ
4. El comando se encola en `PTZWorker`
5. El worker envía `continuous_move` a `PTZController` (ONVIF)
6. La cámara se mueve en la dirección indicada
7. Al soltar el joystick, el frontend envía `POST /api/ptz_stop`

*Si el operador presiona STOP manual, también se desactiva el tracking automático.*

---

## Flujo 5: Tracking automático

*Solo disponible si la cámara es PTZ.*

1. El operador activa el toggle "Tracking automático" en la interfaz
2. El frontend envía `POST /api/auto_tracking` con `{enabled: true}`
3. El sistema verifica capacidad PTZ; si no disponible, devuelve `{enabled: false}`
4. Con tracking activo, en cada frame con detección:
   - El `LiveVideoProcessor` calcula el centro del bounding box más grande
   - Calcula el error respecto al centro del frame
   - Si el error supera la tolerancia configurada (`PTZ_TOLERANCE_FRAC`), encola un movimiento correctivo en `PTZWorker`
5. La cámara sigue automáticamente el dron detectado
6. El operador puede desactivar el tracking con el toggle o presionando STOP

---

## Flujo 6: Inspección automática (patrullaje)

*Solo disponible si la cámara es PTZ.*

1. El operador activa el toggle "Inspección automática"
2. El frontend envía `POST /api/inspection_mode` con `{enabled: true}`
3. Con inspección activa, la cámara ejecuta un barrido angular continuo (sweep) de forma autónoma
4. Si durante el barrido se detecta un dron y el tracking está habilitado, el tracking tiene prioridad y la cámara se centra en el objetivo
5. Al desactivar la inspección, la cámara se detiene

---

## Flujo 7: Análisis manual de imagen

1. El operador navega a la pestaña "Análisis Manual" del dashboard
2. Selecciona una imagen (JPG/PNG) desde su equipo
3. El frontend envía `POST /upload_detect` con el archivo
4. El servidor crea un `job_id` único y lanza un hilo de procesamiento
5. El frontend hace polling a `/video_progress?job_id=<id>` cada segundo
6. El hilo aplica YOLO a la imagen y guarda el resultado en `static/results/result_<job_id>.jpg`
7. El frontend muestra la imagen resultante con las detecciones dibujadas
8. Se muestra el conteo de detecciones y la confianza promedio

---

## Flujo 8: Análisis manual de video

1. El operador selecciona un video (MP4/AVI/MOV)
2. El frontend envía `POST /upload_detect` con el archivo
3. El servidor crea un `job_id` y lanza un hilo de procesamiento
4. El hilo procesa el video frame a frame:
   - Aplica YOLO a cada frame
   - Escribe el frame anotado en `result_<job_id>_raw.mp4`
   - Acumula estadísticas y frames de mayor confianza (top 10)
5. Al terminar, intenta transcodificar el raw a `result_<job_id>_browser.mp4` (si FFmpeg disponible)
6. El frontend recibe la URL del video resultante y lo reproduce en el navegador (o muestra botón de descarga si no es playable)
7. Los frames top 10 se muestran en una galería

---

## Flujo 9: Revisión de alertas recientes

1. El panel de alertas recientes (sidebar o sección del dashboard) consulta `/api/recent_alerts`
2. La API devuelve las últimas N evidencias con imagen en base64, confianza y timestamp
3. El operador puede ver las alertas sin navegar fuera del dashboard

---

## Flujo 10: Cierre de sesión

1. El operador presiona "Cerrar sesión"
2. El frontend navega a `/logout`
3. Flask-Login invalida la sesión
4. El sistema redirige a `/login`

---

## Flujo recomendado para demostración de tesis

1. Iniciar sesión como operador
2. Mostrar el stream en vivo con detección activa (si hay cámara disponible)
3. Si la cámara es PTZ: demostrar joystick manual
4. Activar tracking automático: mostrar cómo la cámara sigue el dron
5. Mostrar panel de alertas recientes con evidencias generadas
6. Analizar una imagen de dron: mostrar resultado con bounding box
7. Analizar un video corto: mostrar el video anotado
8. Mostrar la sección de eventos de detección con conteos y timestamps
