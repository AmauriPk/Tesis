from __future__ import annotations
"""
RPAS Micro - Prototipo de detección de drones (tesis).

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
import os
import sqlite3
import threading
import time
from datetime import datetime
from functools import wraps

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    send_file,
    redirect,
    request,
    session,
    url_for,
)
from flask_login import (
    LoginManager,
    current_user,
    login_required,
)
from ultralytics import YOLO

try:
    import torch
except Exception:  # pragma: no cover
    torch = None

from config import FLASK_CONFIG, ONVIF_CONFIG, RTSP_CONFIG, STORAGE_CONFIG, VIDEO_CONFIG, YOLO_CONFIG, _env_float, _env_int
from src.system_core import CameraConfig, FrameRecord, MetricsDBWriter, PTZController, User, db
from src.video_processor import LiveStreamDeps, LiveVideoProcessor, RTSPLatestFrameReader
from src.system_core import select_priority_detection
from src.services.camera_state_service import (
    init_camera_state_service,
    guardar_config_camara,
    leer_config_camara,
    get_configured_camera_type,
    is_camera_configured_ptz,
)
from src.services.detection_event_service import (
    DetectionEventWriter,
    _ensure_detection_events_schema,
    _parse_iso_ts_to_epoch,
)
from src.services.inspection_patrol_service import _InspectionPatrolWorker
from src.services.ptz_state_service import PTZStateService
from src.services.ptz_worker_service import PTZCommandWorker
from src.services.tracking_worker_service import TrackingPTZWorker
from src.routes.analysis import analysis_bp, init_analysis_routes
from src.routes.events import events_bp, init_events_routes
from src.routes.dataset import dataset_bp, init_dataset_routes
from src.routes.admin_camera import admin_camera_bp, init_admin_camera_routes
from src.routes.auth import auth_bp, init_auth_routes
from src.routes.dashboard import dashboard_bp, init_dashboard_routes
from src.routes.model_params import model_params_bp, init_model_params_routes
from src.routes.ptz_manual import ptz_manual_bp, init_ptz_manual_routes
from src.routes.automation import automation_bp, init_automation_routes

# ======================== APP / DB ========================
app = Flask(__name__)
_secret_env = (os.environ.get("FLASK_SECRET_KEY") or "").strip()
if not _secret_env:
    # Fallback solo para desarrollo / demo local. En entornos reales configurar FLASK_SECRET_KEY.
    print("[SECURITY][WARN] FLASK_SECRET_KEY no configurada; usando clave de desarrollo. No usar así en demo/producción.")
    _secret_env = "dev-secret-change-me"
app.secret_key = _secret_env

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
EVIDENCE_DIR = (os.environ.get("EVIDENCE_DIR") or os.path.join("static", "evidence")).strip() or os.path.join(
    "static", "evidence"
)
os.makedirs(EVIDENCE_DIR, exist_ok=True)

# Dataset para mejora continua / reentrenamiento (Admin).
DATASET_TRAINING_ROOT = os.environ.get("DATASET_TRAINING_ROOT", "dataset_entrenamiento")
DATASET_NEGATIVE_DIR = os.path.join(DATASET_TRAINING_ROOT, "train", "images")
DATASET_POSITIVE_PENDING_DIR = os.path.join(DATASET_TRAINING_ROOT, "pending", "images")
os.makedirs(DATASET_NEGATIVE_DIR, exist_ok=True)
os.makedirs(DATASET_POSITIVE_PENDING_DIR, exist_ok=True)

# Inbox "limpias" a nivel raÃ­z para revertir reclasificaciones.
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

@login_manager.user_loader
def load_user(user_id: str):
    """Callback de Flask-Login para resolver `current_user` desde la sesión."""
    return db.session.get(User, int(user_id))

def role_required(*roles: str):
    """Restringe una ruta a uno o más roles (`admin`, `operator`)."""

    def decorator(fn):
        """Decorador real aplicado sobre la función de ruta."""

        @wraps(fn)
        def wrapper(*args, **kwargs):
            """Wrapper que verifica autenticación y rol antes de ejecutar la ruta."""
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if current_user.role not in roles:
                flash("Acceso denegado: permisos insuficientes.", "danger")
                return redirect(url_for("index"))
            return fn(*args, **kwargs)

        return wrapper

    return decorator

def allowed_file(filename: str) -> bool:
    """Valida extensión del archivo subido contra `STORAGE_CONFIG['allowed_extensions']`."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]

def sync_onvif_config_from_env(cfg: CameraConfig) -> CameraConfig:
    """
    Completa configuraciÃ³n ONVIF desde variables de entorno si estÃ¡ vacÃ­a.

    Regla: no sobreescribe valores ya persistidos en DB.
    """
    changed = False

    host = (ONVIF_CONFIG.get("host") or "").strip()
    username = (ONVIF_CONFIG.get("username") or "").strip()
    password = (ONVIF_CONFIG.get("password") or "").strip()

    try:
        port_env = int(ONVIF_CONFIG.get("port") or 80)
    except Exception:
        port_env = 80

    if not (cfg.onvif_host or "").strip() and host:
        cfg.onvif_host = host
        changed = True
    if not (cfg.onvif_username or "").strip() and username:
        cfg.onvif_username = username
        changed = True
    if not (cfg.onvif_password or "").strip() and password:
        cfg.onvif_password = password
        changed = True
    if not cfg.onvif_port:
        cfg.onvif_port = int(port_env or 80)
        changed = True

    if changed:
        db.session.commit()
    return cfg

def _normalized_onvif_port(port: int | None) -> int:
    """Normaliza el puerto ONVIF, evitando el puerto RTSP (554)."""
    try:
        p = int(port or 80)
    except Exception:
        p = 80
    if p == 554:
        return 80
    return p

def get_or_create_camera_config() -> CameraConfig:
    """Obtiene o inicializa el registro singleton con configuración RTSP/ONVIF."""
    cfg = CameraConfig.query.order_by(CameraConfig.id.asc()).first()
    if cfg:
        return sync_onvif_config_from_env(cfg)

    cfg = CameraConfig(
        camera_type="fixed",
        rtsp_url=RTSP_CONFIG.get("url"),
        rtsp_username=RTSP_CONFIG.get("username"),
        rtsp_password=RTSP_CONFIG.get("password"),
        onvif_host=(ONVIF_CONFIG.get("host") or "").strip() or None,
        onvif_port=int(ONVIF_CONFIG.get("port") or 80),
        onvif_username=(ONVIF_CONFIG.get("username") or "").strip() or None,
        onvif_password=(ONVIF_CONFIG.get("password") or "").strip() or None,
    )
    db.session.add(cfg)
    db.session.commit()
    return cfg

def bootstrap_users() -> None:
    """Crea usuarios por defecto en primera ejecución (solo si la tabla está vacía)."""
    if User.query.count() > 0:
        return

    admin = User(username="admin", role="admin")
    admin_pw_env = (os.environ.get("DEFAULT_ADMIN_PASSWORD") or "").strip()
    admin_pw = admin_pw_env or "admin123"
    if not admin_pw_env or admin_pw == "admin123":
        print(
            "[SECURITY][WARN] Usando password por defecto para admin. "
            "Configura DEFAULT_ADMIN_PASSWORD. "
            f"password_configurada={bool(admin_pw_env)} password_len={len(admin_pw)}"
        )
    admin.set_password(admin_pw)
    operator = User(username="operador", role="operator")
    operator_pw_env = (os.environ.get("DEFAULT_OPERATOR_PASSWORD") or "").strip()
    operator_pw = operator_pw_env or "operador123"
    if not operator_pw_env or operator_pw == "operador123":
        print(
            "[SECURITY][WARN] Usando password por defecto para operador. "
            "Configura DEFAULT_OPERATOR_PASSWORD. "
            f"password_configurada={bool(operator_pw_env)} password_len={len(operator_pw)}"
        )
    operator.set_password(operator_pw)

    db.session.add(admin)
    db.session.add(operator)
    db.session.commit()

    print("[BOOTSTRAP] Usuarios creados:")
    print("  - admin (role=admin)  # password en DEFAULT_ADMIN_PASSWORD")
    print("  - operador (role=operator)  # password en DEFAULT_OPERATOR_PASSWORD")

# ======================== YOLO (device dinamico) ========================
def load_yolo_model() -> YOLO | None:
    """Carga el modelo YOLO y selecciona device dinamico (GPU si existe; si no, CPU)."""
    try:
        if torch is None:
            raise RuntimeError("PyTorch no esta disponible.")
        device = "cuda:0" if bool(getattr(torch, "cuda", None)) and torch.cuda.is_available() else "cpu"
        model_path = str(YOLO_CONFIG.get("model_path") or "").strip() or "yolo26s.pt"
        if not os.path.exists(model_path):
            print(f"[WARN] No existe YOLO_MODEL_PATH='{model_path}'. Usando fallback 'yolo26s.pt'.")
            model_path = "yolo26s.pt"
        model = YOLO(model_path)
        model.to(device)
        print(f"[SUCCESS] Modelo YOLO cargado en device={device}.")
        return model
    except Exception as e:
        print(f"[ERROR] No se pudo cargar YOLO: {e}")
        return None

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

yolo_model = load_yolo_model()

# ======================== LIVE STATE ========================
ptz_state_service = PTZStateService()
state_lock = ptz_state_service.state_lock

camera_source_mode = "fixed"  # fixed | ptz (autodescubrimiento ONVIF)

# ======================== MODEL PARAMS (Admin RBAC) ========================
# ParametrizaciÃ³n operativa ajustable en procesamiento de flujo (Admin).
model_params_lock = threading.Lock()

# ======================== CONFIGURED HW STATE (Admin) ========================
# Fuente de verdad de negocio: lo que el Administrador dejÃ³ configurado.
# Esto NO hace ping a la cÃ¡mara: sÃ³lo refleja configuraciÃ³n persistida / Ãºltimo test admin.

def _update_tracking_target(payload: dict) -> None:
    ptz_state_service.update_tracking_target(payload)


def _get_tracking_target_snapshot() -> dict:
    return ptz_state_service.get_tracking_target_snapshot()


def _tracking_target_is_recent() -> tuple[bool, float]:
    snap = _get_tracking_target_snapshot()
    now = time.time()
    try:
        ttl = float(os.environ.get("PTZ_TRACKING_TARGET_TTL", "1.5"))
    except Exception:
        ttl = 1.5
    ttl = float(_clamp(ttl, 0.5, 3.0))
    age = now - float(snap.get("updated_at") or 0.0)
    return bool(snap.get("has_target")) and (age <= ttl), float(age)

# _env_float() and _env_int() are now imported from config.py (consolidation of duplicated code)

MODEL_PARAMS = {
    "confidence_threshold": float(_env_float("CONFIDENCE_THRESHOLD", 0.60)),
    "persistence_frames": int(max(1, _env_int("PERSISTENCE_FRAMES", 3))),
    "iou_threshold": float(_env_float("IOU_THRESHOLD", 0.45)),
}

def get_model_params() -> dict:
    """
    Devuelve una copia de los parÃ¡metros operativos del modelo.

    Returns:
        Diccionario con llaves como `confidence_threshold`, `persistence_frames`, `iou_threshold`.
    """
    with model_params_lock:
        return dict(MODEL_PARAMS)

def update_model_params(*, confidence_threshold: float, persistence_frames: int, iou_threshold: float) -> dict:
    """
    Actualiza parÃ¡metros operativos del modelo en memoria (hot update).

    AdemÃ¡s sincroniza `DETECTION_PERSISTENCE_FRAMES`, que se usa para mostrar el estado
    de persistencia en la UI (sin necesidad de reiniciar el servidor).

    Args:
        confidence_threshold: Umbral de confianza para YOLO.
        persistence_frames: Frames consecutivos requeridos para confirmar detecciÃ³n.
        iou_threshold: Umbral de IOU para YOLO.

    Returns:
        Copia actualizada de los parÃ¡metros del modelo.
    """
    global DETECTION_PERSISTENCE_FRAMES
    with model_params_lock:
        MODEL_PARAMS["confidence_threshold"] = float(confidence_threshold)
        MODEL_PARAMS["persistence_frames"] = int(max(1, int(persistence_frames)))
        MODEL_PARAMS["iou_threshold"] = float(iou_threshold)
        try:
            DETECTION_PERSISTENCE_FRAMES = int(MODEL_PARAMS["persistence_frames"])
        except Exception:
            # NOTE: Idealmente capturar (TypeError, ValueError) si se esperan problemas de conversiÃ³n.
            pass
        return dict(MODEL_PARAMS)

# Mitigación de aves:
# Requiere que la detección "persista" por N frames consecutivos antes de marcar `detected=True`
# y antes de activar tracking PTZ automático. Esto reduce falsos positivos por aves/ruido.
try:
    raw_dpf = os.environ.get("DETECTION_PERSISTENCE_FRAMES", "3").strip()
    DETECTION_PERSISTENCE_FRAMES = max(1, int(raw_dpf))
except (ValueError, TypeError) as e:
    print(f"[WARN] DETECTION_PERSISTENCE_FRAMES='{raw_dpf}' invalid: {e}, using default=3")
    DETECTION_PERSISTENCE_FRAMES = 3

# Autodescubrimiento de hardware (NO confiar en selector manual).
is_ptz_capable = False
last_confirmed_detection_at: float | None = None
_onvif_last_probe_at: float | None = None
_onvif_last_probe_error: str | None = None
_last_ptz_ready_automation: bool | None = None
_last_ptz_ready_manual: bool | None = None


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
    "camera_source_mode": camera_source_mode,
}

def _get_camera_source_mode() -> str:
    return camera_source_mode


init_analysis_routes(
    app=app,
    yolo_model=yolo_model,
    VIDEO_CONFIG=VIDEO_CONFIG,
    YOLO_CONFIG=YOLO_CONFIG,
    metrics_writer=_metrics_writer,
    allowed_file=allowed_file,
    get_model_params=get_model_params,
    state_lock=state_lock,
    get_camera_source_mode=_get_camera_source_mode,
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
)
app.register_blueprint(auth_bp)

init_model_params_routes(
    role_required=role_required,
    update_model_params=update_model_params,
)
app.register_blueprint(model_params_bp)

def _bbox_offset_norm(frame_w: int, frame_h: int, bbox_xyxy) -> tuple[float, float]:
    """
    Calcula el error normalizado del centro del bbox respecto al centro del frame.

    Returns:
        (dx, dy): valores normalizados en rango aproximado [-1, 1].
            - dx > 0: bbox a la derecha
            - dy > 0: bbox abajo (convención de imagen)
    """
    try:
        x1, y1, x2, y2 = bbox_xyxy
    except Exception:
        return 0.0, 0.0
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    center_x = frame_w / 2.0
    center_y = frame_h / 2.0

    dx = (cx - center_x) / max(1.0, (frame_w / 2.0))  # -1..1
    dy = (cy - center_y) / max(1.0, (frame_h / 2.0))  # -1..1 (positivo hacia abajo)
    return float(dx), float(dy)

def _ptz_centering_vector(
    frame_w: int,
    frame_h: int,
    bbox_xyxy,
    *,
    tolerance_frac: float = 0.20,
    max_speed: float = 0.60,
) -> tuple[float, float]:
    """
    Calcula velocidades (pan, tilt) para centrar un bounding box (bbox) en el frame.

    Regla:
    - Zona Central (tolerancia): si el centro del bbox cae dentro de una caja
      central de tamaÃ±o `tolerance_frac` del frame, la velocidad es 0 (anti-jitter).
    - Fuera: velocidad proporcional al error, escalada suavemente hasta `max_speed`.

    Convenciones:
    - `pan > 0` => mover a la derecha.
    - En imagen `y` crece hacia abajo; en ONVIF, `tilt > 0` suele representar arriba,
      por eso se invierte el signo del eje Y.

    Args:
        frame_w: Ancho del frame en pixeles.
        frame_h: Alto del frame en pixeles.
        bbox_xyxy: Bounding box en formato `(x1, y1, x2, y2)` en pixeles.
        tolerance_frac: Fraccion del frame (0..1) usada como tolerancia central.
        max_speed: Velocidad maxima absoluta por eje.

    Returns:
        Tupla `(pan, tilt)` con valores en `[-max_speed, max_speed]`.
    """
    fw = max(1, int(frame_w))
    fh = max(1, int(frame_h))
    try:
        x1, y1, x2, y2 = bbox_xyxy
    except Exception:
        return 0.0, 0.0
    cx = (float(x1) + float(x2)) / 2.0
    cy = (float(y1) + float(y2)) / 2.0
    fx = float(fw) / 2.0
    fy = float(fh) / 2.0

    err_x_px = float(cx - fx)
    err_y_px = float(cy - fy)

    # Normaliza error a [-1..1] (normalizado)
    err_x = err_x_px / max(1.0, float(fw) / 2.0)
    err_y = err_y_px / max(1.0, float(fh) / 2.0)

    # Zona central: tolerance_frac es el tamaÃ±o de la caja respecto al frame.
    tol = _clamp(float(tolerance_frac), 0.01, 0.90)
    tol_half_x = (tol / 2.0)
    tol_half_y = (tol / 2.0)

    # Control proporcional progresivo por eje:
    # - `deadzone` vive en el mismo espacio normalizado [-1..1].
    # - La velocidad crece progresivamente al alejarse del centro.
    pan = _p_control_speed(err_x, deadzone=tol_half_x, max_speed=float(max_speed), k=1.0)

    # Inversion del eje Y: en imagen err_y>0 es "abajo", pero en ONVIF tilt>0 suele ser "arriba".
    tilt = -1.0 * _p_control_speed(err_y, deadzone=tol_half_y, max_speed=float(max_speed), k=1.0)
    return float(pan), float(tilt)

def _clamp(v: float, lo: float, hi: float) -> float:
    """Limita un valor float al rango [lo, hi]."""
    return float(max(lo, min(hi, v)))

def _p_control_speed(error: float, *, deadzone: float, max_speed: float, k: float = 1.0) -> float:
    """
    Control proporcional (P) con zona muerta:
    - Dentro de `deadzone` => 0 (evita jitter).
    - Fuera => velocidad proporcional a la distancia, suavizando hacia 0 al acercarse al centro.

    Args:
        error: Error normalizado del eje (tipicamente en [-1..1]).
        deadzone: Umbral (0..1) en el que se considera centrado y retorna 0.
        max_speed: Velocidad maxima absoluta a entregar.
        k: Ganancia proporcional.

    Returns:
        Velocidad con signo en el rango [-max_speed, max_speed].
    """
    e = float(error)
    a = abs(e)
    if a <= deadzone:
        return 0.0
    # Normaliza distancia fuera de la zona muerta a [0..1].
    # - Cuando |error| == deadzone => scaled == 0 (velocidad 0)
    # - Cuando |error| == 1 => scaled == 1 (velocidad max)
    scaled = (a - deadzone) / max(1e-6, (1.0 - deadzone))
    v = _clamp(float(k) * float(max_speed) * scaled, 0.0, float(max_speed))
    return v if e > 0 else -v

## Worker de patrullaje movido a `src/services/inspection_patrol_service.py`
def _select_priority_detection(detection_list: list[dict]) -> dict | None:
    """
    Regla de priorización (Enjambre):
    Si hay múltiples detecciones, el tracking PTZ debe centrarse en el bbox MÁS GRANDE.
    """
    if not detection_list:
        return None
    # Regla pura (sin efectos secundarios) para poder testearla fuera de Flask.
    return select_priority_detection(detection_list)

def _set_ptz_capable(value: bool, *, error: str | None = None) -> None:
    """
    Actualiza el estado global de capacidad PTZ.

    Importante:
    - Si el hardware NO es PTZ: se deshabilita `auto_tracking_enabled` por seguridad.
    - Esto es parte del "bloqueo de rutas de movimiento" cuando la cámara es fija.
    """
    global is_ptz_capable, camera_source_mode, _onvif_last_probe_error
    with state_lock:
        is_ptz_capable = bool(value)
        _onvif_last_probe_error = error
        configured_ptz = bool(is_camera_configured_ptz())
        if (not is_ptz_capable) and (not configured_ptz):
            set_auto_tracking_enabled(False)
            set_inspection_mode_enabled(False)
        camera_source_mode = "ptz" if (is_ptz_capable or configured_ptz) else "fixed"
        current_detection_state["camera_source_mode"] = camera_source_mode

def _probe_onvif_ptz_capability() -> bool:
    """
    Autodescubre PTZ por ONVIF:
    - Si existe Capabilities.PTZ (XAddr) o el servicio PTZ responde, es PTZ.
    - Si falla cualquier paso (incl. conexión/credenciales), se asume Fija.
    """
    global _onvif_last_probe_at
    with app.app_context():
        cfg = get_or_create_camera_config()
        host = (cfg.onvif_host or "").strip()
        # Importante (robustez):
        # ONVIF y RTSP suelen usar puertos distintos.
        # - RTSP típicamente: 554
        # - ONVIF típicamente: 80 / 8000 / 8080 (según fabricante)
        # Evitamos asumir que el puerto ONVIF es el mismo que el puerto RTSP.
        try:
            raw_onvif_port = int(cfg.onvif_port or 80)
        except Exception:
            raw_onvif_port = 80
        if raw_onvif_port == 554:
            print("[ONVIF][WARN] onvif_port=554 parece RTSP; usando 80 para ONVIF.")
        configured_onvif_port = _normalized_onvif_port(raw_onvif_port)
        username = (cfg.onvif_username or "").strip()
        password = (cfg.onvif_password or "").strip()

    _onvif_last_probe_at = time.time()

    if not host:
        _set_ptz_capable(False, error="ONVIF host no configurado.")
        return False
    if not username or not password:
        _set_ptz_capable(False, error="Credenciales ONVIF incompletas.")
        return False

    def _ports_to_try(port: int) -> list[int]:
        """
        Genera una lista de puertos ONVIF a intentar.

        Heuristica:
        - Si el usuario configuro 554 (RTSP) como puerto ONVIF por error, se prueban primero
          puertos ONVIF comunes antes de 554.

        Args:
            port: Puerto configurado por el usuario.

        Returns:
            Lista de puertos a probar en orden.
        """
        common = [80, 8000, 8080]
        if port == 554:
            print("[ONVIF][WARN] ONVIF_PORT=554 parece RTSP; se ignorará y se probarán puertos ONVIF comunes.")
            return common
        ports: list[int] = [port]
        for p in common:
            if p not in ports:
                ports.append(p)
        return ports

    last_error: str | None = None
    for port in _ports_to_try(configured_onvif_port):
        try:
            from onvif import ONVIFCamera  # type: ignore

            cam = ONVIFCamera(host, int(port), username, password)

            # Opción A: Capabilities
            try:
                dev = cam.create_devicemgmt_service()
                caps = dev.GetCapabilities({"Category": "All"})
                ptz_caps = getattr(caps, "PTZ", None)
                xaddr = getattr(ptz_caps, "XAddr", None) if ptz_caps is not None else None
                if xaddr:
                    _set_ptz_capable(True, error=None)
                    return True
            except Exception:
                pass

            # Opción B: crear PTZ service y pedir capacidades
            try:
                ptz = cam.create_ptz_service()
                _ = ptz.GetServiceCapabilities()
                _set_ptz_capable(True, error=None)
                return True
            except Exception as e:
                last_error = str(e)
        except Exception as e:
            last_error = str(e)

    _set_ptz_capable(False, error=last_error or "ONVIF/PTZ no disponible.")
    return False

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

# ======================== PTZ READYNESS HELPERS ========================
def _require_ptz_capable() -> None:
    """Bloquea rutas PTZ cuando el Auto-Discovery determina cámara fija."""
    with state_lock:
        ok = bool(is_ptz_capable)
    if not ok:
        abort(403)


def _ptz_discovered_capable() -> bool:
    with state_lock:
        return bool(is_ptz_capable)


def _should_log_ptz_ready() -> bool:
    v = (os.environ.get("DEBUG_PTZ_READY") or "").strip().lower()
    return v in {"1", "true", "t", "yes", "y", "on"}


def _log_ptz_ready(*, kind: str, ready: bool, configured: bool, discovered: bool) -> None:
    global _last_ptz_ready_automation, _last_ptz_ready_manual
    if _should_log_ptz_ready():
        print("[PTZ_READY]", f"{kind}={bool(ready)} configured={bool(configured)} discovered={bool(discovered)}")
        return
    if str(kind) == "automation":
        if _last_ptz_ready_automation is None or bool(_last_ptz_ready_automation) != bool(ready):
            _last_ptz_ready_automation = bool(ready)
            print("[PTZ_READY]", f"automation={bool(ready)} configured={bool(configured)} discovered={bool(discovered)}")
        return
    if str(kind) == "manual":
        if _last_ptz_ready_manual is None or bool(_last_ptz_ready_manual) != bool(ready):
            _last_ptz_ready_manual = bool(ready)
            print("[PTZ_READY]", f"manual={bool(ready)} configured={bool(configured)} discovered={bool(discovered)}")
        return


def is_ptz_ready_for_manual() -> bool:
    configured_ptz = bool(is_camera_configured_ptz())
    discovered = bool(_ptz_discovered_capable())
    ready = bool(configured_ptz or discovered)
    _log_ptz_ready(kind="manual", ready=ready, configured=configured_ptz, discovered=discovered)
    return bool(ready)


def is_ptz_ready_for_automation() -> bool:
    configured_ptz = bool(is_camera_configured_ptz())
    discovered = bool(_ptz_discovered_capable())
    ready = bool(configured_ptz or discovered)
    _log_ptz_ready(kind="automation", ready=ready, configured=configured_ptz, discovered=discovered)
    return bool(ready)


ptz_worker = PTZCommandWorker(
    app=app,
    get_or_create_camera_config=get_or_create_camera_config,
    normalized_onvif_port=_normalized_onvif_port,
    PTZController=PTZController,
)
ptz_worker.start()

inspection_worker = _InspectionPatrolWorker(
    idle_s=10.0,
    ptz_worker=ptz_worker,
    state_lock=state_lock,
    current_detection_state=current_detection_state,
    get_inspection_mode_enabled=get_inspection_mode_enabled,
    set_inspection_mode_enabled=set_inspection_mode_enabled,
    get_auto_tracking_enabled=get_auto_tracking_enabled,
    is_ptz_ready_for_automation=is_ptz_ready_for_automation,
    tracking_target_is_recent=_tracking_target_is_recent,
    clamp=_clamp,
)
inspection_worker.start()

tracking_worker = TrackingPTZWorker(
    state_lock=state_lock,
    ptz_worker=ptz_worker,
    get_auto_tracking_enabled=get_auto_tracking_enabled,
    is_ptz_ready_for_automation=is_ptz_ready_for_automation,
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
    get_camera_mode=lambda: str(camera_source_mode),
    is_tracking_enabled=lambda: bool(get_auto_tracking_enabled()) and bool(is_ptz_ready_for_automation()),
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

# ======================== UI ========================
def _safe_rel_path(rel_path: str) -> str:
    """
    Normaliza un path relativo y bloquea traversal basico.

    Args:
        rel_path: Path relativo recibido desde request.

    Returns:
        Path relativo normalizado (separador `/` y sin prefijo `/`).

    Raises:
        ValueError: Si el path intenta traversal (contiene `..`).
    """
    rel = (rel_path or "").replace("\\", "/").lstrip("/")
    # Bloquea traversal sencillo.
    if ".." in rel.split("/"):
        raise ValueError("invalid_path")
    return rel


def cleanup_old_evidence(*, dry_run: bool = True) -> dict:
    """
    Limpieza segura de evidencias para no saturar disco.

    - No se ejecuta automáticamente.
    - Por defecto `dry_run=True` (solo reporta).
    """
    evidence_dir = (os.environ.get("EVIDENCE_DIR") or EVIDENCE_DIR).strip() or EVIDENCE_DIR
    max_files = int(_env_int("EVIDENCE_MAX_FILES", 500))
    max_age_days = int(_env_int("EVIDENCE_MAX_AGE_DAYS", 30))
    max_files = max(50, min(5000, int(max_files)))
    max_age_days = max(1, min(365, int(max_age_days)))

    abs_dir = evidence_dir
    if not os.path.isabs(abs_dir):
        abs_dir = os.path.join(app.root_path, evidence_dir)
    abs_dir = os.path.abspath(abs_dir)

    kept_refs: set[str] = set()
    db_path = _get_metrics_db_path_abs()
    try:
        if os.path.exists(db_path):
            con = sqlite3.connect(db_path, timeout=10, check_same_thread=False)
            con.row_factory = sqlite3.Row
            try:
                _ensure_detection_events_schema(con)
                cur = con.cursor()
                cur.execute(
                    """
                    SELECT best_evidence_path
                    FROM detection_events
                    ORDER BY id DESC
                    LIMIT 200
                    """
                )
                for r in cur.fetchall() or []:
                    p = (r["best_evidence_path"] or "").replace("\\", "/").lstrip("/")
                    if p:
                        kept_refs.add(p)
            finally:
                try:
                    con.close()
                except Exception:
                    pass
    except Exception:
        pass

    try:
        if not os.path.isdir(abs_dir):
            return {"ok": True, "evidence_dir": abs_dir, "files_deleted": 0, "dry_run": dry_run, "reason": "missing_dir"}

        now = time.time()
        max_age_s = float(max_age_days) * 86400.0
        files = []
        for name in os.listdir(abs_dir):
            if not name.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            abs_path = os.path.join(abs_dir, name)
            try:
                st = os.stat(abs_path)
            except Exception:
                continue
            rel_path = os.path.relpath(abs_path, app.root_path).replace("\\", "/")
            files.append({"abs": abs_path, "rel": rel_path, "mtime": float(st.st_mtime)})

        to_delete = []
        for f in files:
            age_s = now - float(f["mtime"])
            if age_s > max_age_s and f["rel"].replace("\\", "/") not in kept_refs:
                to_delete.append(f)

        files_sorted = sorted(files, key=lambda x: float(x["mtime"]))
        if len(files_sorted) - len(to_delete) > max_files:
            for f in files_sorted:
                if len(files_sorted) - len(to_delete) <= max_files:
                    break
                if f["rel"].replace("\\", "/") in kept_refs:
                    continue
                if f not in to_delete:
                    to_delete.append(f)

        deleted = 0
        for f in to_delete:
            if dry_run:
                continue
            try:
                os.remove(f["abs"])
                deleted += 1
            except Exception:
                continue

        return {
            "ok": True,
            "evidence_dir": abs_dir,
            "dry_run": bool(dry_run),
            "files_total": len(files),
            "files_marked": len(to_delete),
            "files_deleted": deleted,
            "kept_refs": len(kept_refs),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

def _safe_join(base_dir: str, rel_path: str) -> str:
    """
    Hace join seguro `base_dir` + `rel_path` bloqueando path traversal.

    Args:
        base_dir: Directorio base permitido.
        rel_path: Path relativo proporcionado por el usuario.

    Returns:
        Ruta absoluta dentro de `base_dir`.

    Raises:
        ValueError: Si el path resultante escapa de `base_dir`.
    """
    rel = _safe_rel_path(rel_path)
    base = os.path.abspath(base_dir)
    full = os.path.abspath(os.path.join(base, rel))
    if not (full == base or full.startswith(base + os.sep)):
        raise ValueError("invalid_path")
    return full

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

@app.get("/media/<path:rel_path>")
@login_required
@role_required("operator", "admin")
def media(rel_path: str):
    """
    Sirve evidencias/frames de manera segura.
    Permite solo archivos dentro de `app.root_path` (bloquea traversal).
    """
    try:
        rel = _safe_rel_path(rel_path)
        full = _safe_join(os.path.abspath(app.root_path), rel)
    except Exception:
        abort(400)
    if not os.path.exists(full) or not os.path.isfile(full):
        abort(404)
    return send_file(full)

# ======================== STREAM + STATUS ========================
@app.get("/api/get_camera_status")
@login_required
def api_get_camera_status():
    """
    Devuelve el tipo de camara configurado (PTZ vs fixed) segun el archivo persistido.

    Returns:
        JSON con `camera_type` y `configured_is_ptz`.
    """
    is_ptz = bool(leer_config_camara())
    return jsonify({"status": "ok", "camera_type": ("ptz" if is_ptz else "fixed"), "configured_is_ptz": is_ptz}), 200

init_automation_routes(
    role_required=role_required,
    state_lock=state_lock,
    tracking_target_state=tracking_target_state,
    tracking_target_lock=tracking_target_lock,
    ptz_worker=ptz_worker,
    is_camera_configured_ptz=is_camera_configured_ptz,
    is_ptz_ready_for_automation=is_ptz_ready_for_automation,
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
    ptz_discovered_capable=_ptz_discovered_capable,
    is_ptz_ready_for_manual=is_ptz_ready_for_manual,
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
    ptz_capable = bool(_ptz_discovered_capable())
    ready = bool(is_ptz_ready_for_manual())
    print("[PTZ_READY]", f"manual={bool(ready)} configured={bool(configured_ptz)} discovered={bool(ptz_capable)}")
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
        print(f"[PTZ_WORKER][ERROR] source=inspection_test error={msg}")
        return jsonify({"ok": False, "error": msg}), 500

# ======================== INIT ========================
with app.app_context():
    db.create_all()
    cfg = get_or_create_camera_config()
    try:
        guardar_config_camara((cfg.camera_type or "fixed").strip().lower() == "ptz")
    except Exception as e:
        print(f"[INIT][WARN] guardar_config_camara failed: {e}")
    bootstrap_users()
    _probe_onvif_ptz_capability()

if __name__ == "__main__":
    print(f"[INFO] Servidor: http://localhost:{FLASK_CONFIG['port']}")
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
