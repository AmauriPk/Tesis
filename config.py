"""ConfiguraciÃ³n central del proyecto (entorno, rutas, cÃ¡mara, modelo de visiÃ³n)."""

from __future__ import annotations

import os

from src.system_core import env_bool as _env_bool
from src.system_core import env_float as _env_float
from src.system_core import env_int as _env_int

# ======================== CONFIGURACIÃ“N RTSP ========================
RTSP_CONFIG = {
    "enabled": True,
    "url": os.environ.get("RTSP_URL", "0"),
    "username": os.environ.get("RTSP_USERNAME", "usuario"),
    "password": os.environ.get("RTSP_PASSWORD", "password"),
    "timeout": _env_int("RTSP_TIMEOUT", 10),
    "buffer_size": _env_int("RTSP_BUFFER_SIZE", 1),
}

# ======================== CONFIGURACIÃ“N ONVIF ========================
ONVIF_CONFIG = {
    "host": os.environ.get("ONVIF_HOST", ""),
    "port": _env_int("ONVIF_PORT", 80),
    "username": os.environ.get("ONVIF_USERNAME", os.environ.get("RTSP_USERNAME", "")),
    "password": os.environ.get("ONVIF_PASSWORD", os.environ.get("RTSP_PASSWORD", "")),
}

# ======================== CONFIGURACIÃ“N YOLO ========================
YOLO_CONFIG = {
    "model_path": os.environ.get("YOLO_MODEL_PATH", "runs/detect/weights/best.pt"),
    "device": os.environ.get("YOLO_DEVICE", "cuda:0"),
    "confidence": _env_float("YOLO_CONFIDENCE", 0.8),
    "verbose": _env_bool("YOLO_VERBOSE", False),
}

# ======================== CONFIGURACIÃ“N DE VIDEO ========================
VIDEO_CONFIG = {
    "width": _env_int("VIDEO_WIDTH", 1280),
    "height": _env_int("VIDEO_HEIGHT", 720),
    "fps": _env_int("VIDEO_FPS", 30),
    "jpeg_quality": _env_int("JPEG_QUALITY", 80),
    "inference_interval": _env_int("INFERENCE_INTERVAL", 1),
}

# ======================== CONFIGURACIÃ“N DE FLASK ========================
FLASK_CONFIG = {
    "debug": _env_bool("FLASK_DEBUG", False),
    "host": os.environ.get("FLASK_HOST", "0.0.0.0"),
    "port": _env_int("FLASK_PORT", 5000),
    "threaded": _env_bool("FLASK_THREADED", True),
    "max_content_length": _env_int("FLASK_MAX_CONTENT_LENGTH", 500 * 1024 * 1024),
}

# ======================== CONFIGURACIÃ“N DE ALMACENAMIENTO ========================
STORAGE_CONFIG = {
    "db_path": os.environ.get("SQLITE_DB_PATH", "detections.db"),
    "upload_folder": os.environ.get("UPLOAD_FOLDER", "uploads"),
    "detections_frames_folder": os.environ.get("DETECTIONS_FRAMES_FOLDER", "detections_frames"),
    "allowed_extensions": {"png", "jpg", "jpeg", "mp4", "avi", "mov"},
    "dataset_recoleccion_folder": os.environ.get("DATASET_RECOLECCION_FOLDER", "dataset_recoleccion"),
}

# ======================== RUTAS DEL PROYECTO ========================
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATASET_TRAINING_ROOT = os.environ.get("DATASET_TRAINING_ROOT", os.path.join(PROJECT_ROOT, "dataset_entrenamiento"))

DATASET_NEGATIVE_DIR = os.path.join(DATASET_TRAINING_ROOT, "train", "images")
DATASET_POSITIVE_PENDING_DIR = os.path.join(DATASET_TRAINING_ROOT, "pending", "images")
DATASET_RECOLECCION_FOLDER = STORAGE_CONFIG.get("dataset_recoleccion_folder") or os.path.join(
    PROJECT_ROOT, "dataset_recoleccion"
)
DATASET_LIMPIAS_INBOX_DIR = os.path.join(DATASET_RECOLECCION_FOLDER, "limpias")

# Crear directorios si no existen
for _dir in [DATASET_NEGATIVE_DIR, DATASET_POSITIVE_PENDING_DIR, DATASET_LIMPIAS_INBOX_DIR]:
    try:
        os.makedirs(_dir, exist_ok=True)
    except Exception:
        pass

__all__ = [
    "FLASK_CONFIG",
    "ONVIF_CONFIG",
    "PROJECT_ROOT",
    "RTSP_CONFIG",
    "STORAGE_CONFIG",
    "VIDEO_CONFIG",
    "YOLO_CONFIG",
    "DATASET_TRAINING_ROOT",
    "DATASET_NEGATIVE_DIR",
    "DATASET_POSITIVE_PENDING_DIR",
    "DATASET_RECOLECCION_FOLDER",
    "DATASET_LIMPIAS_INBOX_DIR",
    "_env_bool",
    "_env_float",
    "_env_int",
]
