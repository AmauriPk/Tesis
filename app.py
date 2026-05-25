from __future__ import annotations
"""
SIRAN — Sistema Integrado de Reconocimiento de Aeronaves No Tripuladas (tesis).

Reglas INTRANSFERIBLES (NO eliminar; solo optimizar/refactorizar):
1) YOLO26 en GPU (cuda:0) para inferencia.
2) Ingesta de video RTSP y entrega MJPEG vía `multipart/x-mixed-replace`.
3) ONVIF Auto-Discovery asíncrono (hilos) para determinar si la cámara es PTZ o Fija:
   - Si es fija: bloquear rutas de movimiento PTZ.
   - Si es PTZ: permitir joystick y tracking automático.
4) Frontend: ocultar/mostrar joystick basándose en la respuesta del Auto-Discovery.
5) Regla de priorización (Enjambre): el tracking PTZ se centra en el bounding box MÁS GRANDE.
6) Mitigación de aves: persistencia de frames antes de confirmar una detección.
"""
import logging
import logging.handlers
import os
import sqlite3
import secrets
import threading
import time
from datetime import datetime
from functools import wraps


def setup_logging() -> None:
    log_dir = os.environ.get("LOG_DIR", "logs")
    os.makedirs(log_dir, exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    fh = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "siran.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(ch)
    root.addHandler(fh)

setup_logging()

logger = logging.getLogger(__name__)

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    request,
    session,
    url_for,
)
from flask_login import (
    LoginManager,
    current_user,
    logout_user,
    login_required,
)

from config import FLASK_CONFIG, ONVIF_CONFIG, PTZ_CONFIG, RTSP_CONFIG, SECURITY_CONFIG, STORAGE_CONFIG, VIDEO_CONFIG, YOLO_CONFIG, _env_float, _env_int
from src.system_core import CameraConfig, FrameRecord, MetricsDBWriter, PTZController, User, db
from src.video_processor import LiveStreamDeps, LiveVideoProcessor, RTSPLatestFrameReader
from src.services.camera_state_service import (
    init_camera_state_service,
    guardar_config_camara,
    leer_config_camara,
    get_configured_camera_type,
    is_camera_configured_ptz,
)
from src.services.yolo_model_service import load_yolo_model
from src.services.detection_event_service import (
    DetectionEventWriter,
    _ensure_detection_events_schema,
    _parse_iso_ts_to_epoch,
)
from src.services.inspection_patrol_service import _InspectionPatrolWorker
from src.services.ptz_state_service import PTZStateService
from src.services.ptz_worker_service import PTZCommandWorker
from src.services.tracking_worker_service import TrackingPTZWorker
from src.services.media_service import safe_join as _safe_join, safe_rel_path as _safe_rel_path
from src.services.model_params_service import ModelParamsService
from src.services.session_security_service import SessionSecurityService
from src.services.camera_config_service import CameraConfigService
from src.services.ptz_capability_service import PTZCapabilityService
from src.routes.analysis import analysis_bp, init_analysis_routes
from src.routes.events import events_bp, init_events_routes
from src.routes.dataset import dataset_bp, init_dataset_routes
from src.routes.admin_camera import admin_camera_bp, init_admin_camera_routes
from src.routes.auth import auth_bp, init_auth_routes
from src.routes.dashboard import dashboard_bp, init_dashboard_routes
from src.routes.model_params import model_params_bp, init_model_params_routes
from src.routes.ptz_manual import ptz_manual_bp, init_ptz_manual_routes
from src.routes.automation import automation_bp, init_automation_routes
from src.routes.media import media_bp, init_media_routes

# ======================== VALIDACIÓN DE ARRANQUE ========================
if not SECURITY_CONFIG["encrypt_key"]:
    logger.critical(
        "SIRAN_ENCRYPT_KEY no configurada. "
        "Las credenciales de cámara no podrán cifrarse. "
        'Generar con: python -c "from cryptography.fernet import Fernet; '
        'print(Fernet.generate_key().decode())"'
    )

# ======================== APP / DB ========================
app = Flask(__name__)

_secret_key_file = os.path.join("instance", ".secret_key")

def _load_or_create_secret_key() -> str:
    if os.path.exists(_secret_key_file):
        with open(_secret_key_file, "r") as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    os.makedirs("instance", exist_ok=True)
    with open(_secret_key_file, "w") as f:
        f.write(key)
    logger.info("FLASK_SECRET_KEY generada y guardada en %s", _secret_key_file)
    return key

app.secret_key = os.environ.get("FLASK_SECRET_KEY") or _load_or_create_secret_key()

# Identificador volátil por arranque: invalida cookies/sesiones previas tras reinicio.
session_security_service = SessionSecurityService()
SESSION_BOOT_ID = session_security_service.boot_id

init_camera_state_service(root_path=app.root_path)

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///app.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["SESSION_PERMANENT"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = os.environ.get("SESSION_COOKIE_SAMESITE", "Strict")
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE", "").strip().lower() in {
    "1",
    "true",
    "t",
    "yes",
    "y",
    "on",
}

if FLASK_CONFIG.get("debug"):
    # En desarrollo: recargar templates y evitar caché agresiva de estáticos.
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.jinja_env.auto_reload = True
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

app.config["MAX_CONTENT_LENGTH"] = FLASK_CONFIG["max_content_length"]
app.config["UPLOAD_FOLDER"] = STORAGE_CONFIG.get("upload_folder", "uploads")
app.config["RESULTS_FOLDER"] = os.path.join("static", "results")
app.config["TOP_DETECTIONS_FOLDER"] = os.path.join("static", "top_detections")
app.config["DATASET_RECOLECCION_FOLDER"] = STORAGE_CONFIG.get("dataset_recoleccion_folder", "dataset_recoleccion")
app.config["ALLOWED_EXTENSIONS"] = STORAGE_CONFIG["allowed_extensions"]

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs(app.config["RESULTS_FOLDER"], exist_ok=True)
os.makedirs(app.config["TOP_DETECTIONS_FOLDER"], exist_ok=True)
os.makedirs(app.config["DATASET_RECOLECCION_FOLDER"], exist_ok=True)

# Evidencia eficiente (UI de alertas recientes)
EVIDENCE_DIR = str(STORAGE_CONFIG["evidence_dir"])
os.makedirs(EVIDENCE_DIR, exist_ok=True)

# Dataset para mejora continua / reentrenamiento (Admin).
DATASET_TRAINING_ROOT = os.environ.get("DATASET_TRAINING_ROOT", "dataset_entrenamiento")
DATASET_NEGATIVE_DIR = os.path.join(DATASET_TRAINING_ROOT, "train", "images")
DATASET_POSITIVE_PENDING_DIR = os.path.join(DATASET_TRAINING_ROOT, "pending", "images")
os.makedirs(DATASET_NEGATIVE_DIR, exist_ok=True)
os.makedirs(DATASET_POSITIVE_PENDING_DIR, exist_ok=True)

# Inbox "limpias" a nivel raíz para revertir reclasificaciones.
DATASET_LIMPIAS_INBOX_DIR = os.path.join(app.config["DATASET_RECOLECCION_FOLDER"], "limpias")
os.makedirs(DATASET_LIMPIAS_INBOX_DIR, exist_ok=True)

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.init_app(app)

@app.before_request
def _volatile_sessions():
    """Fuerza sesiones volátiles (no persistir al cerrar el navegador)."""
    session.permanent = False
    try:
        endpoint = (request.endpoint or "").strip()
        # Evitar loops / permitir login/logout/static.
        if endpoint in {"auth.login", "auth.logout", "static"}:
            return None
        # Expiración por inactividad (idle timeout).
        if current_user.is_authenticated:
            now = time.time()
            if session_security_service.is_idle_expired(session.get("last_seen_at"), now=now):
                try:
                    logout_user()
                except Exception:
                    pass
                try:
                    session.clear()
                except Exception:
                    pass
                flash("La sesión expiró por inactividad.", "warning")
                return redirect(url_for("auth.login"))
            session_security_service.mark_seen(session, now=now)

        if current_user.is_authenticated and session_security_service.is_session_from_old_boot(session.get("boot_id")):
            # Sesión de un arranque anterior: cerrar y forzar login.
            try:
                logout_user()
            except Exception:
                pass
            try:
                session.clear()
            except Exception:
                pass
            flash("La sesión anterior fue cerrada porque el sistema se reinició.", "warning")
            return redirect(url_for("auth.login"))
    except Exception:
        # Fail-safe: no bloquear requests si falla el check.
        return None

@login_manager.user_loader
def load_user(user_id: str):
    """Callback de Flask-Login para resolver `current_user` desde la sesión."""
    return db.session.get(User, int(user_id))

def role_required(*roles: str):
    """Restringe una ruta a uno o más roles (`admin`, `operator`)."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if current_user.role not in roles:
                if not session.get("_logout_in_progress"):
                    flash("Acceso denegado: permisos insuficientes.", "danger")
                return redirect(url_for("auth.login"))
            return fn(*args, **kwargs)

        return wrapper

    return decorator

def allowed_file(filename: str) -> bool:
    """Valida extensión del archivo subido contra `STORAGE_CONFIG['allowed_extensions']`."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]

camera_config_service = CameraConfigService(
    db=db,
    CameraConfig=CameraConfig,
    rtsp_config=RTSP_CONFIG,
    onvif_config=ONVIF_CONFIG,
)


def sync_onvif_config_from_env(cfg: CameraConfig) -> CameraConfig:
    return camera_config_service.sync_onvif_config_from_env(cfg)


def _normalized_onvif_port(port: int | None) -> int:
    return camera_config_service.normalized_onvif_port(port)


def get_or_create_camera_config() -> CameraConfig:
    return camera_config_service.get_or_create_camera_config()

def bootstrap_users() -> None:
    """Crea usuarios por defecto en primera ejecución (solo si la tabla está vacía)."""
    if User.query.count() > 0:
        return

    admin = User(username="admin", role="admin")
    admin_pw_env = (os.environ.get("DEFAULT_ADMIN_PASSWORD") or "").strip()
    admin_pw = admin_pw_env or "admin123"
    if not admin_pw_env or admin_pw == "admin123":
        logger.warning(
            "Usando password por defecto para admin. Configura DEFAULT_ADMIN_PASSWORD. "
            "password_configurada=%s password_len=%s",
            bool(admin_pw_env),
            len(admin_pw),
        )
    admin.set_password(admin_pw)
    operator = User(username="operador", role="operator")
    operator_pw_env = (os.environ.get("DEFAULT_OPERATOR_PASSWORD") or "").strip()
    operator_pw = operator_pw_env or "operador123"
    if not operator_pw_env or operator_pw == "operador123":
        logger.warning(
            "Usando password por defecto para operador. Configura DEFAULT_OPERATOR_PASSWORD. "
            "password_configurada=%s password_len=%s",
            bool(operator_pw_env),
            len(operator_pw),
        )
    operator.set_password(operator_pw)

    db.session.add(admin)
    db.session.add(operator)
    db.session.commit()

    logger.info("Usuarios creados: admin (role=admin), operador (role=operator)")

# ======================== YOLO MODEL ========================
_metrics_writer = MetricsDBWriter(
    STORAGE_CONFIG.get("db_path", "detections.db"),
    enabled=(os.environ.get("METRICS_LOGGING", "1").strip().lower() not in {"0", "false", "no", "off"}),
)

def _get_metrics_db_path_abs() -> str:
    db_path = STORAGE_CONFIG.get("db_path", "detections.db")
    db_path = str(db_path or "detections.db")
    if db_path and not os.path.isabs(db_path):
        db_path = os.path.join(app.root_path, db_path)
    return db_path


_event_writer = DetectionEventWriter(
    _get_metrics_db_path_abs(),
    enabled=(
        os.environ.get("METRICS_LOGGING", "1").strip().lower() not in {"0", "false", "no", "off"}
    ),
    gap_seconds=float(_env_float("EVENT_GAP_SECONDS", 3.0)),
)


def _metrics_enqueue_with_events(record: FrameRecord) -> None:
    _metrics_writer.enqueue(record)
    _event_writer.enqueue(record)

yolo_model = load_yolo_model(YOLO_CONFIG)

# ======================== LIVE STATE ========================
ptz_state_service = PTZStateService()
state_lock = ptz_state_service.state_lock

# ======================== MODEL PARAMS (Admin RBAC) ========================
# Parametrización operativa ajustable en procesamiento de flujo (Admin).
model_params_service = ModelParamsService(env_float=_env_float, env_int=_env_int)
model_params_lock = model_params_service.lock

# ======================== CONFIGURED HW STATE (Admin) ========================
# Fuente de verdad de negocio: lo que el Administrador dejó configurado.
# Esto NO hace ping a la cámara: sólo refleja configuración persistida / último test admin.

def _update_tracking_target(payload: dict) -> None:
    ptz_state_service.update_tracking_target(payload)


def _get_tracking_target_snapshot() -> dict:
    return ptz_state_service.get_tracking_target_snapshot()


def _tracking_target_is_recent() -> tuple[bool, float]:
    snap = _get_tracking_target_snapshot()
    now = time.time()
    ttl = float(_clamp(PTZ_CONFIG["target_ttl"], 0.5, 3.0))
    age = now - float(snap.get("updated_at") or 0.0)
    return bool(snap.get("has_target")) and (age <= ttl), float(age)

# _env_float() and _env_int() are now imported from config.py (consolidation of duplicated code)

MODEL_PARAMS = model_params_service.model_params

def get_model_params() -> dict:
    """
    Devuelve una copia de los parámetros operativos del modelo.

    Returns:
        Diccionario con llaves como `confidence_threshold`, `persistence_frames`, `iou_threshold`.
    """
    return model_params_service.get_model_params()

def update_model_params(*, confidence_threshold: float, persistence_frames: int, iou_threshold: float) -> dict:
    """
    Actualiza parámetros operativos del modelo en memoria (hot update).

    Además sincroniza `DETECTION_PERSISTENCE_FRAMES`, que se usa para mostrar el estado
    de persistencia en la UI (sin necesidad de reiniciar el servidor).

    Args:
        confidence_threshold: Umbral de confianza para YOLO.
        persistence_frames: Frames consecutivos requeridos para confirmar detección.
        iou_threshold: Umbral de IOU para YOLO.

    Returns:
        Copia actualizada de los parámetros del modelo.
    """
    global DETECTION_PERSISTENCE_FRAMES
    updated = model_params_service.update_model_params(
        confidence_threshold=confidence_threshold,
        persistence_frames=persistence_frames,
        iou_threshold=iou_threshold,
    )
    try:
        DETECTION_PERSISTENCE_FRAMES = int(updated["persistence_frames"])
    except Exception:
        # NOTE: Idealmente capturar (TypeError, ValueError) si se esperan problemas de conversión.
        pass
    return dict(updated)

# Mitigación de aves:
# Requiere que la detección "persista" por N frames consecutivos antes de marcar `detected=True`
# y antes de activar tracking PTZ automático. Esto reduce falsos positivos por aves/ruido.
try:
    DETECTION_PERSISTENCE_FRAMES = int(model_params_service.get_detection_persistence_frames())
except Exception:
    DETECTION_PERSISTENCE_FRAMES = 3

last_confirmed_detection_at: float | None = None


def set_auto_tracking_enabled(value: bool) -> None:
    ptz_state_service.set_auto_tracking_enabled(bool(value))


def get_auto_tracking_enabled() -> bool:
    return bool(ptz_state_service.get_auto_tracking_enabled())


def set_inspection_mode_enabled(value: bool) -> None:
    ptz_state_service.set_inspection_mode_enabled(bool(value))


def get_inspection_mode_enabled() -> bool:
    return bool(ptz_state_service.get_inspection_mode_enabled())

# Tracking PTZ (separado del hilo de video)
tracking_target_lock = ptz_state_service.tracking_target_lock
tracking_target_state = ptz_state_service.tracking_target_state

current_detection_state = {
    "status": "Zona despejada",
    "avg_confidence": 0.0,
    "detected": False,
    "last_update": None,
    "detection_count": 0,
    "camera_source_mode": "fixed",
}

ptz_capability_service = PTZCapabilityService(
    state_lock=state_lock,
    current_detection_state=current_detection_state,
    is_camera_configured_ptz=is_camera_configured_ptz,
    set_auto_tracking_enabled=set_auto_tracking_enabled,
    set_inspection_mode_enabled=set_inspection_mode_enabled,
    get_or_create_camera_config=get_or_create_camera_config,
    normalized_onvif_port=_normalized_onvif_port,
)


init_analysis_routes(
    app=app,
    yolo_model=yolo_model,
    VIDEO_CONFIG=VIDEO_CONFIG,
    YOLO_CONFIG=YOLO_CONFIG,
    metrics_writer=_metrics_writer,
    allowed_file=allowed_file,
    get_model_params=get_model_params,
    state_lock=state_lock,
    get_camera_source_mode=ptz_capability_service.get_camera_source_mode,
    role_required=role_required,
)
app.register_blueprint(analysis_bp)

init_events_routes(
    app_root_path=app.root_path,
    storage_config=STORAGE_CONFIG,
    evidence_dir=EVIDENCE_DIR,
    role_required=role_required,
    get_metrics_db_path_abs=_get_metrics_db_path_abs,
    ensure_detection_events_schema=_ensure_detection_events_schema,
    parse_iso_ts_to_epoch=_parse_iso_ts_to_epoch,
)
app.register_blueprint(events_bp)

init_auth_routes(
    User=User,
    FLASK_CONFIG=FLASK_CONFIG,
    SESSION_BOOT_ID=SESSION_BOOT_ID,
)
app.register_blueprint(auth_bp)

init_model_params_routes(
    role_required=role_required,
    update_model_params=update_model_params,
)
app.register_blueprint(model_params_bp)

def _clamp(v: float, lo: float, hi: float) -> float:
    """Limita un valor float al rango [lo, hi]."""
    return float(max(lo, min(hi, v)))

## Worker de patrullaje movido a `src/services/inspection_patrol_service.py`

def _set_ptz_capable(value: bool, *, error: str | None = None) -> None:
    """
    Actualiza el estado global de capacidad PTZ.

    Importante:
    - Si el hardware NO es PTZ: se deshabilita `auto_tracking_enabled` por seguridad.
    - Esto es parte del "bloqueo de rutas de movimiento" cuando la cámara es fija.
    """
    ptz_capability_service.set_ptz_capable(bool(value), error=error)

def _probe_onvif_ptz_capability() -> bool:
    """
    Autodescubre PTZ por ONVIF:
    - Si existe Capabilities.PTZ (XAddr) o el servicio PTZ responde, es PTZ.
    - Si falla cualquier paso (incl. conexión/credenciales), se asume Fija.
    """
    with app.app_context():
        ok = bool(ptz_capability_service.probe_onvif_ptz_capability())
    return bool(ok)

init_admin_camera_routes(
    role_required=role_required,
    db=db,
    get_or_create_camera_config=get_or_create_camera_config,
    guardar_config_camara=guardar_config_camara,
    normalized_onvif_port=_normalized_onvif_port,
    PTZController=PTZController,
    probe_onvif_ptz_capability=_probe_onvif_ptz_capability,
    get_model_params=get_model_params,
)
app.register_blueprint(admin_camera_bp)

ptz_worker = PTZCommandWorker(
    app=app,
    get_or_create_camera_config=get_or_create_camera_config,
    normalized_onvif_port=_normalized_onvif_port,
    PTZController=PTZController,
)
ptz_worker.start()

inspection_worker = _InspectionPatrolWorker(
    idle_s=PTZ_CONFIG["inspection_idle_s"],
    ptz_worker=ptz_worker,
    state_lock=state_lock,
    current_detection_state=current_detection_state,
    get_inspection_mode_enabled=get_inspection_mode_enabled,
    set_inspection_mode_enabled=set_inspection_mode_enabled,
    get_auto_tracking_enabled=get_auto_tracking_enabled,
    is_ptz_ready_for_automation=ptz_capability_service.is_ptz_ready_for_automation,
    tracking_target_is_recent=_tracking_target_is_recent,
    clamp=_clamp,
)
inspection_worker.start()

tracking_worker = TrackingPTZWorker(
    state_lock=state_lock,
    ptz_worker=ptz_worker,
    get_auto_tracking_enabled=get_auto_tracking_enabled,
    is_ptz_ready_for_automation=ptz_capability_service.is_ptz_ready_for_automation,
    get_tracking_target_snapshot=_get_tracking_target_snapshot,
    clamp=_clamp,
)
tracking_worker.start()
# ======================== LIVE STREAM (RTSP + MODELO DE VISION) ========================

def _get_live_rtsp_url() -> str | None:
    """Obtiene la URL RTSP efectiva (usa configuracion persistida si existe)."""
    with app.app_context():
        cfg = get_or_create_camera_config()
        url = cfg.effective_rtsp_url()
        return url or RTSP_CONFIG.get("url")

live_reader = RTSPLatestFrameReader(
    get_rtsp_url=_get_live_rtsp_url,
    video_config=VIDEO_CONFIG,
    rtsp_config=RTSP_CONFIG,
)

live_deps = LiveStreamDeps(
    video_config=VIDEO_CONFIG,
    yolo_config=YOLO_CONFIG,
    detections_folder_rel=str(EVIDENCE_DIR),
    app_root_path=str(app.root_path),
)

def _ptz_tracking_move(**kwargs):
    x = float(kwargs.get("x") or 0.0)
    y = float(kwargs.get("y") or 0.0)
    z = float(kwargs.get("zoom") or 0.0)
    # Tracking estable: duracion fija y fuente distinguible en logs.
    ptz_worker.enqueue_move(x=x, y=y, zoom=z, duration_s=0.25, source="tracking")

live_processor = LiveVideoProcessor(
    reader=live_reader,
    model=yolo_model,
    deps=live_deps,
    get_model_params=get_model_params,
    metrics_enqueue=_metrics_enqueue_with_events,
    make_frame_record=FrameRecord,
    get_camera_mode=lambda: ptz_capability_service.get_camera_source_mode(),
    is_tracking_enabled=lambda: bool(get_auto_tracking_enabled()) and bool(ptz_capability_service.is_ptz_ready_for_automation()),
    is_camera_configured_ptz=is_camera_configured_ptz,
    ptz_move=_ptz_tracking_move,
    ptz_stop=ptz_worker.enqueue_stop,
    state_lock=state_lock,
    detection_state=current_detection_state,
    ui_persistence_frames=int(DETECTION_PERSISTENCE_FRAMES),
    update_tracking_target=_update_tracking_target,
)

init_dashboard_routes(
    role_required=role_required,
    state_lock=state_lock,
    current_detection_state=current_detection_state,
    get_live_processor=lambda: live_processor,
    get_live_reader=lambda: live_reader,
    get_or_create_camera_config=get_or_create_camera_config,
    leer_config_camara=leer_config_camara,
    get_configured_camera_type=get_configured_camera_type,
    get_tracking_worker=lambda: tracking_worker,
)
app.register_blueprint(dashboard_bp)

@app.get("/__diag")
def diag():
    """Diagnóstico rápido (solo en debug y localhost)."""
    if not FLASK_CONFIG.get("debug"):
        abort(404)
    if request.remote_addr not in {"127.0.0.1", "::1"}:
        abort(403)
    return jsonify(
        {
            "app_file": __file__,
            "root_path": app.root_path,
            "template_folder": app.template_folder,
            "debug": bool(FLASK_CONFIG.get("debug")),
            "host": FLASK_CONFIG.get("host"),
            "port": FLASK_CONFIG.get("port"),
        }
    )

init_dataset_routes(
    role_required=role_required,
    safe_join=_safe_join,
    dataset_recoleccion_folder=app.config["DATASET_RECOLECCION_FOLDER"],
    dataset_training_root=DATASET_TRAINING_ROOT,
    dataset_negative_dir=DATASET_NEGATIVE_DIR,
    dataset_positive_pending_dir=DATASET_POSITIVE_PENDING_DIR,
    dataset_limpias_inbox_dir=DATASET_LIMPIAS_INBOX_DIR,
)
app.register_blueprint(dataset_bp)

init_media_routes(
    role_required=role_required,
)
app.register_blueprint(media_bp)

init_automation_routes(
    role_required=role_required,
    state_lock=state_lock,
    tracking_target_state=tracking_target_state,
    tracking_target_lock=tracking_target_lock,
    ptz_worker=ptz_worker,
    is_camera_configured_ptz=is_camera_configured_ptz,
    is_ptz_ready_for_automation=ptz_capability_service.is_ptz_ready_for_automation,
    get_auto_tracking_enabled=get_auto_tracking_enabled,
    set_auto_tracking_enabled=set_auto_tracking_enabled,
    get_inspection_mode_enabled=get_inspection_mode_enabled,
    set_inspection_mode_enabled=set_inspection_mode_enabled,
    current_detection_state=current_detection_state,
)
app.register_blueprint(automation_bp)


init_ptz_manual_routes(
    app=app,
    role_required=role_required,
    ptz_worker=ptz_worker,
    state_lock=state_lock,
    tracking_target_state=tracking_target_state,
    tracking_target_lock=tracking_target_lock,
    is_camera_configured_ptz=is_camera_configured_ptz,
    ptz_discovered_capable=ptz_capability_service.ptz_discovered_capable,
    is_ptz_ready_for_manual=ptz_capability_service.is_ptz_ready_for_manual,
    get_or_create_camera_config=get_or_create_camera_config,
    normalized_onvif_port=_normalized_onvif_port,
    clamp=_clamp,
    get_auto_tracking_enabled=get_auto_tracking_enabled,
    set_auto_tracking_enabled=set_auto_tracking_enabled,
)
app.register_blueprint(ptz_manual_bp)

@app.post("/api/inspection_test_move")
@login_required
@role_required("operator")
def api_inspection_test_move():
    """
    Movimiento de prueba (automático directo) sin pasar por el worker de inspección.
    Útil para diagnosticar si el problema está en el worker/cola o en el control ONVIF.
    """
    configured_ptz = bool(is_camera_configured_ptz())
    ptz_capable = bool(ptz_capability_service.ptz_discovered_capable())
    ready = bool(ptz_capability_service.is_ptz_ready_for_manual())
    logger.debug("PTZ ready check: manual=%s configured=%s discovered=%s", bool(ready), bool(configured_ptz), bool(ptz_capable))
    if not ready:
        return jsonify({"ok": False, "error": "PTZ manual bloqueado: la cámara no está configurada como PTZ"}), 403

    try:
        with app.app_context():
            cfg = get_or_create_camera_config()
            host = (cfg.onvif_host or "").strip()
            username = (cfg.onvif_username or "").strip()
            password = (cfg.onvif_password or "").strip()
            port = _normalized_onvif_port(cfg.onvif_port)
        if not host:
            return jsonify({"ok": False, "error": "ONVIF_HOST no configurado."}), 400
        if not username or not password:
            return jsonify({"ok": False, "error": "Credenciales ONVIF incompletas."}), 400
        ctrl = PTZController(host=host, port=int(port), username=username, password=password)
        ctrl.continuous_move(x=0.25, y=0.0, zoom=0.0, duration_s=2.0)
        return jsonify({"ok": True})
    except Exception as e:
        msg = str(e) or e.__class__.__name__
        logger.error("PTZ inspection_test error: %s", msg)
        return jsonify({"ok": False, "error": msg}), 500

# ======================== SECURITY HEADERS ========================
@app.after_request
def set_security_headers(response):
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "font-src 'self'; "
        "img-src 'self' data: blob:; "
        "connect-src 'self'"
    )
    return response

# ======================== INIT ========================
with app.app_context():
    db.create_all()
    cfg = get_or_create_camera_config()
    try:
        guardar_config_camara((cfg.camera_type or "fixed").strip().lower() == "ptz")
    except Exception as e:
        logger.warning("guardar_config_camara failed: %s", e)
    bootstrap_users()
    _probe_onvif_ptz_capability()

if __name__ == "__main__":
    logger.info("Servidor: http://localhost:%s", FLASK_CONFIG['port'])
    app.run(
        debug=FLASK_CONFIG["debug"],
        use_reloader=bool(FLASK_CONFIG.get("debug")),
        host=FLASK_CONFIG["host"],
        port=FLASK_CONFIG["port"],
        threaded=bool(FLASK_CONFIG.get("threaded", True)),
    )

def _shutdown_resources() -> None:
    try:
        live_processor.stop(timeout_s=2.0)
    except Exception:
        pass
    try:
        live_reader.stop(timeout_s=2.0)
    except Exception:
        pass
    try:
        _metrics_writer.stop(timeout_s=2.0)
    except Exception:
        pass

import atexit
atexit.register(_shutdown_resources)
