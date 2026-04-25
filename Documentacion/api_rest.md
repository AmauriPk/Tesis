# api_rest.md â€“ DocumentaciÃ³n tÃ©cnica de la API REST (Flask)

Este documento describe los endpoints HTTP/REST del backend Flask del proyecto **â€œPrototipo de sistema de visiÃ³n artificial para la detecciÃ³n de RPAS Microâ€**. La API estÃ¡ orientada al consumo por la interfaz web y a validaciones tÃ©cnicas del despliegue.

## Convenciones generales

- **AutenticaciÃ³n:** los endpoints operan bajo sesiÃ³n autenticada (Flask-Login). En ausencia de sesiÃ³n, el backend ejecuta el flujo de autenticaciÃ³n correspondiente.
- **Formato de respuesta:** JSON para rutas de estado/control; `multipart/x-mixed-replace` para streaming.
- **Fail-Safe PTZ:** el control PTZ se habilita Ãºnicamente si el backend determina `is_ptz_capable = true` mediante Auto-Discovery ONVIF. En caso contrario, se rechazan comandos PTZ.

## Resumen de endpoints solicitados

| Endpoint | MÃ©todo | Finalidad |
|---|---:|---|
| `/video_feed` | GET | Stream multipart (RTSP â†’ navegador). |
| `/api/camera_status` | GET | Estado de Auto-Discovery ONVIF (PTZ vs fija). |
| `/ptz_move` | POST | Movimiento PTZ condicional (solo PTZ). |
| `/ptz_stop` | POST | DetenciÃ³n PTZ condicional (solo PTZ). |
| `/upload_detect` | POST | DetecciÃ³n manual (archivo subido; job asÃ­ncrono). |

---

## 1) `GET /video_feed`

**PropÃ³sito:** entregar un flujo de video en vivo en formato multipart para consumo directo por el navegador. El backend obtiene frames desde una fuente RTSP y publica el resultado como secuencia de JPEG.

**Respuesta esperada:**

- `200 OK`
- `Content-Type: multipart/x-mixed-replace; boundary=frame`
- Cuerpo: frames JPEG delimitados por `boundary=frame`.

**Notas tÃ©cnicas:**

- La adquisiciÃ³n se basa en OpenCV y utiliza una estrategia de â€œÃºltimo frameâ€ para minimizar latencia.
- El stream integra anotaciones de detecciÃ³n (bounding boxes) cuando la inferencia estÃ¡ activa.

---

## 2) `GET /api/camera_status`

**PropÃ³sito:** reportar el resultado del autodescubrimiento de hardware por ONVIF. Este endpoint es la base de la UI condicional (apariciÃ³n/desapariciÃ³n del panel PTZ).

**Respuesta esperada (JSON):**

```json
{ "is_ptz_capable": true }
```

**InterpretaciÃ³n:**

- `true`: la cÃ¡mara expone capacidades/servicio PTZ accesible por ONVIF.
- `false`: la cÃ¡mara no es PTZ o el autodescubrimiento ONVIF fallÃ³ por cualquier motivo (host no accesible, credenciales invÃ¡lidas, ONVIF deshabilitado, timeouts). El sistema entra en modo **CÃ¡mara Fija (fail-safe)**.

---

## 3) `POST /ptz_move`

**PropÃ³sito:** solicitar un movimiento PTZ. El backend encola la orden para ejecuciÃ³n asÃ­ncrona (hilo separado) con el objetivo de no introducir â€œlagâ€ en el flujo de video.

**PolÃ­tica de seguridad (fail-safe):**

- Si `is_ptz_capable = false` â†’ `403 Forbidden`.

### 3.1) Payload por direcciÃ³n

**Request (JSON):**

```json
{ "direction": "left" }
```

Direcciones soportadas: `left`, `right`, `up`, `down`.

### 3.2) Payload vectorial

**Request (JSON):**

```json
{ "x": 0.4, "y": -0.2, "zoom": 0.0, "duration_s": 0.18 }
```

- `x`, `y`, `zoom`: velocidades normalizadas (rango lÃ³gico `[-1.0, 1.0]`).
- `duration_s`: duraciÃ³n del movimiento continuo (segundos).

**Respuesta esperada (JSON):**

```json
{ "ok": true }
```

**Errores esperados:**

- `400 Bad Request`: payload invÃ¡lido.
- `403 Forbidden`: cÃ¡mara no PTZ (fail-safe).

---

## 4) `POST /ptz_stop`

**PropÃ³sito:** detener el movimiento PTZ.

**PolÃ­tica de seguridad (fail-safe):**

- Si `is_ptz_capable = false` â†’ `403 Forbidden`.

**Respuesta esperada (JSON):**

```json
{ "ok": true }
```

---

## 5) `POST /upload_detect`

**PropÃ³sito:** iniciar una detecciÃ³n manual sobre un archivo subido (imagen o video). El procesamiento ocurre en background, retornando un identificador de job.

**Request:**

- `Content-Type: multipart/form-data`
- Campo requerido: `file`
- Extensiones soportadas: `.png`, `.jpg`, `.jpeg`, `.mp4`, `.avi`, `.mov`

**Respuesta esperada (JSON):**

```json
{ "success": true, "job_id": "..." }
```

**Errores tÃ­picos (JSON):**

```json
{ "success": false, "error": "ExtensiÃ³n no permitida" }
```

```json
{ "success": false, "error": "Modelo YOLO no disponible" }
```


