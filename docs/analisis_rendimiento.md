# Análisis de Rendimiento — SIRAN

Fecha: 2026-05-07

---

## Tabla de cuellos de botella

| Cuello de botella | Impacto | Recomendación | Dificultad | Cuándo |
|---|---|---|---|---|
| **YOLO inference en GPU** | Alto — es el proceso más costoso (10–100ms/frame según hardware) | `inference_interval` ya configurable. Asegurar que `INFERENCE_INTERVAL >= 2` para 30fps. | Baja | Ahora (configuración) |
| **`LiveVideoProcessor._run` — loop sin sleep** | Medio — el loop corre sin yield excepto en idle, puede consumir CPU innecesariamente cuando RTSP está activo | Agregar `time.sleep(0.001)` al final del loop principal si la inferencia fue muy rápida | Baja | Post-defensa |
| **`RTSPLatestFrameReader._run` — lectura continua** | Bajo-Medio — `cap.read()` es bloqueante. Si RTSP tiene latencia alta, el hilo queda bloqueado. El timeout de `CAP_PROP_READ_TIMEOUT_MSEC` está configurado | OK: diseño correcto (hilo dedicado, último frame). No cambiar. | — | — |
| **SQLite escritura de métricas** | Bajo — `MetricsDBWriter` usa WAL + batch de 100 registros. Buen diseño. | Asegurar que `detections.db` esté en SSD (no en red) | Muy baja | Ahora (verificación) |
| **`DetectionEventWriter._run`** | Bajo — procesa records de una cola independiente, no bloquea video. | OK | — | — |
| **Generación de evidencias** | Bajo-Medio — `cv2.imwrite` en el loop de video puede bloquear brevemente. Hay cooldown de 5s por defecto. | El cooldown es correcto. Si se necesita más rendimiento, mover imwrite a hilo separado | Media | Post-defensa |
| **`PTZ command worker`** | Bajo — ONVIF sobre red puede bloquear. Mitigado por hilo separado + cola. Rate-limit de 200ms. | Correcto | — | — |
| **`TrackingPTZWorker`** | Bajo — loop con 200ms sleep, bajo costo. | OK | — | — |
| **`_InspectionPatrolWorker`** | Bajo — loop con 250ms sleep. | OK | — | — |
| **Polling del frontend** (`/detection_status`, `/api/camera_status`)  | Medio — si el JS hace polling cada <1s, genera muchos requests. Verificar en dashboard.js. | Asegurar que el intervalo de polling sea ≥ 1000ms en JS | Baja | Ahora (verificación JS) |
| **`/api/recent_alerts` y `/api/recent_detection_events`** | Medio — abren conexión SQLite en cada request, sin connection pool | Aceptable para tesis (bajo volumen). Para producción: añadir caché de 1-2s. | Media | Post-defensa |
| **Carga inicial del servidor** | Medio — `_probe_onvif_ptz_capability()` se llama en `app_context` al arrancar, puede bloquear si hay timeout ONVIF | Mover a un hilo separado con `threading.Thread(daemon=True).start()` | Baja | Post-defensa |
| **Video análisis manual (upload_detect)** | Alto — inferencia frame-a-frame de video sin paralelismo. Para videos largos puede tardar minutos. | Diseño correcto: el análisis corre en hilo separado, no bloquea el servidor. | — | — |
| **`static/results/` crecimiento** | Bajo-Medio — los MP4 y AVI se acumulan indefinidamente si no se limpian | Agregar endpoint admin de limpieza o job periódico | Media | Post-defensa |
| **`static/evidence/` crecimiento** | Bajo-Medio — `cleanup_old_evidence` existe pero no se llama automáticamente | Activar como endpoint `/api/admin/cleanup_evidence` o cron | Media | Post-defensa |
| **`backfill_from_detections`** | Bajo — solo corre una vez al arranque si `detection_events` está vacía. Acotado a 2000 rows. | OK | — | — |

---

## Parámetros de rendimiento configurables vía .env

| Variable | Default | Descripción |
|---|---|---|
| `INFERENCE_INTERVAL` | 1 | Inferir cada N frames (1=todos, 2=cada 2 frames, etc.) |
| `CONFIDENCE_THRESHOLD` | 0.60 | Umbral YOLO (más alto = menos falsos positivos) |
| `PERSISTENCE_FRAMES` | 3 | Frames consecutivos para confirmar detección |
| `EVIDENCE_COOLDOWN_SECONDS` | 5 | Segundos entre guardados de evidencia |
| `EVIDENCE_MIN_CONFIDENCE` | 0.85 | Confianza mínima para guardar evidencia |
| `PTZ_TRACKING_COMMAND_INTERVAL` | 0.35 | Intervalo mínimo entre comandos PTZ de tracking |
| `PTZ_TRACKING_MAX_SPEED` | 0.50 | Velocidad máxima de tracking PTZ |
| `EVENT_GAP_SECONDS` | 3.0 | Gap para separar eventos de detección |
| `METRICS_LOGGING` | 1 | Activar/desactivar telemetría SQLite |

---

## Recomendaciones inmediatas (antes de la defensa)

1. Verificar en `dashboard.js` que el polling de `/detection_status` sea ≥ 1000ms.
2. Configurar `INFERENCE_INTERVAL=2` en `.env` si la GPU tiene problemas de latencia.
3. Asegurar que `detections.db` esté en disco local (no en carpeta compartida de red).
