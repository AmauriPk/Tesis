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

import base64
import json
import os
import queue
import secrets
import shutil
import sqlite3
import subprocess
import threading
import time
from datetime import datetime
from functools import wraps
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

import cv2
import numpy as np
from flask import (
    Flask,
    Response,
    abort,
    flash,
    jsonify,
    send_file,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from ultralytics import YOLO
from werkzeug.utils import secure_filename

try:
    import torch
except Exception:  # pragma: no cover
    torch = None

try:
    import ffmpeg  # type: ignore
except Exception:  # pragma: no cover
    ffmpeg = None

from config import FLASK_CONFIG, RTSP_CONFIG, STORAGE_CONFIG, VIDEO_CONFIG, YOLO_CONFIG, _env_float, _env_int
from models import CameraConfig, User, db
from ptz_controller import PTZController
from metrics_logger import FrameRecord, MetricsDBWriter

# ======================== APP / DB ========================
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

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
login_manager.login_view = "login"
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


def get_or_create_camera_config() -> CameraConfig:
    """Obtiene o inicializa el registro singleton con configuración RTSP/ONVIF."""
    cfg = CameraConfig.query.order_by(CameraConfig.id.asc()).first()
    if cfg:
        return cfg

    cfg = CameraConfig(
        camera_type="fixed",
        rtsp_url=RTSP_CONFIG.get("url"),
        rtsp_username=RTSP_CONFIG.get("username"),
        rtsp_password=RTSP_CONFIG.get("password"),
        onvif_host=None,
        onvif_port=80,
        onvif_username=None,
        onvif_password=None,
    )
    db.session.add(cfg)
    db.session.commit()
    return cfg


def bootstrap_users() -> None:
    """Crea usuarios por defecto en primera ejecución (solo si la tabla está vacía)."""
    if User.query.count() > 0:
        return

    admin = User(username="admin", role="admin")
    admin.set_password(os.environ.get("DEFAULT_ADMIN_PASSWORD", "admin123"))
    operator = User(username="operador", role="operator")
    operator.set_password(os.environ.get("DEFAULT_OPERATOR_PASSWORD", "operador123"))

    db.session.add(admin)
    db.session.add(operator)
    db.session.commit()

    print("[BOOTSTRAP] Usuarios creados:")
    print("  - admin (role=admin)  # password en DEFAULT_ADMIN_PASSWORD")
    print("  - operador (role=operator)  # password en DEFAULT_OPERATOR_PASSWORD")


# ======================== YOLO (GPU strict) ========================
def load_yolo_model() -> YOLO | None:
    """Carga el modelo YOLO y fuerza su ejecución en GPU `cuda:0`."""
    try:
        if YOLO_CONFIG.get("device") != "cuda:0":
            raise RuntimeError("YOLO_CONFIG['device'] debe ser 'cuda:0' para ejecutar estrictamente en GPU.")
        if torch is None:
            raise RuntimeError("PyTorch no está disponible.")
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA no está disponible. Este prototipo requiere GPU (cuda:0).")

        model_path = str(YOLO_CONFIG.get("model_path") or "").strip() or "yolo26s.pt"
        if not os.path.exists(model_path):
            print(f"[WARN] No existe YOLO_MODEL_PATH='{model_path}'. Usando fallback 'yolo26s.pt'.")
            model_path = "yolo26s.pt"

        model = YOLO(model_path)
        model.to(YOLO_CONFIG["device"])
        print("[SUCCESS] Modelo YOLO cargado en GPU (cuda:0).")
        return model
    except Exception as e:
        print(f"[ERROR] No se pudo cargar YOLO: {e}")
        return None


_metrics_writer = MetricsDBWriter(
    STORAGE_CONFIG.get("db_path", "detections.db"),
    enabled=(os.environ.get("METRICS_LOGGING", "1").strip().lower() not in {"0", "false", "no", "off"}),
)

yolo_model = load_yolo_model()

# ======================== LIVE STATE ========================
state_lock = threading.Lock()
stream_lock = threading.Lock()

camera_source_mode = "fixed"  # fixed | ptz (autodescubrimiento ONVIF)

# ======================== MODEL PARAMS (Admin RBAC) ========================
# ParametrizaciÃ³n operativa ajustable en tiempo real (Admin).
model_params_lock = threading.Lock()

# ======================== CONFIGURED HW STATE (Admin) ========================
# Fuente de verdad de negocio: lo que el Administrador dejÃ³ configurado.
# Esto NO hace ping a la cÃ¡mara: sÃ³lo refleja configuraciÃ³n persistida / Ãºltimo test admin.


def _camera_cfg_path() -> str:
    """
    Construye la ruta absoluta del archivo de configuraciÃ³n de cÃ¡mara.

    Returns:
        Ruta absoluta a `config_camara.json` dentro del `app.root_path`.
    """
    return os.path.join(app.root_path, "config_camara.json")


def guardar_config_camara(is_ptz: bool) -> None:
    """Persiste en disco si la cámara está configurada como PTZ o Fija."""
    path = _camera_cfg_path()
    tmp = f"{path}.tmp"
    payload = {"is_ptz": bool(is_ptz)}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def leer_config_camara() -> bool:
    """Lee `config_camara.json` y retorna is_ptz. Si no existe, False."""
    path = _camera_cfg_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        value = bool(data.get("is_ptz", False))
        print(f"[CAMERA_CFG] read {path} -> is_ptz={value}")
        return value
    except FileNotFoundError:
        print(f"[CAMERA_CFG] read {path} -> MISSING (default False)")
        return False
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        print(f"[CAMERA_CFG] read {path} -> PARSE ERROR: {e} (default False)")
        # Fail-safe: ante corrupciones/parcial, asumir fija.
        return False


def get_configured_camera_type() -> str:
    """
    Obtiene el tipo de cÃ¡mara configurado por el administrador.

    La fuente de verdad es el archivo JSON persistente (`config_camara.json`).

    Returns:
        `"ptz"` si la configuraciÃ³n persistida indica PTZ; en caso contrario `"fixed"`.
    """
    return "ptz" if leer_config_camara() else "fixed"


def set_configured_camera_type(camera_type: str) -> str:
    """
    Normaliza y persiste el tipo de cÃ¡mara configurado por el administrador.

    Este setter no realiza autodescubrimiento ni test de conectividad; sÃ³lo persiste la
    decisiÃ³n de negocio para que UI/threads puedan reaccionar consistentemente.

    Args:
        camera_type: Tipo solicitado (`"fixed"` o `"ptz"`). Cualquier otro valor se
            normaliza a `"fixed"`.

    Returns:
        El tipo normalizado que se terminÃ³ persisitiendo (`"fixed"` o `"ptz"`).
    """
    ct = (camera_type or "fixed").strip().lower()
    if ct not in {"fixed", "ptz"}:
        ct = "fixed"
    # Persistir en disco (lo que realmente usan threads/UI).
    try:
        guardar_config_camara(ct == "ptz")
    except Exception:
        # Fail-safe: no tumbar la app por persistencia.
        pass
    return ct


def is_camera_configured_ptz() -> bool:
    """
    Indica si la cÃ¡mara estÃ¡ configurada como PTZ en disco.

    Returns:
        True si el administrador dejÃ³ configurado PTZ (persistido); de lo contrario False.
    """
    return bool(leer_config_camara())


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
auto_tracking_enabled = False
inspection_mode_enabled = False
last_confirmed_detection_at: float | None = None
_onvif_last_probe_at: float | None = None
_onvif_last_probe_error: str | None = None

current_detection_state = {
    "status": "Zona despejada",
    "avg_confidence": 0.0,
    "detected": False,
    "last_update": None,
    "detection_count": 0,
    "camera_source_mode": camera_source_mode,
}

latest_annotated_jpeg: bytes | None = None
latest_annotated_ts: float | None = None

job_lock = threading.Lock()
progress_by_job: dict[str, dict] = {}
result_by_job: dict[str, dict] = {}


def _bbox_offset_norm(frame_w: int, frame_h: int, bbox_xyxy) -> tuple[float, float]:
    """
    Calcula el error normalizado del centro del bbox respecto al centro del frame.

    Returns:
        (dx, dy): valores normalizados en rango aproximado [-1, 1].
            - dx > 0: bbox a la derecha
            - dy > 0: bbox abajo (convención de imagen)
    """
    x1, y1, x2, y2 = bbox_xyxy
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
    x1, y1, x2, y2 = bbox_xyxy
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


class _InspectionPatrolWorker:
    """
    Patrullaje automÃ¡tico:
    - Solo aplica si hardware PTZ (fail-safe por autodescubrimiento ONVIF).
    - Si no hay detecciÃ³n confirmada en los Ãºltimos N segundos, pan lento y continuo.
    - Si aparece amenaza (detecciÃ³n confirmada), se interrumpe y el tracking toma control.
    """

    def __init__(self, *, idle_s: float = 10.0):
        """
        Crea el worker de patrullaje.

        Args:
            idle_s: Segundos sin deteccion confirmada tras los cuales inicia el barrido PTZ.

        Returns:
            None.
        """
        self._idle_s = float(idle_s)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._patrolling = False
        self._dir = 1.0
        self._sweep_started_at: float | None = None
        try:
            self._sweep_duration_s = float(os.environ.get("PTZ_SWEEP_DURATION_S", "14.0"))
        except Exception:
            self._sweep_duration_s = 14.0
        try:
            self._sweep_speed = float(os.environ.get("PTZ_SWEEP_SPEED", "0.08"))
        except Exception:
            self._sweep_speed = 0.08

    def start(self):
        """
        Inicia el hilo de patrullaje (idempotente).

        Returns:
            None.
        """
        if not self._thread.is_alive():
            self._thread.start()

    def _run(self):
        """
        Loop del patrullaje:

        - Si hay deteccion confirmada => desactiva inspection y emite STOP PTZ.
        - Si no hay deteccion por `idle_s` => pan lento con sweep de duracion limitada.
        - Si hay tracking activo => el tracking tiene prioridad y el patrullaje se apaga.

        Returns:
            None.
        """
        global last_confirmed_detection_at, inspection_mode_enabled
        while not self._stop.is_set():
            time.sleep(0.35)
            with state_lock:
                enabled = bool(inspection_mode_enabled)
                ptz_ok = bool(is_ptz_capable)
                tracking = bool(auto_tracking_enabled)
                last_det = last_confirmed_detection_at
                detected = bool(current_detection_state.get("detected"))

            # Si hay amenaza confirmada, detener inspecciÃ³n de inmediato (sin tocar tracking).
            if detected:
                with state_lock:
                    inspection_mode_enabled = False
                ptz_worker.enqueue_stop()
                self._patrolling = False
                continue

            if not enabled or not ptz_ok or not is_camera_configured_ptz():
                if self._patrolling:
                    ptz_worker.enqueue_stop()
                    self._patrolling = False
                continue

            now = time.time()
            idle = (last_det is None) or ((now - float(last_det)) >= self._idle_s)

            # Si hay tracking activo y no estamos en idle, el tracking manda.
            if tracking and not idle:
                if self._patrolling:
                    ptz_worker.enqueue_stop()
                    self._patrolling = False
                continue

            if idle:
                # Pan muy lento y continuo (solo eje X). DuraciÃ³n moderada para suavidad.
                if self._sweep_started_at is None:
                    self._sweep_started_at = now
                elapsed = now - float(self._sweep_started_at)
                if elapsed >= float(self._sweep_duration_s):
                    ptz_worker.enqueue_stop()
                    self._patrolling = False
                    self._dir = -1.0 * float(self._dir)
                    self._sweep_started_at = now
                    continue

                x_speed = _clamp(float(self._sweep_speed) * float(self._dir), -0.25, 0.25)
                ptz_worker.enqueue_move(x=x_speed, y=0.0, zoom=0.0, duration_s=0.45)
                self._patrolling = True
            else:
                if self._patrolling:
                    ptz_worker.enqueue_stop()
                    self._patrolling = False
                self._sweep_started_at = None


inspection_worker = _InspectionPatrolWorker(idle_s=10.0)
inspection_worker.start()


def _select_priority_detection(detection_list: list[dict]) -> dict | None:
    """
    Regla de priorización (Enjambre):
    Si hay múltiples detecciones, el tracking PTZ debe centrarse en el bbox MÁS GRANDE.
    """
    if not detection_list:
        return None
    # Regla pura (sin efectos secundarios) para poder testearla fuera de Flask.
    from backend_rules import select_priority_detection

    return select_priority_detection(detection_list)


def _set_ptz_capable(value: bool, *, error: str | None = None) -> None:
    """
    Actualiza el estado global de capacidad PTZ.

    Importante:
    - Si el hardware NO es PTZ: se deshabilita `auto_tracking_enabled` por seguridad.
    - Esto es parte del "bloqueo de rutas de movimiento" cuando la cámara es fija.
    """
    global is_ptz_capable, camera_source_mode, _onvif_last_probe_error, auto_tracking_enabled, inspection_mode_enabled
    with state_lock:
        is_ptz_capable = bool(value)
        _onvif_last_probe_error = error
        if not is_ptz_capable:
            auto_tracking_enabled = False
            inspection_mode_enabled = False
        camera_source_mode = "ptz" if is_ptz_capable else "fixed"
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
            configured_onvif_port = int(cfg.onvif_port or 80)
        except Exception:
            configured_onvif_port = 80
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
        # Heurística: si el usuario dejó 554 (RTSP) como ONVIF, probar primero puertos ONVIF comunes.
        common = [80, 8000, 8080]
        if port == 554:
            return common + [554]
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


def _ptz_vector(direction: str):
    """Convierte una dirección simple (joystick) a vector (pan, tilt, zoom)."""
    # Mapeo simple. Ajustar según el PTZ real.
    if direction == "left":
        return (-0.3, 0.0, 0.0)
    if direction == "right":
        return (0.3, 0.0, 0.0)
    if direction == "up":
        return (0.0, 0.3, 0.0)
    if direction == "down":
        return (0.0, -0.3, 0.0)
    return (0.0, 0.0, 0.0)


class PTZCommandWorker:
    """
    Ejecuta comandos PTZ en un hilo separado para evitar congelamientos.

    La UI y el thread de inferencia no deben llamar directamente a ONVIF/PTZ porque:
    - ONVIF puede bloquear por red/RTT.
    - Un exceso de comandos puede saturar el PTZ y causar drift/jitter.

    Este worker aplica:
    - Cola con drop/backpressure (maxsize).
    - Rate-limit de movimientos.
    - Reconstruccion del controlador en caso de error.
    """

    def __init__(self):
        """
        Inicializa la cola, el thread y el estado interno del worker.

        Returns:
            None.
        """
        self._q: queue.Queue[dict] = queue.Queue(maxsize=80)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._controller: PTZController | None = None
        self._last_cmd_at = 0.0
        self._last_vec = (0.0, 0.0)
        self._delta_threshold = 0.05

    def start(self):
        """
        Inicia el hilo worker (idempotente).

        Returns:
            None.
        """
        if not self._thread.is_alive():
            self._thread.start()

    def enqueue_move(self, *, x: float, y: float, zoom: float = 0.0, duration_s: float = 0.15):
        """
        Encola un movimiento continuo (pan/tilt/zoom) con duracion limitada.

        Aplica un filtro de "cambio minimo" para evitar spamear movimientos casi identicos.

        Args:
            x: Pan (izquierda/derecha) en rango aproximado [-1, 1].
            y: Tilt (arriba/abajo) en rango aproximado [-1, 1].
            zoom: Zoom en rango aproximado [-1, 1].
            duration_s: Duracion del movimiento continuous-move antes de auto-stop.

        Returns:
            None.
        """
        try:
            x_f = float(x)
            y_f = float(y)
        except Exception:
            # NOTE: Idealmente capturar (TypeError, ValueError) si se esperan tipos invalidos.
            return

        last_x, last_y = self._last_vec
        is_stop_vec = abs(x_f) <= 1e-9 and abs(y_f) <= 1e-9
        if (
            (not is_stop_vec)
            and (abs(x_f - float(last_x)) <= self._delta_threshold)
            and (abs(y_f - float(last_y)) <= self._delta_threshold)
        ):
            return
        self._last_vec = (float(x_f), float(y_f))

        try:
            self._q.put_nowait(
                {
                    "type": "move",
                    "x": float(x_f),
                    "y": float(y_f),
                    "zoom": float(zoom),
                    "duration_s": float(duration_s),
                }
            )
        except Exception:
            # NOTE: Idealmente capturar queue.Full para distinguir de otros errores.
            pass

    def enqueue_direction(self, direction: str):
        """
        Encola un movimiento direccional (arriba/abajo/izq/der) para el joystick.

        Args:
            direction: Direccion logica (`left|right|up|down`).

        Returns:
            None.
        """
        x, y, z = _ptz_vector(direction)
        self.enqueue_move(x=x, y=y, zoom=z, duration_s=0.15)

    def enqueue_stop(self):
        """
        Encola un STOP PTZ con prioridad para evitar drift.

        Esta operacion intenta limpiar la cola antes de insertar el stop, para que el
        hardware reciba el stop lo antes posible.

        Returns:
            None.
        """
        try:
            try:
                # Limpia la cola internamente. `Queue` no expone un metodo oficial para esto,
                # pero aqui es aceptable porque buscamos un stop "de emergencia".
                with self._q.mutex:  # type: ignore[attr-defined]
                    self._q.queue.clear()  # type: ignore[attr-defined]
            except Exception:
                pass
            self._last_vec = (0.0, 0.0)
            self._q.put_nowait({"type": "stop"})
        except Exception:
            # NOTE: Idealmente capturar queue.Full para distinguir de otros errores.
            pass

    def _get_controller(self) -> PTZController | None:
        """
        Construye un controlador PTZ desde la configuracion persistida.

        Returns:
            Una instancia de `PTZController` si hay credenciales/host configurados; si no, None.
        """
        # Los hilos no tienen app context por defecto.
        with app.app_context():
            cfg = get_or_create_camera_config()
            if not cfg.onvif_host or not cfg.onvif_username or not cfg.onvif_password:
                return None
            return PTZController(
                host=cfg.onvif_host,
                port=int(cfg.onvif_port or 80),
                username=cfg.onvif_username,
                password=cfg.onvif_password,
            )

    def _run(self):
        """
        Loop del worker: rate-limit y ejecucion segura de comandos ONVIF PTZ.

        Returns:
            None.
        """
        while not self._stop.is_set():
            try:
                cmd = self._q.get(timeout=0.2)
            except queue.Empty:
                continue

            cmd_type = (cmd.get("type") or "").lower()

            # Rate limit (evita saturar PTZ): solo aplica a moves.
            if cmd_type == "move":
                now = time.time()
                if now - self._last_cmd_at < 0.20:
                    continue
                self._last_cmd_at = now

            try:
                if self._controller is None:
                    self._controller = self._get_controller()
                if self._controller is None:
                    continue
                if cmd_type == "stop":
                    self._controller.stop()
                    continue
                if cmd_type == "move":
                    x = float(cmd.get("x") or 0.0)
                    y = float(cmd.get("y") or 0.0)
                    z = float(cmd.get("zoom") or 0.0)
                    duration_s = float(cmd.get("duration_s") or 0.15)
                    self._controller.continuous_move(x=x, y=y, zoom=z, duration_s=duration_s)
            except Exception as e:
                # NOTE: Seria ideal capturar excepciones de red/ONVIF concretas para telemetria.
                print(f"[PTZ][ERROR] {e}")
                self._controller = None


ptz_worker = PTZCommandWorker()
ptz_worker.start()


class _RTSPLatestFrameReader:
    """
    Lee RTSP en un hilo y conserva sólo el último frame (drop de frames si hay lag).
    """

    def __init__(self):
        """Inicializa el reader con un buffer de 'último frame' y un thread de captura."""
        self._lock = threading.Lock()
        self._frame = None
        self._ts = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._current_url = None

    def start(self):
        """Inicia el thread de lectura RTSP (idempotente)."""
        if not self._thread.is_alive():
            self._thread.start()

    def get_latest(self):
        """Devuelve el último frame disponible (frame, timestamp)."""
        with self._lock:
            return self._frame, self._ts

    def _get_rtsp_url(self) -> str | None:
        """Obtiene RTSP URL efectiva (inyecta credenciales si aplica)."""
        # Los hilos no tienen app context por defecto.
        with app.app_context():
            cfg = get_or_create_camera_config()
            url = cfg.effective_rtsp_url()
            return url or RTSP_CONFIG.get("url")

    def _run(self):
        """Loop de captura RTSP con reconexión y drop de frames (solo guarda el último)."""
        cap = None
        try:
            while not self._stop.is_set():
                desired_url = self._get_rtsp_url()
                if desired_url and desired_url != self._current_url:
                    self._current_url = desired_url
                    if cap is not None:
                        try:
                            cap.release()
                        except Exception:
                            pass
                        cap = None

                if not self._current_url:
                    time.sleep(0.5)
                    continue

                if cap is None or not cap.isOpened():
                    cap = cv2.VideoCapture(self._current_url)
                    if cap.isOpened():
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH, VIDEO_CONFIG["width"])
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, VIDEO_CONFIG["height"])
                        cap.set(cv2.CAP_PROP_FPS, VIDEO_CONFIG["fps"])
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, RTSP_CONFIG.get("buffer_size", 1))
                    else:
                        print("[RTSP] No se pudo abrir RTSP. Reintentando...")
                        time.sleep(1.0)
                        continue

                ret, frame = cap.read()
                if not ret or frame is None:
                    print(f"[RTSP][WARN] Read failed on {self._current_url}, reconnecting...")
                    try:
                        cap.release()
                    except Exception:
                        pass
                    cap = None
                    time.sleep(0.5)
                    continue

                ts = time.time()
                with self._lock:
                    self._frame = frame
                    self._ts = ts
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass


class _DetectionPersistence:
    """
    Filtro de persistencia para mitigación de aves.

    La detección se considera "confirmada" únicamente si el modelo produce detecciones
    durante `required_consecutive_frames` frames consecutivos.
    """

    def __init__(self, required_consecutive_frames: int):
        """Crea el filtro con el umbral de frames consecutivos requerido."""
        self.required_consecutive_frames = max(1, int(required_consecutive_frames))
        self._consecutive_hits = 0

    def update(self, has_detection: bool) -> tuple[bool, int]:
        """
        Actualiza el estado del filtro.

        Args:
            has_detection: True si el frame actual tiene >=1 detección.

        Returns:
            (confirmed, consecutive_hits)
        """
        if has_detection:
            self._consecutive_hits += 1
        else:
            self._consecutive_hits = 0
        confirmed = self._consecutive_hits >= self.required_consecutive_frames
        return confirmed, self._consecutive_hits

    def set_required_consecutive_frames(self, required_consecutive_frames: int) -> None:
        """Actualiza el umbral y reinicia el contador para evitar estados inconsistentes."""
        self.required_consecutive_frames = max(1, int(required_consecutive_frames))
        self._consecutive_hits = 0


class _LiveVideoProcessor:
    """
    Ejecuta inferencia YOLO sobre el stream RTSP y publica el ultimo JPEG anotado.

    Responsabilidades:
    - Consumir frames del reader (drop-frame: solo ultimo frame).
    - Ejecutar YOLO en intervalos configurables.
    - Aplicar mitigacion de aves (persistencia por N frames).
    - Guardar evidencia (snapshot) por evento confirmado.
    - Ejecutar tracking PTZ (via `PTZCommandWorker`) bajo reglas de priorizacion.
    """

    def __init__(self, reader: _RTSPLatestFrameReader):
        """
        Inicializa el pipeline live (inferencia + anotacion + publicacion de ultimo JPEG).

        Args:
            reader: Fuente de frames RTSP con buffer de ultimo frame.

        Returns:
            None.
        """
        self.reader = reader
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._stop = threading.Event()
        self._last_ts = None
        self._frame_count = 0
        self._detection_times = []
        self._persistence = _DetectionPersistence(int(get_model_params()["persistence_frames"]))
        self._evidence_saved_for_active_detection = False
        self._last_evidence_saved_at = 0.0

    def start(self):
        """
        Inicia el thread de procesamiento (idempotente).

        Returns:
            None.
        """
        if not self._thread.is_alive():
            self._thread.start()

    def _run(self):
        """
        Loop principal: toma frames, corre YOLO, aplica persistencia y tracking PTZ.

        Returns:
            None.
        """
        global latest_annotated_jpeg, latest_annotated_ts

        while not self._stop.is_set():
            frame, ts = self.reader.get_latest()
            if frame is None or ts is None:
                time.sleep(0.02)
                continue
            if ts == self._last_ts:
                time.sleep(0.005)
                continue
            self._last_ts = ts

            # Normaliza resolución. Evita trabajo si ya coincide.
            target_w = int(VIDEO_CONFIG["width"])
            target_h = int(VIDEO_CONFIG["height"])
            try:
                if frame.shape[1] != target_w or frame.shape[0] != target_h:
                    frame = cv2.resize(frame, (target_w, target_h))
            except cv2.error as e_cv:
                print(f"[VIDEO][CV2_ERROR] Frame resize failed: {e_cv}")
            except (AttributeError, TypeError) as e:
                print(f"[VIDEO][ERROR] Frame shape check failed: {e}")

            self._frame_count += 1

            detection_list = []
            inference_ms: float | None = None
            if yolo_model is not None and (self._frame_count % max(1, VIDEO_CONFIG.get("inference_interval", 1)) == 0):
                try:
                    params = get_model_params()
                    # Permite ajuste en caliente del filtro anti-aves.
                    required = int(params.get("persistence_frames", 3))
                    if required != int(self._persistence.required_consecutive_frames):
                        self._persistence.set_required_consecutive_frames(required)

                    t0 = time.time()
                    results = yolo_model(
                        frame,
                        device=YOLO_CONFIG["device"],
                        conf=float(params.get("confidence_threshold", YOLO_CONFIG["confidence"])),
                        iou=float(params.get("iou_threshold", 0.45)),
                        verbose=YOLO_CONFIG["verbose"],
                    )
                    dt = time.time() - t0
                    inference_ms = float(dt * 1000.0)
                    self._detection_times.append(dt)
                    self._detection_times = self._detection_times[-30:]
                    frame, detection_list = draw_detections(frame, results)
                except cv2.error as e_cv:
                    print(f"[YOLO][CV2_ERROR] {e_cv}")
                except RuntimeError as e_rt:
                    print(f"[YOLO][RUNTIME_ERROR] {e_rt}")
                except Exception as e:
                    print(f"[YOLO][ERROR] {e}")
                    cv2.putText(frame, "Error en inferencia", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            # ---------------- Mitigación de aves (persistencia) ----------------
            # Solo se "confirma" detección tras N frames consecutivos con detecciones.
            # Esto afecta:
            # - La bandera `detected` y estado UI.
            # - El tracking PTZ automático (no mover ante falsos positivos instantáneos).
            confirmed, consecutive_hits = self._persistence.update(bool(detection_list))

            # ---------------- Evidencia visual (snapshot por detección confirmada) ----------------
            # Guardar 1 imagen por "evento" para el Panel de Alertas (no por frame).
            if detection_list and confirmed:
                now = time.time()
                if (not self._evidence_saved_for_active_detection) and ((now - float(self._last_evidence_saved_at)) >= 1.0):
                    try:
                        os.makedirs(app.config["TOP_DETECTIONS_FOLDER"], exist_ok=True)
                        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                        fname = f"live_alert_{stamp}.jpg"
                        rel_path = os.path.join(app.config["TOP_DETECTIONS_FOLDER"], fname).replace("\\", "/")
                        abs_path = os.path.join(app.root_path, rel_path)
                        cv2.imwrite(abs_path, frame)
                        for d in detection_list:
                            if isinstance(d, dict) and not d.get("image_path"):
                                d["image_path"] = rel_path
                        self._evidence_saved_for_active_detection = True
                        self._last_evidence_saved_at = now
                    except Exception:
                        pass
            else:
                self._evidence_saved_for_active_detection = False

            # ---------------- Persistencia de métricas (SQLite) ----------------
            # - 1 registro por frame inferido (latencia real)
            # - N registros por detección (bbox)
            if inference_ms is not None:
                try:
                    h, w = frame.shape[:2]
                except Exception:
                    h, w = None, None
                try:
                    with state_lock:
                        cam_mode = str(camera_source_mode)
                except Exception:
                    cam_mode = "unknown"
                try:
                    _metrics_writer.enqueue(
                        FrameRecord(
                            timestamp_iso=datetime.fromtimestamp(float(ts)).isoformat(),
                            source="rtsp",
                            inference_ms=float(inference_ms),
                            frame_w=int(w) if w is not None else 0,
                            frame_h=int(h) if h is not None else 0,
                            detections=list(detection_list),
                            confirmed=bool(confirmed),
                            camera_mode=cam_mode,
                        )
                    )
                except Exception:
                    # Fail-safe: no frenar stream si falla logging.
                    pass

            # ---------------- Tracking automático PTZ (hilo separado) ----------------
            with state_lock:
                mode = camera_source_mode
                tracking = bool(auto_tracking_enabled)
            # Regla de priorización (Enjambre): seleccionar bbox MÁS GRANDE.
            priority = _select_priority_detection(detection_list)
            if mode == "ptz" and tracking and confirmed and priority is not None and is_camera_configured_ptz():
                h, w = frame.shape[:2]
                dx, dy = _bbox_offset_norm(w, h, priority["bbox"])  # dy>0 => bbox abajo

                # Bloque clave (tesis): tracking con control proporcional progresivo (anti-jitter).
                # - dx se usa para pan (derecha/izquierda)
                # - dy se invierte para tilt (arriba/abajo) por convención ONVIF
                # - La velocidad baja gradualmente al acercarse al centro (zona muerta).
                deadzone = 0.10
                max_speed = 0.60
                try:
                    tolerance_frac = float(os.environ.get("PTZ_CENTER_TOLERANCE_FRAC", "0.20"))
                except Exception:
                    tolerance_frac = 0.20
                x, y = _ptz_centering_vector(w, h, priority["bbox"], tolerance_frac=tolerance_frac, max_speed=max_speed)

                # Suavizado adicional para evitar vibración (filtro exponencial simple).
                if not hasattr(self, "_last_ptz_cmd"):
                    self._last_ptz_cmd = (0.0, 0.0)
                lx, ly = self._last_ptz_cmd
                alpha = 0.55
                sx = (alpha * float(x)) + ((1.0 - alpha) * float(lx))
                sy = (alpha * float(y)) + ((1.0 - alpha) * float(ly))
                self._last_ptz_cmd = (sx, sy)

                if abs(sx) > 0.001 or abs(sy) > 0.001:
                    ptz_worker.enqueue_move(
                        x=_clamp(sx, -max_speed, max_speed),
                        y=_clamp(sy, -max_speed, max_speed),
                        zoom=0.0,
                        duration_s=0.12,
                    )
                else:
                    # Evitar spamear STOP en cada frame centrado.
                    if abs(lx) > 0.02 or abs(ly) > 0.02:
                        ptz_worker.enqueue_stop()

            # Estado UI
            with state_lock:
                current_detection_state["camera_source_mode"] = camera_source_mode
                current_detection_state["last_update"] = datetime.now().isoformat()
                if detection_list and confirmed:
                    last_confirmed_detection_at = time.time()
                    avg_conf = float(np.mean([d["confidence"] for d in detection_list]))
                    current_detection_state["status"] = "Alerta: Dron detectado"
                    current_detection_state["avg_confidence"] = avg_conf
                    current_detection_state["detected"] = True
                    current_detection_state["detection_count"] = len(detection_list)
                elif detection_list and not confirmed:
                    # Persistencia en curso: mostrar actividad sin disparar alerta final.
                    avg_conf = float(np.mean([d["confidence"] for d in detection_list]))
                    current_detection_state["status"] = f"Validando detección ({consecutive_hits}/{DETECTION_PERSISTENCE_FRAMES})"
                    current_detection_state["avg_confidence"] = avg_conf
                    current_detection_state["detected"] = False
                    current_detection_state["detection_count"] = len(detection_list)
                else:
                    current_detection_state["status"] = "Zona despejada"
                    current_detection_state["avg_confidence"] = 0.0
                    current_detection_state["detected"] = False
                    current_detection_state["detection_count"] = 0

            # FPS estimado inferencia
            if self._detection_times:
                avg = float(np.mean(self._detection_times))
                fps = (1.0 / avg) if avg > 0 else 0.0
                cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, VIDEO_CONFIG["jpeg_quality"]])
            if ok:
                with stream_lock:
                    latest_annotated_jpeg = buf.tobytes()
                    latest_annotated_ts = ts


_rtsp_reader = _RTSPLatestFrameReader()
_live_processor = _LiveVideoProcessor(_rtsp_reader)
_live_threads_started = False


def _ensure_live_threads_started():
    """Arranca threads de RTSP + YOLO una sola vez (lazy-init cuando llega el primer cliente)."""
    global _live_threads_started
    if _live_threads_started:
        return
    _rtsp_reader.start()
    _live_processor.start()
    _live_threads_started = True


def draw_detections(frame, results):
    """Dibuja bounding boxes sobre el frame y normaliza a una lista simple para lógica aguas abajo."""
    detection_list = []
    for result in results:
        if result.boxes is None:
            continue
        for box in result.boxes:
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
            conf = float(box.conf[0].cpu().numpy())
            color = (0, 255, 0)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            label = f"RPAS Micro {conf:.0%}"
            label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(frame, (x1, max(0, y1 - 25)), (x1 + label_size[0], y1), color, -1)
            cv2.putText(frame, label, (x1, max(15, y1 - 7)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
            detection_list.append({"class_name": "RPAS Micro", "confidence": conf, "bbox": (x1, y1, x2, y2)})
    return frame, detection_list


def process_rtsp_stream():
    """Generador MJPEG: emite el último frame anotado disponible (sin recalcular por cliente)."""
    _ensure_live_threads_started()

    placeholder = np.zeros((VIDEO_CONFIG["height"], VIDEO_CONFIG["width"], 3), dtype=np.uint8)
    cv2.putText(placeholder, "Conectando a RTSP...", (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
    _, ph_buf = cv2.imencode(".jpg", placeholder, [cv2.IMWRITE_JPEG_QUALITY, 80])
    ph_bytes = ph_buf.tobytes()

    last_sent_ts = None
    while True:
        with stream_lock:
            jpeg = latest_annotated_jpeg
            ts = latest_annotated_ts

        if jpeg is None or ts is None:
            frame_bytes = ph_bytes
            time.sleep(0.05)
        else:
            if ts == last_sent_ts:
                time.sleep(0.01)
                continue
            last_sent_ts = ts
            frame_bytes = jpeg

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Content-Length: " + str(len(frame_bytes)).encode() + b"\r\n\r\n" + frame_bytes + b"\r\n"
        )


# ======================== AUTH ========================
@app.route("/login", methods=["GET", "POST"])
def login():
    """Login simple (Flask-Login)."""
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            session.permanent = False
            next_url = (request.form.get("next") or request.args.get("next") or "").strip()
            if next_url:
                parsed = urlparse(next_url)
                is_safe = (parsed.scheme == "") and (parsed.netloc == "")
                if is_safe and next_url not in {"/", "/?tab=live"}:
                    return redirect(next_url)
            return redirect(url_for("index", tab="live"))
        flash("Credenciales inválidas.", "danger")

    return render_template("login.html", show_bootstrap_hint=bool(FLASK_CONFIG.get("debug")))


@app.route("/logout")
@login_required
def logout():
    """Cierra sesión."""
    logout_user()
    return redirect(url_for("login"))


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
@app.route("/")
@login_required
def index():
    """Dashboard principal (manual + live). Operador-only por regla de negocio."""
    if current_user.role == "admin":
        return redirect(url_for("admin_dashboard"))
    cfg = get_or_create_camera_config()
    # Fuente de verdad: config_camara.json (evita sobrescrituras por DB / memoria volátil).
    is_ptz = bool(leer_config_camara())
    camera_type_str = "ptz" if is_ptz else "fixed"
    active_tab = (request.args.get("tab") or "").strip().lower() or "live"
    if active_tab not in {"live", "manual"}:
        active_tab = "live"
    return render_template(
        "index.html",
        is_admin=(current_user.role == "admin"),
        camera_type=camera_type_str,
        current_user=current_user,
        active_tab=active_tab,
    )


@app.get("/admin_dashboard")
@login_required
@role_required("admin")
def admin_dashboard():
    """Dashboard exclusivo para Administrador (config HW + parÃ¡metros IA)."""
    cfg = get_or_create_camera_config()
    params = get_model_params()
    return render_template("admin.html", cfg=cfg, model_params=params)


@app.route("/admin/camera", methods=["GET", "POST"])
@login_required
@role_required("admin")
def admin_camera():
    """Panel admin para editar RTSP/ONVIF (persistido en DB)."""
    cfg = get_or_create_camera_config()

    if request.method == "POST":
        cfg.camera_type = (request.form.get("camera_type") or "fixed").lower()
        try:
            guardar_config_camara((cfg.camera_type or "fixed").strip().lower() == "ptz")
        except Exception:
            pass

        cfg.rtsp_url = (request.form.get("rtsp_url") or "").strip() or None
        cfg.rtsp_username = (request.form.get("rtsp_username") or "").strip() or None
        cfg.rtsp_password = (request.form.get("rtsp_password") or "").strip() or None

        cfg.onvif_host = (request.form.get("onvif_host") or "").strip() or None
        try:
            cfg.onvif_port = int(request.form.get("onvif_port") or 80)
        except Exception:
            cfg.onvif_port = 80
        cfg.onvif_username = (request.form.get("onvif_username") or "").strip() or None
        cfg.onvif_password = (request.form.get("onvif_password") or "").strip() or None

        db.session.commit()
        # Autodescubrimiento (no confiar en camera_type).
        _probe_onvif_ptz_capability()
        flash("Configuración de cámara guardada.", "success")
        return redirect(url_for("admin_dashboard"))

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/camera/test", methods=["POST"])
@login_required
@role_required("admin")
def admin_camera_test():
    """Prueba rápida de conexión ONVIF (requiere `onvif-zeep`)."""
    cfg = get_or_create_camera_config()
    if not cfg.onvif_host or not cfg.onvif_username or not cfg.onvif_password:
        return jsonify({"ok": False, "error": "Completa host/usuario/contraseña ONVIF."}), 400
    try:
        controller = PTZController(cfg.onvif_host, int(cfg.onvif_port or 80), cfg.onvif_username, cfg.onvif_password)
        return jsonify(controller.test_connection())
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def _humanize_onvif_error(err: Exception) -> str:
    """
    Convierte errores ONVIF/Red a un mensaje legible para UI.

    Args:
        err: Excepcion capturada durante un test ONVIF.

    Returns:
        Mensaje human-friendly para mostrar al usuario.
    """
    msg = (str(err) or err.__class__.__name__).strip()
    low = msg.lower()

    if "not authorized" in low or "unauthorized" in low or "authentication" in low or "auth" in low:
        return "Error de AutenticaciÃ³n: credenciales incorrectas o permisos insuficientes."

    if "timed out" in low or "timeout" in low:
        return "Host inalcanzable (Timeout)."
    if "name or service not known" in low or "no such host" in low or "could not resolve" in low:
        return "Host invÃ¡lido: no se pudo resolver DNS."
    if "connection refused" in low:
        return "ConexiÃ³n rechazada: puerto ONVIF cerrado o incorrecto."
    if "network is unreachable" in low:
        return "Red inalcanzable: revisa conectividad y rutas."

    if "wsdl" in low:
        return "Error ONVIF/WSDL: endpoint no compatible o respuesta invÃ¡lida."

    return msg


def _detect_ptz_capability(host: str, port: int, username: str, password: str) -> bool:
    """Conecta por ONVIF y determina si expone PTZ (sin movimientos)."""
    from onvif import ONVIFCamera  # type: ignore

    cam = ONVIFCamera(host, int(port), username, password)

    try:
        dev = cam.create_devicemgmt_service()
        caps = dev.GetCapabilities({"Category": "All"})
        ptz_caps = getattr(caps, "PTZ", None)
        xaddr = getattr(ptz_caps, "XAddr", None) if ptz_caps is not None else None
        if xaddr:
            return True
    except Exception:
        pass

    try:
        ptz = cam.create_ptz_service()
        _ = ptz.GetServiceCapabilities()
        return True
    except Exception:
        return False


def _build_rtsp_url(rtsp_url: str, username: str | None, password: str | None) -> str:
    """
    Inyecta credenciales RTSP en una URL si no estan presentes.

    Args:
        rtsp_url: URL base RTSP.
        username: Usuario RTSP (opcional).
        password: Contrasena RTSP (opcional).

    Returns:
        URL RTSP reconstruida con credenciales si aplican; si no, la original.
    """
    raw = (rtsp_url or "").strip()
    if not raw:
        return ""
    try:
        u = urlparse(raw)
    except Exception:
        return raw

    if (u.scheme or "").lower() != "rtsp":
        return raw

    # Si ya trae usuario, no tocar.
    if u.username:
        return raw

    user = (username or "").strip()
    pwd = password or ""
    if not user or not pwd:
        return raw

    host = u.hostname or ""
    if not host:
        return raw

    netloc = f"{user}:{pwd}@{host}"
    if u.port:
        netloc += f":{u.port}"

    rebuilt = u._replace(netloc=netloc)
    return rebuilt.geturl()


def _grab_rtsp_snapshot_b64(rtsp_url: str) -> str:
    """
    Abre el RTSP de forma momentanea, lee 1 frame y libera recursos.
    Retorna JPEG base64 (sin prefijo data:).
    """
    cap = cv2.VideoCapture(rtsp_url)
    try:
        if not cap.isOpened():
            raise RuntimeError("No se pudo abrir el stream RTSP.")
        ret, frame = cap.read()
        if not ret or frame is None:
            raise RuntimeError("No se pudo leer un fotograma del RTSP.")
    finally:
        try:
            cap.release()
        except Exception:
            pass

    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        raise RuntimeError("No se pudo codificar el fotograma (JPEG).")
    return base64.b64encode(buf.tobytes()).decode("ascii")


@app.post("/api/test_connection")
@login_required
@role_required("admin")
def api_test_connection():
    """
    Prueba conectividad ONVIF y (opcionalmente) RTSP, sin bloquear el request indefinidamente.

    Body esperado (JSON o form-data):
        - host, port, username, password (ONVIF)
        - rtsp_url, rtsp_username, rtsp_password (opcional)

    Returns:
        Tuple `(json, status_code)` con:
            - `status=success` y `is_ptz` si el host responde y expone PTZ.
            - `status=error` y mensaje ante fallos (timeout, auth, host invalido, etc.).
    """
    payload = request.get_json(silent=True) or {}
    if not payload:
        payload = request.form.to_dict(flat=True)

    host = (payload.get("host") or payload.get("ip") or payload.get("onvif_host") or "").strip()
    port_raw = payload.get("port") or payload.get("onvif_port") or 80
    username = (payload.get("username") or payload.get("user") or payload.get("onvif_username") or "").strip()
    password = payload.get("password") or payload.get("onvif_password") or ""
    rtsp_url = (payload.get("rtsp_url") or "").strip()
    rtsp_username = (payload.get("rtsp_username") or "").strip()
    rtsp_password = payload.get("rtsp_password") or ""

    if not host:
        return jsonify({"status": "error", "message": "Host requerido."}), 400
    try:
        port = int(port_raw)
        if port <= 0 or port > 65535:
            raise ValueError("out_of_range")
    except Exception:
        return jsonify({"status": "error", "message": "Puerto ONVIF invÃ¡lido."}), 400
    if not username or not password:
        return jsonify({"status": "error", "message": "Credenciales ONVIF incompletas."}), 400

    timeout_s = 6.0
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_detect_ptz_capability, host, int(port), username, password)
            is_ptz = bool(fut.result(timeout=timeout_s))

        # Snapshot RTSP (no bloqueante, no consume recursos).
        snapshot_b64: str | None = None
        warning: str | None = None
        if not rtsp_url:
            warning = "ONVIF OK, pero no se proporciono URL RTSP para snapshot."
        else:
            effective_rtsp = _build_rtsp_url(rtsp_url, rtsp_username, rtsp_password)
            snapshot_timeout_s = 7.0
            try:
                with ThreadPoolExecutor(max_workers=1) as ex2:
                    fut2 = ex2.submit(_grab_rtsp_snapshot_b64, effective_rtsp)
                    snapshot_b64 = fut2.result(timeout=snapshot_timeout_s)
            except FuturesTimeoutError:
                warning = "ONVIF OK, pero RTSP fallo (Timeout)."
            except Exception as e_rtsp:
                warning = f"ONVIF OK, pero RTSP fallo: {str(e_rtsp) or e_rtsp.__class__.__name__}"

        # Resultado del autodescubrimiento (Admin) => persistir en disco.
        try:
            guardar_config_camara(bool(is_ptz))
        except Exception:
            pass

        # Sincronizar con DB para evitar discrepancias (fuente secundaria).
        try:
            cfg = get_or_create_camera_config()
            cfg.camera_type = "ptz" if bool(is_ptz) else "fixed"
            db.session.commit()
        except Exception:
            # Fail-safe: no romper el test si DB falla.
            pass
        payload_ok = {"status": "success", "is_ptz": is_ptz, "snapshot_b64": snapshot_b64}
        if warning:
            payload_ok["warning"] = warning
        return jsonify(payload_ok), 200
    except FuturesTimeoutError:
        return jsonify({"status": "error", "message": "Host inalcanzable (Timeout)."}), 400
    except Exception as e:
        msg = _humanize_onvif_error(e)
        low = (str(e) or "").lower()
        if "no module named" in low and "onvif" in low:
            msg = "Dependencia faltante: instala onvif-zeep para habilitar el test ONVIF."
        return jsonify({"status": "error", "message": msg}), 400


@app.post("/api/update_model_params")
@login_required
@role_required("admin")
def api_update_model_params():
    """
    Actualiza parÃ¡metros operativos del modelo en caliente.
    Body JSON esperado:
      - confidence_threshold: float [0.10, 1.00]
      - persistence_frames: int [1, 10]
      - iou_threshold: float [0.10, 1.00]
    """
    payload = request.get_json(silent=True) or {}
    if not payload:
        payload = request.form.to_dict(flat=True)

    try:
        conf = float(payload.get("confidence_threshold"))
        iou = float(payload.get("iou_threshold"))
        persistence = int(payload.get("persistence_frames"))
    except Exception:
        return jsonify({"status": "error", "message": "ParÃ¡metros invÃ¡lidos (tipos)."}), 400

    if not (0.10 <= conf <= 1.00):
        return jsonify({"status": "error", "message": "CONFIDENCE_THRESHOLD fuera de rango (0.10 - 1.00)."}), 400
    if not (0.10 <= iou <= 1.00):
        return jsonify({"status": "error", "message": "IOU_THRESHOLD fuera de rango (0.10 - 1.00)."}), 400
    if not (1 <= persistence <= 10):
        return jsonify({"status": "error", "message": "PERSISTENCE_FRAMES fuera de rango (1 - 10)."}), 400

    updated = update_model_params(confidence_threshold=conf, persistence_frames=persistence, iou_threshold=iou)
    return jsonify({"status": "success", "model_params": updated}), 200


@app.get("/api/recent_alerts")
@login_required
@role_required("operator")
def api_recent_alerts():
    """
    Retorna las Ãºltimas detecciones confirmadas (para Panel de Alertas del Operador).
    Fail-safe: ante DB inexistente/bloqueada => lista vacÃ­a (200).
    """
    db_path = STORAGE_CONFIG.get("db_path", "detections.db")
    if db_path and not os.path.isabs(db_path):
        db_path = os.path.join(app.root_path, db_path)
    limit_raw = (request.args.get("limit") or "").strip()
    try:
        limit = int(limit_raw) if limit_raw else 15
    except Exception:
        limit = 15
    limit = max(1, min(50, int(limit)))

    alerts = []

    try:
        if not os.path.exists(db_path):
            print(f"[ALERTS] db={db_path} missing_db=1")
            return jsonify({"status": "success", "alerts": alerts}), 200

        con = sqlite3.connect(db_path, timeout=10, check_same_thread=False)
        con.row_factory = sqlite3.Row
        try:
            cur = con.cursor()
            try:
                cur.execute("PRAGMA journal_mode=WAL;")
            except Exception:
                pass

            # Detecta la tabla real disponible (evita "no such table" silencioso).
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {str(r[0]) for r in (cur.fetchall() or [])}

            rows = []
            using_table = None
            if "detections_v2" in tables:
                using_table = "detections_v2"
                cur.execute(
                    """
                    SELECT id, timestamp, confidence, x1, y1, x2, y2, class_name, source, camera_mode, image_path
                    FROM detections_v2
                    WHERE confirmed = 1
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                rows = cur.fetchall() or []
            elif "inference_frames" in tables:
                # Fallback: existe confirmación por frame, pero no hay bbox por detección.
                using_table = "inference_frames"
                cur.execute(
                    """
                    SELECT id, timestamp, NULL as confidence, NULL as x1, NULL as y1, NULL as x2, NULL as y2,
                           NULL as class_name, source, camera_mode
                    FROM inference_frames
                    WHERE confirmed = 1
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                rows = cur.fetchall() or []
            else:
                print(f"[WARN] Panel de Alertas: no hay tablas esperadas en DB. tables={sorted(tables)}")
                return jsonify({"status": "success", "alerts": []}), 200
            alerts = []
            import struct

            def _to_int(v):
                """
                Convierte valores heterogeneos de SQLite/Numpy a int seguro.

                Args:
                    v: Valor proveniente de sqlite (int/str/bytes/BLOB/etc.).

                Returns:
                    int si es convertible; si no, None.
                """
                if v is None:
                    return None
                if isinstance(v, (int, bool)):
                    return int(v)
                # En algunas filas, coordenadas se guardaron como BLOB (bytes) por tipos numpy.
                if isinstance(v, (bytes, bytearray, memoryview)):
                    b = bytes(v)
                    try:
                        if len(b) == 4:
                            return int(struct.unpack("<i", b)[0])
                        if len(b) == 8:
                            return int(struct.unpack("<q", b)[0])
                        return int.from_bytes(b, "little", signed=False)
                    except Exception:
                        return None
                try:
                    return int(v)
                except Exception:
                    return None

            for r in rows:
                x1 = _to_int(r["x1"]) if "x1" in r.keys() else None
                y1 = _to_int(r["y1"]) if "y1" in r.keys() else None
                x2 = _to_int(r["x2"]) if "x2" in r.keys() else None
                y2 = _to_int(r["y2"]) if "y2" in r.keys() else None

                image_path = None
                try:
                    image_path = r["image_path"] if "image_path" in r.keys() else None
                except Exception:
                    image_path = None
                if isinstance(image_path, (bytes, bytearray, memoryview)):
                    try:
                        image_path = bytes(image_path).decode("utf-8", errors="ignore")
                    except Exception:
                        image_path = None

                # URL web (regla solicitada):
                # - Si DB guarda "static/..." => "/static/..."
                # - Si viene absoluta dentro del proyecto => convertir a relativa
                # - Si no se puede mapear => ""
                image_url = ""
                try:
                    raw = (str(image_path).strip() if image_path else "") or ""
                    if raw:
                        p = raw.replace("\\", "/")
                        if os.path.isabs(p):
                            try:
                                root_abs = os.path.abspath(app.root_path)
                                p_abs = os.path.abspath(p)
                                if p_abs.startswith(root_abs):
                                    p = os.path.relpath(p_abs, root_abs).replace("\\", "/")
                                else:
                                    p = ""
                            except Exception:
                                p = ""
                        if p:
                            p = p.lstrip("/")
                            image_url = "/" + p
                except Exception:
                    image_url = ""
                alerts.append(
                    {
                        "id": int(r["id"]) if r["id"] is not None else None,
                        "timestamp": r["timestamp"],
                        "confidence": float(r["confidence"]) if r["confidence"] is not None else None,
                        "bbox": [x1, y1, x2, y2],
                        "class_name": r["class_name"],
                        "source": r["source"],
                        "camera_mode": r["camera_mode"],
                        "image_url": image_url,
                    }
                )
            print(f"[ALERTS] db={db_path} table={using_table} rows={len(alerts)}")
            return jsonify({"status": "success", "alerts": alerts, "table": using_table}), 200
        finally:
            try:
                con.close()
            except Exception:
                pass
    except Exception as e:
        # DB bloqueada/corrupta/etc => no romper UI del operador.
        print(f"[ERROR] Panel de Alertas DB: {e}")
        return jsonify({"status": "success", "alerts": []}), 200


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


def _dataset_recoleccion_root() -> str:
    """
    Devuelve la raiz absoluta del dataset de recoleccion configurado.

    Returns:
        Ruta absoluta del directorio configurado en `DATASET_RECOLECCION_FOLDER`.
    """
    return os.path.abspath(app.config["DATASET_RECOLECCION_FOLDER"])


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


def _iter_clean_dataset_images(limit: int = 200) -> list[dict]:
    """
    Lista imÃ¡genes limpias en dataset_recoleccion/**/limpias/*.(jpg|png)
    Retorna items con id relativo (para API) y metadatos bÃ¡sicos.
    """
    root = _dataset_recoleccion_root()
    items: list[tuple[float, str]] = []
    exts = {".jpg", ".jpeg", ".png"}

    for dirpath, dirnames, filenames in os.walk(root):
        if os.path.basename(dirpath).lower() != "limpias":
            continue
        for name in filenames:
            _, ext = os.path.splitext(name)
            if ext.lower() not in exts:
                continue
            full = os.path.join(dirpath, name)
            try:
                st = os.stat(full)
                mtime = float(st.st_mtime)
            except Exception:
                mtime = 0.0
            rel = os.path.relpath(full, root).replace("\\", "/")
            items.append((mtime, rel))

    items.sort(key=lambda x: x[0], reverse=True)
    out: list[dict] = []
    for mtime, rel in items[: max(1, int(limit))]:
        out.append(
            {
                "id": rel,
                "name": os.path.basename(rel),
                "mtime": datetime.fromtimestamp(float(mtime)).isoformat() if mtime else None,
                "url": url_for("api_get_dataset_image", path=rel),
            }
        )
    return out


@app.get("/api/get_dataset_images")
@login_required
@role_required("admin")
def api_get_dataset_images():
    """
    Lista imagenes limpias recolectadas (dataset de mejora continua).

    Query params:
        limit: maximo de items a devolver (1..500).

    Returns:
        Tuple `(json, status_code)` con la lista de imagenes y metadatos basicos.
    """
    limit_raw = (request.args.get("limit") or "").strip()
    try:
        limit = int(limit_raw) if limit_raw else 200
    except Exception:
        limit = 200
    limit = max(1, min(500, int(limit)))
    return jsonify({"status": "success", "images": _iter_clean_dataset_images(limit=limit)}), 200


@app.get("/api/dataset_image")
@login_required
@role_required("admin")
def api_get_dataset_image():
    """
    Descarga una imagen especifica del dataset de recoleccion de forma segura.

    Query params:
        path: ruta relativa dentro de la raiz del dataset.

    Returns:
        Respuesta Flask con el archivo o error HTTP (400/404).
    """
    rel = (request.args.get("path") or "").strip()
    try:
        full = _safe_join(_dataset_recoleccion_root(), rel)
    except Exception:
        abort(400)
    if not os.path.exists(full) or not os.path.isfile(full):
        abort(404)
    return send_file(full)


def _unique_dest_path(dest_dir: str, filename: str) -> str:
    """
    Genera una ruta destino unica dentro de un directorio.

    Args:
        dest_dir: Directorio destino.
        filename: Nombre de archivo original.

    Returns:
        Ruta absoluta candidata (no existente) dentro de `dest_dir`.
    """
    os.makedirs(dest_dir, exist_ok=True)
    base, ext = os.path.splitext(filename)
    ext = ext or ".jpg"
    candidate = os.path.join(dest_dir, filename)
    if not os.path.exists(candidate):
        return candidate
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = os.path.join(dest_dir, f"{base}_{stamp}{ext}")
    if not os.path.exists(candidate):
        return candidate
    # Fallback contador
    for i in range(1, 9999):
        c = os.path.join(dest_dir, f"{base}_{stamp}_{i}{ext}")
        if not os.path.exists(c):
            return c
    return os.path.join(dest_dir, f"{base}_{secrets.token_urlsafe(6)}{ext}")


@app.post("/api/classify_image")
@login_required
@role_required("admin")
def api_classify_image():
    """
    Reclasifica una imagen del dataset de recoleccion moviendola a su carpeta destino.

    Body esperado (JSON o form-data):
        - id/path: ruta relativa de la imagen dentro de dataset_recoleccion
        - label/classification: `negative|negativa|positive|positiva|positiva_dron`

    Returns:
        Tuple `(json, status_code)` indicando exito o mensaje de error.
    """
    payload = request.get_json(silent=True) or {}
    if not payload:
        payload = request.form.to_dict(flat=True)

    rel = (payload.get("id") or payload.get("path") or "").strip()
    label = (payload.get("label") or payload.get("classification") or "").strip().lower()
    if not rel:
        return jsonify({"status": "error", "message": "Falta id de imagen."}), 400
    if label not in {"positiva", "positiva_dron", "positive", "negativa", "negative"}:
        return jsonify({"status": "error", "message": "ClasificaciÃ³n invÃ¡lida."}), 400

    try:
        src = _safe_join(_dataset_recoleccion_root(), rel)
    except Exception:
        return jsonify({"status": "error", "message": "Ruta invÃ¡lida."}), 400
    if not os.path.exists(src) or not os.path.isfile(src):
        return jsonify({"status": "error", "message": "Imagen no encontrada."}), 404

    filename = os.path.basename(src)
    if label in {"negativa", "negative"}:
        dest = _unique_dest_path(DATASET_NEGATIVE_DIR, filename)
    else:
        dest = _unique_dest_path(DATASET_POSITIVE_PENDING_DIR, filename)

    try:
        shutil.move(src, dest)
    except Exception as e:
        return jsonify({"status": "error", "message": f"No se pudo mover archivo: {str(e)}"}), 500

    return jsonify({"status": "success", "moved_to": dest}), 200


def _iter_classified_images(limit: int = 300) -> list[dict]:
    """
    Lista imÃ¡genes ya clasificadas:
      - Negativas: DATASET_NEGATIVE_DIR
      - Positivas (pendientes de anotaciÃ³n): DATASET_POSITIVE_PENDING_DIR
    """
    exts = {".jpg", ".jpeg", ".png"}
    sources = [
        ("negative", DATASET_NEGATIVE_DIR, "Falso Positivo"),
        ("positive", DATASET_POSITIVE_PENDING_DIR, "Positiva (Pendiente de AnotaciÃ³n)"),
    ]

    items: list[tuple[float, dict]] = []
    for scope, base, label in sources:
        try:
            base_abs = os.path.abspath(base)
            if not os.path.exists(base_abs):
                continue
            for name in os.listdir(base_abs):
                full = os.path.join(base_abs, name)
                if not os.path.isfile(full):
                    continue
                _, ext = os.path.splitext(name)
                if ext.lower() not in exts:
                    continue
                try:
                    mtime = float(os.stat(full).st_mtime)
                except Exception:
                    mtime = 0.0
                rel = os.path.relpath(full, os.path.abspath(DATASET_TRAINING_ROOT)).replace("\\", "/")
                items.append(
                    (
                        mtime,
                        {
                            "scope": scope,
                            "label": label,
                            "name": name,
                            "id": f"{scope}:{name}",
                            "mtime": datetime.fromtimestamp(float(mtime)).isoformat() if mtime else None,
                            "url": url_for("api_get_classified_image", path=rel),
                        },
                    )
                )
        except Exception:
            continue

    items.sort(key=lambda x: x[0], reverse=True)
    return [it for _, it in items[: max(1, int(limit))]]


@app.get("/api/get_classified_images")
@login_required
@role_required("admin")
def api_get_classified_images():
    """
    Lista imagenes ya clasificadas para administracion (negativas y positivas pendientes).

    Query params:
        limit: maximo de items (1..800).

    Returns:
        Tuple `(json, status_code)` con items y metadatos.
    """
    limit_raw = (request.args.get("limit") or "").strip()
    try:
        limit = int(limit_raw) if limit_raw else 300
    except Exception:
        limit = 300
    limit = max(1, min(800, int(limit)))
    return jsonify({"status": "success", "images": _iter_classified_images(limit=limit)}), 200


@app.get("/api/classified_image")
@login_required
@role_required("admin")
def api_get_classified_image():
    """
    Descarga una imagen clasificada (dataset de entrenamiento) de forma segura.

    Query params:
        path: ruta relativa dentro de `DATASET_TRAINING_ROOT`.

    Returns:
        Respuesta Flask con el archivo o error HTTP (400/404).
    """
    rel = (request.args.get("path") or "").strip()
    try:
        full = _safe_join(os.path.abspath(DATASET_TRAINING_ROOT), rel)
    except Exception:
        abort(400)
    if not os.path.exists(full) or not os.path.isfile(full):
        abort(404)
    return send_file(full)


@app.post("/api/revert_classification")
@login_required
@role_required("admin")
def api_revert_classification():
    """
    Revierte una clasificacion moviendo la imagen al inbox de "limpias".

    Body esperado (JSON o form-data):
        - id: opcionalmente `scope:name`
        - scope: `negative|positive`
        - name: nombre del archivo

    Returns:
        Tuple `(json, status_code)` indicando exito o motivo del fallo.
    """
    payload = request.get_json(silent=True) or {}
    if not payload:
        payload = request.form.to_dict(flat=True)

    img_id = (payload.get("id") or "").strip()
    scope = (payload.get("scope") or "").strip().lower()
    name = (payload.get("name") or "").strip()

    if img_id and (":" in img_id) and (not scope or not name):
        try:
            scope, name = img_id.split(":", 1)
            scope = (scope or "").strip().lower()
            name = (name or "").strip()
        except Exception:
            pass

    if scope not in {"negative", "positive"} or not name:
        return jsonify({"status": "error", "message": "Identificador invÃ¡lido."}), 400

    src_dir = DATASET_NEGATIVE_DIR if scope == "negative" else DATASET_POSITIVE_PENDING_DIR
    src = os.path.join(src_dir, name)
    if not os.path.exists(src) or not os.path.isfile(src):
        return jsonify({"status": "error", "message": "Imagen no encontrada."}), 404

    dest = _unique_dest_path(DATASET_LIMPIAS_INBOX_DIR, name)
    try:
        shutil.move(src, dest)
    except Exception as e:
        return jsonify({"status": "error", "message": f"No se pudo revertir: {str(e)}"}), 500

    return jsonify({"status": "success"}), 200


# ======================== STREAM + STATUS ========================
@app.route("/video_feed")
@login_required
@role_required("operator")
def video_feed():
    """Entrega el stream MJPEG anotado."""
    return Response(
        process_rtsp_stream(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache"},
    )


@app.route("/detection_status")
@login_required
@role_required("operator")
def detection_status():
    """Estado resumido (para badge/UI)."""
    with state_lock:
        return jsonify(dict(current_detection_state))


@app.get("/api/camera_status")
@login_required
@role_required("operator")
def camera_status():
    """Expone si el hardware soporta PTZ (resultado de Auto-Discovery ONVIF)."""
    # Fail-safe: jamás responder 500 aquí. Ante cualquier problema de ONVIF (timeout, credenciales,
    # cámara sin PTZ, falta de dependencia), se asume cámara fija.
    ct = get_configured_camera_type()
    return jsonify({"status": "ok", "camera_type": ct, "configured_is_ptz": (ct == "ptz")}), 200


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


@app.route("/api/auto_tracking", methods=["GET", "POST"])
@login_required
@role_required("operator")
def api_auto_tracking():
    """Lee o actualiza el flag de tracking automático (solo efectivo si el hardware es PTZ)."""
    global auto_tracking_enabled
    if request.method == "GET":
        with state_lock:
            return jsonify({"enabled": bool(auto_tracking_enabled)})

    payload = {}
    try:
        payload = request.get_json(silent=True) or {}
    except Exception:
        payload = {}

    enabled = payload.get("enabled", None)
    if enabled is None:
        enabled_txt = (request.form.get("enabled") or "").strip().lower()
        enabled = enabled_txt in {"1", "true", "t", "yes", "y", "on"}

    with state_lock:
        # Seguridad: no habilitar tracking si el hardware no es PTZ.
        auto_tracking_enabled = bool(enabled) and bool(is_ptz_capable)
        disabled = not bool(enabled)
    if disabled:
        ptz_worker.enqueue_stop()
    with state_lock:
        return jsonify({"enabled": bool(auto_tracking_enabled)})


@app.route("/api/inspection_mode", methods=["GET", "POST"])
@login_required
@role_required("operator")
def api_inspection_mode():
    """Lee o actualiza el modo de inspección/patrullaje automático (solo efectivo si PTZ)."""
    global inspection_mode_enabled

    if request.method == "GET":
        with state_lock:
            return jsonify({"enabled": bool(inspection_mode_enabled)})

    payload = request.get_json(silent=True) or {}
    enabled = bool(payload.get("enabled"))

    with state_lock:
        if enabled:
            inspection_mode_enabled = bool(enabled) and bool(is_ptz_capable) and bool(leer_config_camara())
            # Al habilitar inspección, garantizar que el tracking esté listo para intervenir.
            # (Desacoplado) No tocar auto_tracking aquÃ­.
        else:
            inspection_mode_enabled = False
            # (Desacoplado) No tocar auto_tracking aquÃ­.

        disabled = not bool(enabled)

    if disabled:
        ptz_worker.enqueue_stop()

    with state_lock:
        return jsonify({"enabled": bool(inspection_mode_enabled)})

def _require_ptz_capable() -> None:
    """Bloquea rutas PTZ cuando el Auto-Discovery determina cámara fija."""
    with state_lock:
        ok = bool(is_ptz_capable)
    if not ok:
        abort(403)


@app.post("/ptz_move")
@login_required
@role_required("operator")
def ptz_move():
    """Movimiento PTZ (joystick) o vector libre; bloqueado si la cámara no es PTZ."""
    _require_ptz_capable()
    payload = request.get_json(silent=True) or {}
    direction = (payload.get("direction") or "").strip().lower()
    if direction:
        ptz_worker.enqueue_direction(direction)
        return jsonify({"ok": True})

    try:
        x = float(payload.get("x") or 0.0)
        y = float(payload.get("y") or 0.0)
        zoom = float(payload.get("zoom") or 0.0)
        duration_s = float(payload.get("duration_s") or 0.15)
    except Exception:
        return jsonify({"ok": False, "error": "Payload inválido."}), 400

    x = _clamp(x, -1.0, 1.0)
    y = _clamp(y, -1.0, 1.0)
    zoom = _clamp(zoom, -1.0, 1.0)
    duration_s = _clamp(duration_s, 0.05, 0.6)
    ptz_worker.enqueue_move(x=x, y=y, zoom=zoom, duration_s=duration_s)
    return jsonify({"ok": True})


@app.post("/ptz_stop")
@login_required
@role_required("operator")
def ptz_stop():
    """Stop PTZ; bloqueado si la cámara no es PTZ."""
    _require_ptz_capable()
    global auto_tracking_enabled, inspection_mode_enabled
    with state_lock:
        auto_tracking_enabled = False
        inspection_mode_enabled = False
    ptz_worker.enqueue_stop()
    return jsonify({"ok": True})


@app.route("/video_progress")
@login_required
@role_required("operator")
def video_progress():
    """Progreso/resultado de un job de inferencia manual (polling desde el frontend)."""
    job_id = (request.args.get("job_id") or "").strip()
    if not job_id:
        return jsonify({"success": False, "error": "Falta job_id"}), 400
    with job_lock:
        p = progress_by_job.get(job_id)
        r = result_by_job.get(job_id)
    if not p:
        return jsonify({"success": False, "error": "Job no encontrado"}), 404
    payload = dict(p)
    if r:
        payload.update(r)
    return jsonify(payload)


# ======================== UPLOAD DETECT (persist results) ========================
@app.route("/upload_detect", methods=["POST"])
@login_required
@role_required("operator")
def upload_detect():
    """Encola una detección manual (imagen/video) y retorna `job_id`."""
    try:
        if "file" not in request.files:
            return jsonify({"success": False, "status": "error", "message": "No se subió archivo", "error": "No se subió archivo"}), 400
        f = request.files["file"]
        if not f or not f.filename:
            return jsonify({"success": False, "status": "error", "message": "Archivo sin nombre", "error": "Archivo sin nombre"}), 400
        if not allowed_file(f.filename):
            return jsonify({"success": False, "status": "error", "message": "Extensión no permitida", "error": "Extensión no permitida"}), 400
        if yolo_model is None:
            return jsonify({"success": False, "status": "error", "message": "Modelo YOLO no disponible", "error": "Modelo YOLO no disponible"}), 500

        filename = secure_filename(f.filename)
        ts = int(time.time())
        job_id = secrets.token_urlsafe(10)
        temp_name = f"{ts}_{job_id}_{filename}"
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        temp_path = os.path.join(app.config["UPLOAD_FOLDER"], temp_name)
        f.save(temp_path)

        ext = filename.rsplit(".", 1)[1].lower()
        analysis_root = None
        clean_dir = None
        bb_dir = None
        if ext in {"mp4", "avi", "mov"}:
            stem = os.path.splitext(filename)[0].strip() or "video"
            ts_folder = datetime.now().strftime("%Y%m%d_%H%M")
            folder_base = f"{stem}_{ts_folder}"
            analysis_root = os.path.join(app.config["DATASET_RECOLECCION_FOLDER"], folder_base)
            if os.path.exists(analysis_root):
                analysis_root = os.path.join(app.config["DATASET_RECOLECCION_FOLDER"], f"{folder_base}_{job_id[:6]}")
            clean_dir = os.path.join(analysis_root, "limpias")
            bb_dir = os.path.join(analysis_root, "con_bounding_box")
            os.makedirs(clean_dir, exist_ok=True)
            os.makedirs(bb_dir, exist_ok=True)

        with job_lock:
            progress_by_job[job_id] = {"success": True, "job_id": job_id, "progress": 0, "status": "queued", "done": False}
        threading.Thread(target=_run_detection_job, args=(job_id, temp_path, ext, filename, clean_dir, bb_dir), daemon=True).start()
        return jsonify({"success": True, "job_id": job_id, "analysis_root": analysis_root})
    except Exception as e:
        try:
            if "temp_path" in locals() and temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass
        return jsonify({"success": False, "status": "error", "message": str(e), "error": str(e)}), 500


def _set_job_progress(job_id: str, progress: int, status: str | None = None, done: bool | None = None):
    """Actualiza progreso de un job de inferencia manual."""
    with job_lock:
        if job_id not in progress_by_job:
            progress_by_job[job_id] = {"success": True, "job_id": job_id}
        progress_by_job[job_id]["progress"] = int(max(0, min(100, progress)))
        if status is not None:
            progress_by_job[job_id]["status"] = status
        if done is not None:
            progress_by_job[job_id]["done"] = bool(done)


def _set_job_result(job_id: str, payload: dict):
    """Persiste el payload final del job (URL de resultado, métricas o error)."""
    with job_lock:
        result_by_job[job_id] = payload


def _run_detection_job(job_id: str, temp_path: str, ext: str, original_filename: str, clean_dir: str | None, bb_dir: str | None):
    """Ejecuta el job de detección manual en un hilo (no bloquea request)."""
    try:
        _set_job_progress(job_id, 1, status="starting")
        if ext in {"jpg", "jpeg", "png"}:
            _process_image_and_persist(job_id, temp_path)
        elif ext in {"mp4", "avi", "mov"}:
            _process_video_and_persist(job_id, temp_path, original_filename=original_filename, clean_dir=clean_dir, bb_dir=bb_dir)
        else:
            _set_job_result(job_id, {"success": False, "error": "Tipo de archivo no soportado"})
        _set_job_progress(job_id, 100, status="done", done=True)
    except Exception as e:
        _set_job_result(job_id, {"success": False, "error": str(e)})
        _set_job_progress(job_id, 100, status="error", done=True)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def _process_image_and_persist(job_id: str, path: str):
    """Procesa una imagen: inferencia YOLO, dibuja y guarda el resultado en `static/results`."""
    image = cv2.imread(path)
    if image is None:
        raise RuntimeError("No se pudo leer la imagen")

    _set_job_progress(job_id, 10, status="infering")

    h, w = image.shape[:2]
    if w > 1280 or h > 720:
        scale = min(1280 / w, 720 / h)
        image = cv2.resize(image, (int(w * scale), int(h * scale)))

    params = get_model_params()
    t0 = time.time()
    results = yolo_model(
        image,
        device=YOLO_CONFIG["device"],
        conf=float(params.get("confidence_threshold", YOLO_CONFIG["confidence"])),
        iou=float(params.get("iou_threshold", 0.45)),
        verbose=YOLO_CONFIG["verbose"],
    )
    inference_ms = float((time.time() - t0) * 1000.0)
    image, detection_list = draw_detections(image, results)

    out_name = f"result_{job_id}.jpg"
    out_path = os.path.join(app.config["RESULTS_FOLDER"], out_name)
    cv2.imwrite(out_path, image)

    avg_conf = float(np.mean([d["confidence"] for d in detection_list])) if detection_list else 0.0

    # Telemetría (persistencia en detections_v2/inference_frames)
    try:
        h, w = image.shape[:2]
        with state_lock:
            cam_mode = str(camera_source_mode)
        _metrics_writer.enqueue(
            FrameRecord(
                timestamp_iso=datetime.now().isoformat(),
                source="upload_image",
                inference_ms=inference_ms,
                frame_w=int(w),
                frame_h=int(h),
                detections=list(detection_list),
                confirmed=bool(detection_list),
                camera_mode=cam_mode,
            )
        )
    except Exception:
        pass

    _set_job_result(
        job_id,
        {
            "success": True,
            "result_type": "image",
            "result_url": f"/static/results/{out_name}",
            "detections_count": len(detection_list),
            "avg_confidence": avg_conf,
        },
    )


def _open_writer_h264(path: str, fps: float, width: int, height: int):
    """Intenta abrir un `cv2.VideoWriter` H.264; retorna (writer|None, codec_usado)."""
    # Intentar H.264 directo si la build de OpenCV/FFmpeg lo soporta.
    for fourcc_name in ("avc1", "H264"):
        try:
            fourcc = cv2.VideoWriter_fourcc(*fourcc_name)
            out = cv2.VideoWriter(path, fourcc, float(fps), (width, height))
            if out.isOpened():
                return out, fourcc_name
        except Exception:
            pass
    return None, None


def _ffmpeg_transcode_h264(src_path: str, dst_path: str):
    """Transcodifica a H.264 con ffmpeg (python-ffmpeg o binario), si está disponible."""
    # Preferir ffmpeg-python si está disponible (requiere binario ffmpeg en PATH).
    if ffmpeg is not None:
        try:
            (
                ffmpeg.input(src_path)
                .output(dst_path, vcodec="libx264", pix_fmt="yuv420p", movflags="+faststart")
                .overwrite_output()
                .run(quiet=True)
            )
            return True
        except Exception:
            pass

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        return False
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        src_path,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        dst_path,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def _persist_top_detections_images(clean_dir: str, bb_dir: str, top_items: list[tuple[float, int, bytes, bytes]]) -> list[dict]:
    """Guarda Top 10 en limpio + con bounding box y devuelve al frontend SOLO las imÃ¡genes con bounding box.

    - Archivo: `conf_98_5_frame_145.jpg`
    - JSON: usa `image_base64` para renderizar en la galerÃ­a/modal sin exponer el dataset por /static.
    """
    os.makedirs(clean_dir, exist_ok=True)
    os.makedirs(bb_dir, exist_ok=True)

    payload_items: list[dict] = []
    for conf, frame_no, clean_jpg, bb_jpg in top_items[:10]:
        conf_str = f"{(float(conf) * 100.0):.1f}".replace(".", "_")
        fname = f"conf_{conf_str}_frame_{int(frame_no)}.jpg"
        with open(os.path.join(clean_dir, fname), "wb") as fp:
            fp.write(clean_jpg)
        with open(os.path.join(bb_dir, fname), "wb") as fp:
            fp.write(bb_jpg)

        b64 = base64.b64encode(bb_jpg).decode("ascii")
        payload_items.append({"confidence": float(conf), "frame": int(frame_no), "image_base64": f"data:image/jpeg;base64,{b64}"})

    return payload_items


def _process_video_and_persist(job_id: str, path: str, original_filename: str | None = None, clean_dir: str | None = None, bb_dir: str | None = None):
    """Procesa un video: inferencia frame-a-frame y persistencia del MP4 anotado."""
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError("No se pudo leer el video")

    fps = cap.get(cv2.CAP_PROP_FPS) or VIDEO_CONFIG["fps"]
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or VIDEO_CONFIG["width"]
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or VIDEO_CONFIG["height"]
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    if width > 1280 or height > 720:
        scale = min(1280 / width, 720 / height)
        width = int(width * scale)
        height = int(height * scale)

    out_name = f"result_{job_id}.mp4"
    out_path = os.path.join(app.config["RESULTS_FOLDER"], out_name)
    tmp_path = os.path.join(app.config["RESULTS_FOLDER"], f"tmp_{job_id}.mp4")

    out, used = _open_writer_h264(out_path, fps, width, height)
    wrote_to = out_path
    if out is None:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(tmp_path, fourcc, float(fps), (width, height))
        wrote_to = tmp_path
        used = "mp4v"
    if not out.isOpened():
        raise RuntimeError("No se pudo crear el writer de video (codec).")

    frame_count = 0
    total_detections = 0
    total_conf = 0.0
    # Top-N frames con mayor confianza (guardamos JPG para no acumular frames crudos en RAM).
    top_n = 10
    top_heap: list[tuple[float, int, bytes, bytes]] = []

    try:
        try:
            from tqdm import tqdm  # type: ignore

            iterator = tqdm(total=total_frames if total_frames > 0 else None, desc="Procesando video", unit="frame")
        except Exception:
            iterator = None

        _set_job_progress(job_id, 1, status="processing")
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame.shape[1] != width or frame.shape[0] != height:
                frame = cv2.resize(frame, (width, height))

            # Dataset limpio: copiar el frame ANTES de dibujar bounding boxes / labels.
            clean_frame = frame.copy()

            params = get_model_params()
            results = yolo_model(
                frame,
                device=YOLO_CONFIG["device"],
                conf=float(params.get("confidence_threshold", YOLO_CONFIG["confidence"])),
                iou=float(params.get("iou_threshold", 0.45)),
                verbose=YOLO_CONFIG["verbose"],
            )
            frame, detection_list = draw_detections(frame, results)

            total_detections += len(detection_list)
            if detection_list:
                total_conf += float(np.mean([d["confidence"] for d in detection_list]))
                best_conf = float(max(d["confidence"] for d in detection_list))
                bb_frame = frame
                ok_clean, clean_buf = cv2.imencode(".jpg", clean_frame, [cv2.IMWRITE_JPEG_QUALITY, VIDEO_CONFIG["jpeg_quality"]])
                ok_bb, bb_buf = cv2.imencode(".jpg", bb_frame, [cv2.IMWRITE_JPEG_QUALITY, VIDEO_CONFIG["jpeg_quality"]])
                if ok_clean and ok_bb:
                    frame_no = frame_count + 1
                    item = (best_conf, int(frame_no), clean_buf.tobytes(), bb_buf.tobytes())
                    if len(top_heap) < top_n:
                        heapq.heappush(top_heap, item)
                    elif best_conf > top_heap[0][0]:
                        heapq.heapreplace(top_heap, item)

            out.write(frame)
            frame_count += 1

            if iterator is not None:
                iterator.update(1)

            if total_frames > 0 and frame_count % 3 == 0:
                _set_job_progress(job_id, int((frame_count / total_frames) * 100), status="processing")
            elif total_frames <= 0 and frame_count % 15 == 0:
                approx = min(95, 5 + int(frame_count / max(1, int(VIDEO_CONFIG.get("fps", 30)))))
                _set_job_progress(job_id, approx, status="processing")
    finally:
        try:
            if iterator is not None:
                iterator.close()
        except Exception:
            pass
        cap.release()
        out.release()

    # Si no se pudo escribir H.264 directo, transcodificar a libx264 si existe ffmpeg.
    if used not in {"avc1", "H264"} and wrote_to != out_path:
        try:
            ok = _ffmpeg_transcode_h264(wrote_to, out_path)
            if not ok:
                shutil.copyfile(wrote_to, out_path)
        finally:
            try:
                os.remove(wrote_to)
            except Exception:
                pass

    avg_conf = (total_conf / max(1, frame_count)) if frame_count else 0.0
    top_items = sorted(top_heap, key=lambda x: x[0], reverse=True)

    if not clean_dir or not bb_dir:
        stem = os.path.splitext(original_filename or "")[0].strip() or "video"
        ts_folder = datetime.now().strftime("%Y%m%d_%H%M")
        folder_base = f"{stem}_{ts_folder}"
        analysis_root = os.path.join(app.config["DATASET_RECOLECCION_FOLDER"], folder_base)
        if os.path.exists(analysis_root):
            analysis_root = os.path.join(app.config["DATASET_RECOLECCION_FOLDER"], f"{folder_base}_{job_id[:6]}")
        clean_dir = os.path.join(analysis_root, "limpias")
        bb_dir = os.path.join(analysis_root, "con_bounding_box")
        os.makedirs(clean_dir, exist_ok=True)
        os.makedirs(bb_dir, exist_ok=True)

    top_detections = _persist_top_detections_images(clean_dir, bb_dir, top_items) if top_items else []
    _set_job_result(
        job_id,
        {
            "success": True,
            "result_type": "video",
            "result_url": f"/static/results/{out_name}",
            "top_detections": top_detections,
            "frames_processed": frame_count,
            "total_detections": total_detections,
            "avg_confidence": float(avg_conf),
        },
    )


# ======================== INIT ========================
with app.app_context():
    db.create_all()
    cfg = get_or_create_camera_config()
    try:
        guardar_config_camara((cfg.camera_type or "fixed").strip().lower() == "ptz")
    except Exception:
        pass
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
