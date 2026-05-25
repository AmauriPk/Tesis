"""ConfiguraciÃ³n central del proyecto (entorno, rutas, cÃ¡mara, modelo de visiÃ³n)."""

from __future__ import annotations

import os

from src.system_core import env_bool as _env_bool
from src.system_core import env_float as _env_float
from src.system_core import env_int as _env_int

# ======================== CONFIGURACIÃ"N RTSP ========================
RTSP_CONFIG = {
    "enabled": True,
    "url": os.environ.get("RTSP_URL", "0"),
    "username": os.environ.get("RTSP_USERNAME", "usuario"),
    "password": os.environ.get("RTSP_PASSWORD", "password"),
    "timeout": _env_int("RTSP_TIMEOUT", 5),    # RF-01: conexión en < 5 s
    "buffer_size": _env_int("RTSP_BUFFER_SIZE", 1),
}

# ======================== CONFIGURACIÃ"N ONVIF ========================
ONVIF_CONFIG = {
    "host": os.environ.get("ONVIF_HOST", ""),
    "port": _env_int("ONVIF_PORT", 80),
    "username": os.environ.get("ONVIF_USERNAME", os.environ.get("RTSP_USERNAME", "")),
    "password": os.environ.get("ONVIF_PASSWORD", os.environ.get("RTSP_PASSWORD", "")),
    "rtsp_port": _env_int("RTSP_PORT", 554),  # puerto RTSP; si aparece como ONVIF port indica mala config
}

# ======================== CONFIGURACIÃ"N YOLO ========================
YOLO_CONFIG = {
    "model_path": os.environ.get("YOLO_MODEL_PATH", "runs/detect/weights/best.pt"),
    "device": os.environ.get("YOLO_DEVICE", "cuda:0"),
    "confidence": _env_float("YOLO_CONFIDENCE", 0.8),
    "verbose":       _env_bool("YOLO_VERBOSE",  False),
    "iou_clamp_min": _env_float("IOU_CLAMP_MIN", 0.10),
    "iou_clamp_max": _env_float("IOU_CLAMP_MAX", 0.95),
}

# ======================== CONFIGURACIÃ"N PTZ ========================
PTZ_CONFIG = {
    # Tracking — cuándo y con qué velocidad mover la cámara
    "target_ttl":       _env_float("PTZ_TRACKING_TARGET_TTL",       3.0),   # RO-04: T=3 s
    "command_interval": _env_float("PTZ_TRACKING_COMMAND_INTERVAL", 0.35),
    "max_speed":        _env_float("PTZ_TRACKING_MAX_SPEED",        0.50),
    "min_speed":        _env_float("PTZ_TRACKING_MIN_SPEED",        0.12),
    "pan_duration":     _env_float("PTZ_TRACKING_PAN_DURATION",     0.30),
    "tilt_duration":    _env_float("PTZ_TRACKING_TILT_DURATION",    0.55),
    "pan_speed":        _env_float("PTZ_TRACKING_PAN_SPEED",        0.35),
    "tilt_speed":       _env_float("PTZ_TRACKING_TILT_SPEED",       0.45),
    "tolerance":        _env_float("PTZ_TRACKING_TOLERANCE",        0.15),  # RO-03: zona central 30% = ±15%
    "edge_tilt_boost":  _env_float("PTZ_TRACKING_EDGE_TILT_BOOST",  1.4),
    # Proporcionalidad (RO-05): pan_cmd = k_pan * error_x, tilt_cmd = -k_tilt * error_y
    "k_pan":            _env_float("PTZ_K_PAN",                     0.8),
    "k_tilt":           _env_float("PTZ_K_TILT",                    0.8),
    # Inspección / patrullaje automático
    "inspection_idle_s":   _env_float("PTZ_INSPECTION_IDLE_S",        10.0),
    "continuous_360":      _env_bool("PTZ_INSPECTION_CONTINUOUS_360",  False),
    "inspection_mode":     os.environ.get("PTZ_INSPECTION_MODE", "sweep"),
    "inspection_speed":    _env_float("PTZ_INSPECTION_SPEED",          0.45),
    "inspection_duration": _env_float("PTZ_INSPECTION_DURATION",       4.0),
    "inspection_pause":    _env_float("PTZ_INSPECTION_PAUSE",          0.7),
    # General
    "ptz_move_duration": _env_float("PTZ_MOVE_DURATION",            0.25),
    # Inversión de ejes (hardware-specific)
    "invert_pan":        _env_bool("PTZ_INVERT_PAN",                 False),
    "invert_tilt":       _env_bool("PTZ_INVERT_TILT",                False),
    # Readquisición activa (RO-04): barrido angular ±15° tras pérdida de target
    "reacq_enabled":    _env_bool("PTZ_REACQ_ENABLED",   True),
    "reacq_duration_s": _env_float("PTZ_REACQ_DURATION_S", 3.0),  # RO-04: T=3 s
    "reacq_speed":      _env_float("PTZ_REACQ_SPEED",    0.20),   # velocidad suave
    "reacq_pulse_s":    _env_float("PTZ_REACQ_PULSE_S",  0.40),   # duración de cada pulso
    "reacq_pause_s":    _env_float("PTZ_REACQ_PAUSE_S",  0.20),   # pausa entre pulsos
    # Continuidad IoU entre frames (RO-06): evita movimientos bruscos por falsos positivos
    "iou_continuity_enabled": _env_bool("PTZ_IOU_CONTINUITY",      True),
    "iou_continuity_min":     _env_float("PTZ_IOU_CONTINUITY_MIN",  0.50),  # RO-06
    "iou_continuity_misses":  _env_int("PTZ_IOU_CONTINUITY_MISSES", 3),    # frames consecutivos antes de readquisición
}

# ======================== TRACKER (SORT simplificado) ========================
TRACKER_CONFIG = {
    "iou_threshold": _env_float("TRACKER_IOU_THRESHOLD", 0.30),
    "max_misses":    _env_int("TRACKER_MAX_MISSES",       3),
    "min_hits":      _env_int("TRACKER_MIN_HITS",         1),
}

# ======================== CONFIGURACIÃ"N DE VIDEO ========================
VIDEO_CONFIG = {
    "width": _env_int("VIDEO_WIDTH", 1280),
    "height": _env_int("VIDEO_HEIGHT", 720),
    "fps": _env_int("VIDEO_FPS", 30),
    "jpeg_quality": _env_int("JPEG_QUALITY", 80),
    "inference_interval": _env_int("INFERENCE_INTERVAL", 1),
}

# ======================== CONFIGURACIÃ"N DE FLASK ========================
FLASK_CONFIG = {
    "debug": _env_bool("FLASK_DEBUG", False),
    "host": os.environ.get("FLASK_HOST", "0.0.0.0"),
    "port": _env_int("FLASK_PORT", 5000),
    "threaded": _env_bool("FLASK_THREADED", True),
    "max_content_length": _env_int("FLASK_MAX_CONTENT_LENGTH", 500 * 1024 * 1024),
}

# ======================== SEGURIDAD ========================
SECURITY_CONFIG = {
    # Cifrado de credenciales en DB (Fernet).
    # CRITICO: cambiar el servidor sin migrar esta clave corrompe las credenciales almacenadas.
    # Generar con: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    "encrypt_key":             os.environ.get("SIRAN_ENCRYPT_KEY", ""),
    "login_max_attempts":      _env_int("LOGIN_MAX_ATTEMPTS",    5),
    "login_lockout_seconds":   _env_int("LOGIN_LOCKOUT_SECONDS", 60),
    "login_window_seconds":    _env_int("LOGIN_WINDOW_SECONDS",  300),
    # Override de debug PTZ: fuerza PTZ como ready sin hardware real (peligroso en produccion)
    "debug_ptz_ready":         _env_bool("DEBUG_PTZ_READY",      False),
    "debug_camera_cfg":        _env_bool("DEBUG_CAMERA_CFG",     False),
    "session_idle_timeout_s":  _env_int("SESSION_IDLE_TIMEOUT_SECONDS", 900),
    "detection_persistence_frames": _env_int("DETECTION_PERSISTENCE_FRAMES", 3),
}

# ======================== CONFIGURACIÃ"N DE ALMACENAMIENTO ========================
STORAGE_CONFIG = {
    "db_path": os.environ.get("SQLITE_DB_PATH", "detections.db"),
    "upload_folder": os.environ.get("UPLOAD_FOLDER", "uploads"),
    "detections_frames_folder": os.environ.get("DETECTIONS_FRAMES_FOLDER", "detections_frames"),
    "evidence_dir": os.environ.get("EVIDENCE_DIR", "static/evidence"),
    "evidence_min_confidence": _env_float("EVIDENCE_MIN_CONFIDENCE", 0.85),
    "evidence_cooldown_s":     _env_float("EVIDENCE_COOLDOWN_SECONDS", 5.0),
    "evidence_max_files":      _env_int("EVIDENCE_MAX_FILES", 500),
    "evidence_max_age_days":   _env_int("EVIDENCE_MAX_AGE_DAYS", 30),
    "ffmpeg_bin":              os.environ.get("FFMPEG_BIN", ""),
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

# ======================== CONFIGURACIÓN APP ========================
APP_CONFIG = {
    "log_dir":                 os.environ.get("LOG_DIR", "logs"),
    "database_url":            os.environ.get("DATABASE_URL", "sqlite:///app.db"),
    "session_cookie_samesite": os.environ.get("SESSION_COOKIE_SAMESITE", "Strict"),
    "session_cookie_secure":   os.environ.get("SESSION_COOKIE_SECURE", "").strip().lower() in {
                                   "1", "true", "t", "yes", "y", "on"},
    "metrics_enabled":         os.environ.get("METRICS_LOGGING", "1").strip().lower()
                               not in {"0", "false", "no", "off"},
}

__all__ = [
    "APP_CONFIG",
    "FLASK_CONFIG",
    "ONVIF_CONFIG",
    "PTZ_CONFIG",
    "PROJECT_ROOT",
    "RTSP_CONFIG",
    "SECURITY_CONFIG",
    "STORAGE_CONFIG",
    "TRACKER_CONFIG",
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
