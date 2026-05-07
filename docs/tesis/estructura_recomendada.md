# Estructura Recomendada del Proyecto — SIRAN

## Estructura actual observada

```
Proyecto01/
├── app.py                          # Monolito principal (~3800 líneas)
├── config.py                       # Configuración central
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md                       # A crear
├── instance/                       # Flask instance (app.db SQLite)
├── src/
│   ├── __init__.py
│   ├── system_core.py              # DB models, PTZ, metrics, utilidades
│   ├── video_processor.py          # RTSP reader, LiveVideoProcessor
│   └── services/
│       ├── __init__.py
│       └── video_export_service.py # Extraído - exportación de video
├── templates/
│   ├── index.html
│   ├── admin.html
│   ├── admin_camera.html
│   └── login.html
├── static/
│   ├── style.css
│   ├── dashboard.js
│   ├── admin_dataset.js
│   ├── admin_camera.js
│   ├── admin_model_params.js
│   ├── results/                    # Videos e imágenes generados (NO en Git)
│   ├── evidence/                   # Evidencias (NO en Git)
│   ├── top_detections/             # Detecciones top (NO en Git)
│   └── capturas/
├── docs/
│   ├── refactor_video_export.md
│   └── tesis/                      # Documentación de tesis (NUEVO)
├── uploads/                        # Temporal (NO en Git)
├── dataset_recoleccion/            # Dataset recolectado (NO en Git)
├── dataset_entrenamiento/          # Dataset para entrenamiento (NO en Git)
├── runs/                           # Resultados YOLO (NO en Git)
├── CAMARA/                         # (verificar contenido)
└── venv_new/                       # Entorno virtual (NO en Git)
```

---

## Estructura recomendada (a futuro)

```
Proyecto01/
├── app.py                          # Solo startup, init, config global
├── config.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── src/
│   ├── __init__.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py                 # Modelo User
│   │   └── camera_config.py        # Modelo CameraConfig
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py                 # /login, /logout
│   │   ├── dashboard.py            # /, /admin_dashboard
│   │   ├── ptz.py                  # /ptz_move, /api/ptz_stop, tracking
│   │   ├── analysis.py             # /upload_detect, /video_progress
│   │   ├── events.py               # /api/recent_alerts, events, export
│   │   ├── dataset.py              # /api/classify_image, etc.
│   │   └── admin.py                # /admin/camera, /api/test_connection
│   ├── services/
│   │   ├── __init__.py
│   │   ├── video_export_service.py # YA IMPLEMENTADO
│   │   ├── detection_service.py    # YOLO inference, draw_detections
│   │   ├── event_service.py        # DetectionEventWriter
│   │   └── ptz_service.py          # PTZWorker, PTZController
│   ├── core/
│   │   ├── __init__.py
│   │   ├── system_core.py          # Utilidades, clamp, FrameRecord
│   │   └── metrics_writer.py       # MetricsDBWriter
│   └── video/
│       ├── __init__.py
│       └── video_processor.py      # RTSPLatestFrameReader, LiveVideoProcessor
├── templates/
├── static/
└── docs/
    └── tesis/
```

---

## Refactorizaciones recomendadas

| Prioridad | Módulo a extraer | Origen | Destino | Motivo |
|---|---|---|---|---|
| 1 (hecha) | Video export | app.py:3700-3823 | `src/services/video_export_service.py` | Lógica FFmpeg/codec independiente |
| 2 | Rutas de análisis | app.py:3549-3698 | `src/routes/analysis.py` | Rutas + lógica de jobs |
| 3 | Rutas PTZ | app.py:3401-3528 | `src/routes/ptz.py` | Rutas + estado PTZ |
| 4 | Rutas de eventos | app.py:2177-2590 | `src/routes/events.py` | Consultas de alertas y eventos |
| 5 | Rutas de dataset | app.py:2938-3228 | `src/routes/dataset.py` | Gestión de imágenes |
| 6 | Rutas de admin | app.py:1876-2144 | `src/routes/admin.py` | Configuración de cámara |
| 7 | Rutas de autenticación | app.py:1796-1843 | `src/routes/auth.py` | Login/logout |
| 8 | Modelos SQLAlchemy | src/system_core.py | `src/models/` | Separar modelos de utilidades |

---

## Orden recomendado de refactor

1. Extraer primero los módulos **sin dependencias externas** (video_export ya hecho)
2. Luego los módulos **con dependencias claras** (análisis, eventos, dataset)
3. Finalmente los módulos **con estado global** (PTZ, auth) que requieren más cuidado
4. Al extraer una ruta, registrar el Blueprint en `app.py` con el prefijo correcto
5. Verificar funcionamiento después de cada extracción (no hacer todo en un commit)

---

## Riesgos de refactorizar todo de golpe

1. **Variables globales compartidas:** `yolo_model`, `live_processor`, `ptz_worker`, `state_lock`, `auto_tracking_enabled` están referenciadas en múltiples funciones. Extraer rutas requiere pasar estas referencias como parámetros o encapsularlas en un objeto de estado.

2. **Blueprints de Flask:** el paso a Blueprints requiere registrar cada Blueprint con prefijo y configurar el contexto de aplicación correctamente.

3. **Sin pruebas:** sin pruebas automatizadas, cualquier refactor puede romper funcionalidad silenciosamente.

4. **Historial de Git:** es preferible hacer el refactor en una rama separada para poder comparar con la versión anterior si algo falla.

**Recomendación:** hacer el refactor de forma incremental, un módulo por commit, verificando que el sistema arranca y funciona correctamente después de cada extracción.
