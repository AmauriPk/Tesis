# arquitectura_modulos.md â€“ IntegraciÃ³n arquitectÃ³nica por mÃ³dulos

## 1. VisiÃ³n general

El prototipo **â€œSistema de visiÃ³n artificial para la detecciÃ³n de RPAS Microâ€** se implementa como una aplicaciÃ³n web en Flask con un pipeline de visiÃ³n por computador orientado a tiempo real. El diseÃ±o se fundamenta en:

- **Agnosticismo de hardware:** el sistema no presupone si la cÃ¡mara es PTZ o fija; lo determina mediante Auto-Discovery ONVIF.
- **Modularidad:** adquisiciÃ³n, inferencia, control mecÃ¡nico y presentaciÃ³n se desacoplan para facilitar mantenimiento y evoluciÃ³n.
- **Fail-safe:** ante incertidumbre o fallas ONVIF, el sistema adopta el modo â€œCÃ¡mara Fijaâ€, bloqueando control PTZ y simplificando la interfaz.
- **Concurrencia controlada:** la inferencia y el control PTZ se ejecutan en hilos separados para evitar degradaciÃ³n del streaming.

La soluciÃ³n se organiza en cuatro mÃ³dulos lÃ³gicos, los cuales interactÃºan por medio de buffers de estado y endpoints HTTP.

---

## 2. MÃ³dulo 1 â€“ AdquisiciÃ³n y Auto-descubrimiento (RTSP/ONVIF)

### 2.1 AdquisiciÃ³n RTSP

Este mÃ³dulo es responsable de obtener video desde una cÃ¡mara IP mediante RTSP y disponibilizar frames al pipeline de inferencia. Para minimizar latencia:

- La lectura RTSP se ejecuta en un hilo dedicado.
- Se preserva Ãºnicamente el frame mÃ¡s reciente (â€œÃºltimo frameâ€), evitando acumulaciÃ³n de cola cuando la carga computacional se incrementa.
- La salida se utiliza tanto para inferencia como para el stream web.

### 2.2 Auto-Discovery ONVIF (habilitaciÃ³n de PTZ)

El backend integra `onvif-zeep` para interrogar la cÃ¡mara (servicios/capabilities ONVIF). El resultado se materializa en el booleano `is_ptz_capable`:

- Si se detecta PTZ por capacidades o por disponibilidad del servicio, `is_ptz_capable = true`.
- Si no existe PTZ o falla ONVIF (conexiÃ³n/credenciales/servicio), `is_ptz_capable = false`.

**Fail-safe:** en estado `false` el sistema opera como cÃ¡mara fija, bloquea endpoints PTZ y el frontend oculta el panel de control mecÃ¡nico.

---

## 3. MÃ³dulo 2 â€“ Inferencia (YOLO26 en GPU)

La inferencia se realiza con YOLO26 (end-to-end sin NMS), ejecutado estrictamente en GPU (RTX 4060) mediante `ultralytics` y OpenCV para el manejo de frames.

Funciones principales:

- Ejecutar inferencia sobre frames en tiempo real (configurable por intervalo).
- Generar bounding boxes y confidencias del objetivo.
- Anotar visualmente el frame para el streaming web.
- Actualizar un estado de detecciÃ³n (alertas, conteo, confianza, timestamp) consultado por la UI.

El mÃ³dulo se diseÃ±a para operar de forma asÃ­ncrona y no bloquear el thread de respuesta HTTP del servidor.

---

## 4. MÃ³dulo 3 â€“ Control MecÃ¡nico AsÃ­ncrono (ONVIF PTZ)

Este mÃ³dulo implementa el control PTZ sobre ONVIF bajo dos condiciones estrictas:

1) **La cÃ¡mara debe ser PTZ segÃºn Auto-Discovery** (`is_ptz_capable = true`).  
2) Las operaciones de control se ejecutan **fuera del pipeline de video** para no generar lag.

CaracterÃ­sticas:

- Cola de comandos PTZ para desacoplar peticiones HTTP de ejecuciÃ³n ONVIF.
- Worker en hilo dedicado que consume la cola y realiza `ContinuousMove` / `Stop`.
- Rate limiting para evitar saturaciÃ³n del dispositivo PTZ.
- Bloqueo explÃ­cito de `/ptz_move` y `/ptz_stop` con `403` si el estado es no-PTZ.

### Tracking AutomÃ¡tico

Cuando la cÃ¡mara es PTZ y el operador habilita tracking automÃ¡tico:

- Se calcula el error de centrado del bounding box (distancia al centro del frame).
- Se derivan correcciones pan/tilt y se envÃ­an al worker PTZ en hilos separados.
- La comunicaciÃ³n mecÃ¡nica se mantiene asÃ­ncrona para preservar la fluidez del streaming.

---

## 5. MÃ³dulo 4 â€“ Interfaz y LÃ³gica Condicional (JavaScript/DOM)

El frontend consume el estado del backend y ajusta su interfaz en tiempo de ejecuciÃ³n:

- En la carga, consulta `/api/camera_status`.
- Si el resultado es PTZ, se muestra el panel de control (joystick/botones) y el switch de tracking automÃ¡tico.
- Si el resultado es â€œCÃ¡mara Fijaâ€, el panel PTZ se oculta/elimina del DOM, manteniendo la UI en modo fijo.

Este mÃ³dulo reduce el riesgo de operaciÃ³n incorrecta al no exponer controles no soportados por el hardware detectado.

---

## 6. IntegraciÃ³n (flujo de interacciÃ³n)

1) RTSP adquiere frames y publica el â€œÃºltimo frameâ€ disponible.  
2) YOLO26 consume frames, genera detecciones y anota el frame.  
3) `/video_feed` transmite el frame anotado como multipart al navegador.  
4) ONVIF determina `is_ptz_capable`; el frontend ajusta su UI con base en `/api/camera_status`.  
5) Si hay PTZ y el tracking estÃ¡ activo, la inferencia genera correcciones y el mÃ³dulo mecÃ¡nico ejecuta los comandos en background.


