# Limpieza de Imports — SIRAN

Fecha: 2026-05-07

---

## app.py — Imports eliminados (aplicados)

Los siguientes imports estaban definidos en app.py pero no se usaban en el cuerpo de app.py. Las rutas que los usan los importan directamente desde sus propios archivos.

| Import | Motivo de eliminación |
|---|---|
| `import base64` | Solo usado en `admin_camera.py` (lo importa directamente) |
| `import heapq` | Solo usado en `analysis.py` (lo importa directamente) |
| `import secrets` | Solo usado en `analysis.py` (lo importa directamente) |
| `import shutil` | No usado en app.py (solo en `dataset.py`) |
| `from urllib.parse import urlparse` | Solo usado en `admin_camera.py` y `auth.py` |
| `from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError` | Solo usado en `admin_camera.py` |
| `import cv2` | No hay llamadas `cv2.` en app.py; los módulos que lo usan lo importan directamente |
| `import numpy as np` | No hay llamadas `np.` en app.py; los módulos que lo usan lo importan directamente |
| `from werkzeug.utils import secure_filename` | Solo usado en `analysis.py` |
| `try: import ffmpeg` / `ffmpeg = None` | El módulo `ffmpeg` nunca se llama en app.py |
| `from src.services.video_export_service import (create_video_writer, make_browser_compatible_mp4, resolve_ffmpeg_bin, is_valid_video_file)` | `analysis.py` importa estos directamente; app.py no los llama |
| `draw_detections` (en import de `src.video_processor`) | Solo usado en `analysis.py`; se conservan `LiveStreamDeps`, `LiveVideoProcessor`, `RTSPLatestFrameReader` |
| `clamp` (en import de `src.system_core`) | app.py usa `_clamp` local; se conserva `select_priority_detection` |
| `set_configured_camera_type` (en import de `src.services.camera_state_service`) | No se llama en app.py |
| `flash` (en import de Flask) | **Conservado** — usado en `role_required` de app.py (línea ~153) |
| `render_template` (en import de Flask) | Solo usado en blueprints (`admin_camera.py`, `dashboard.py`, `auth.py`) |
| `Response` (en import de Flask) | Solo usado en `dashboard.py` |
| `login_user` (en import de flask_login) | Solo usado en `auth.py` |
| `logout_user` (en import de flask_login) | Solo usado en `auth.py` |

---

## analysis.py — Imports eliminados (aplicados)

| Import | Motivo de eliminación |
|---|---|
| `is_valid_video_file` (de video_export_service) | Importado pero nunca llamado en analysis.py; la validación se hace manualmente con `os.path.getsize` |

---

## Imports conservados por precaución

| Archivo | Import conservado | Motivo |
|---|---|---|
| `app.py` | `import queue` | Usado en `DetectionEventWriter._q` |
| `app.py` | `import threading` | Usado en múltiples partes de app.py |
| `app.py` | `import sqlite3` | Usado en `DetectionEventWriter._connect` y `_ensure_detection_events_schema` |
| `app.py` | `import time` | Usado en múltiples lugares |
| `app.py` | `from datetime import datetime` | Usado en `DetectionEventWriter` y MODEL_PARAMS |
| `app.py` | `from functools import wraps` | Usado en `role_required` decorator |
| `app.py` | `from ultralytics import YOLO` | Carga del modelo |
| `app.py` | `try: import torch` | Detección de GPU en `load_yolo_model` y `DETECTION_PERSISTENCE_FRAMES` |
| `app.py` | `select_priority_detection` de system_core | Usado en `_select_priority_detection` wrapper (aunque este wrapper es código muerto, mantener import) |
| `app.py` | `LiveStreamDeps, LiveVideoProcessor, RTSPLatestFrameReader` | Usados directamente en app.py |
| `app.py` | Todos los imports de `src.routes.*` | Blueprints registrados |
| `app.py` | `PTZStateService, PTZCommandWorker, TrackingPTZWorker` | Instanciados en app.py |
| `video_processor.py` | `torch` | Detección de GPU en `LiveVideoProcessor._run` |

---

## Imports dudosos (conservados)

| Archivo | Import | Razón de duda |
|---|---|---|
| `app.py` | `select_priority_detection` | Solo usada en `_select_priority_detection` wrapper que parece código muerto, pero se mantiene el import porque `_select_priority_detection` podría ser llamada desde JavaScript/template en un escenario no obvio |
| `app.py` | `FrameRecord` de system_core | Se usa al construir records en `_metrics_enqueue_with_events` — aunque se llama desde `analysis.py` y `video_processor.py`, `_metrics_enqueue_with_events` que lo usa también está en app.py |
| `config.py` | `_env_bool, _env_float, _env_int` en `__all__` | Se exportan para uso externo vía `from config import ...` en app.py |

---

## Efecto de la limpieza

- **Líneas eliminadas de app.py**: ~25 líneas de imports
- **Impacto en funcionalidad**: Ninguno — todos los módulos que usaban esas dependencias importan directamente
- **Riesgo**: Muy bajo — Python levantaría ImportError si algo aún dependiera de estos imports
