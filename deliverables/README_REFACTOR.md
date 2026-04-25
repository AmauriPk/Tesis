## Entregable de refactorización (RPAS Micro)

Archivos incluidos en esta carpeta:
- `app.py`
- `config.py`
- `models.py`
- `ptz_controller.py`
- `index.html` (antes `templates/index.html`)
- `admin_camera.html` (antes `templates/admin_camera.html`)
- `login.html` (antes `templates/login.html`)
- `style.css` (antes `static/style.css`)
- `dashboard.js` (antes `static/dashboard.js`)

### Qué se eliminó y por qué
- `app.py`: `_bbox_off_center()` no se utilizaba en ningún flujo.
- `app.py`: endpoints `/progress/<job_id>` y `/progress_stream/<job_id>` no estaban referenciados por el frontend (se usaba `/video_progress`), y `progress_stream` mantenía `import json` huérfano.
- `config.py`: secciones `ALERT_CONFIG` / `SECURITY_CONFIG` y helpers `get_config()` / `validate_config()` + bloque `__main__` no eran consumidos por el servidor.

### Reglas de tesis preservadas (intactas)
1) **YOLO en GPU**: el backend fuerza `cuda:0` en `load_yolo_model()`.
2) **RTSP + stream MJPEG**: se mantiene el generador `multipart/x-mixed-replace` (`/video_feed`).
3) **ONVIF Auto-Discovery asíncrono**: se mantiene `_probe_onvif_ptz_capability()` y el refresco en hilo `_maybe_refresh_onvif_probe()`.
4) **Bloqueo de rutas PTZ si cámara fija**: se mantiene `_require_ptz_capable()` (abort 403).
5) **Frontend UI dinámica**: `dashboard.js` muestra/oculta el panel PTZ según `/api/camera_status`.
6) **Regla Enjambre**: el tracking PTZ prioriza el **bbox más grande** (`_select_priority_detection()`).
7) **Mitigación de aves**: se requiere persistencia de frames antes de confirmar detección y antes de mover PTZ (`_DetectionPersistence`).

### Ajustes/variables útiles
- `DETECTION_PERSISTENCE_FRAMES` (env): frames consecutivos requeridos para confirmar detección (default `3`).

