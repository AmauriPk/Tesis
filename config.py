"""Configuración del prototipo RPAS Micro (RTSP/YOLO/Video/Flask/Storage)."""

import os


def _env_bool(name: str, default: bool) -> bool:
    """Lee una variable de entorno booleana con tolerancia a múltiples formatos."""
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip().lower()
    if value in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "f", "no", "n", "off"}:
        return False
    return default


def _env_int(name: str, default: int) -> int:
    """Lee una variable de entorno int; si falla, retorna `default`."""
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value.strip())
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    """Lee una variable de entorno float; si falla, retorna `default`."""
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value.strip())
    except Exception:
        return default

# ======================== CONFIGURACIÓN RTSP ========================
RTSP_CONFIG = {
    "enabled": True,  # Habilitar streaming RTSP
    # Seguridad: evita credenciales embebidas en repo; usa variables de entorno.
    "url": os.environ.get("RTSP_URL", "rtsp://usuario:password@CAMERA_IP:554/Streaming/Channels/101"),
    "username": os.environ.get("RTSP_USERNAME", "usuario"),
    "password": os.environ.get("RTSP_PASSWORD", "password"),
    "timeout": 30,  # Timeout de conexión en segundos (placeholder; OpenCV maneja reconexión)
    "buffer_size": 1,  # Tamaño de buffer (evitar latencia)
}

# ======================== CONFIGURACIÓN YOLO ========================
YOLO_CONFIG = {
    "model_path": os.environ.get("YOLO_MODEL_PATH", "runs/detect/weights/best.pt"),
    "device": os.environ.get("YOLO_DEVICE", "cuda:0"),  # GPU a usar (cuda:0 para RTX 4060)
    "confidence": _env_float("YOLO_CONFIDENCE", 0.8),  # Threshold de confianza mínimo
    "verbose": _env_bool("YOLO_VERBOSE", False),  # Mostrar logs YOLO detallados
    # Claves legacy (reservadas para futuras extensiones).
    "save_detections": True,
    "min_confidence_db": 0.80,
}

# ======================== CONFIGURACIÓN DE VIDEO ========================
VIDEO_CONFIG = {
    "width": _env_int("VIDEO_WIDTH", 1280),  # Ancho de frame
    "height": _env_int("VIDEO_HEIGHT", 720),  # Alto de frame
    "fps": _env_int("VIDEO_FPS", 30),  # FPS objetivo
    "jpeg_quality": _env_int("JPEG_QUALITY", 80),  # Calidad JPEG (1-100)
    "inference_interval": _env_int("INFERENCE_INTERVAL", 1),  # Procesar cada N frames (1 = todos)
}

# ======================== CONFIGURACIÓN DE FLASK ========================
FLASK_CONFIG = {
    "debug": _env_bool("FLASK_DEBUG", False),  # Modo debug (no recomendado en producción)
    "host": os.environ.get("FLASK_HOST", "0.0.0.0"),  # Host (0.0.0.0 para acceso remoto)
    "port": _env_int("FLASK_PORT", 5000),  # Puerto
    "threaded": _env_bool("FLASK_THREADED", True),  # Soporte multi-thread
    "max_content_length": _env_int("FLASK_MAX_CONTENT_LENGTH", 500 * 1024 * 1024),  # Máximo upload 500MB
}

# ======================== CONFIGURACIÓN DE ALMACENAMIENTO ========================
STORAGE_CONFIG = {
    "db_path": os.environ.get("SQLITE_DB_PATH", "detections.db"),
    "upload_folder": os.environ.get("UPLOAD_FOLDER", "uploads"),
    "detections_frames_folder": os.environ.get("DETECTIONS_FRAMES_FOLDER", "detections_frames"),
    "allowed_extensions": {"png", "jpg", "jpeg", "mp4", "avi", "mov"},
    # Claves legacy (no usadas actualmente por el servidor).
    "cleanup_old_uploads": True,
    "cleanup_days": 7,
}
