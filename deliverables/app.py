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
import queue
import secrets
import shutil
import subprocess
import threading
import time
from datetime import datetime
from functools import wraps
from urllib.parse import urlparse

import cv2
import numpy as np
from flask import (
    Flask,
    Response,
    abort,
    flash,
    jsonify,
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

from config import FLASK_CONFIG, RTSP_CONFIG, STORAGE_CONFIG, VIDEO_CONFIG, YOLO_CONFIG
from models import CameraConfig, User, db
from ptz_controller import PTZController

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
app.config["ALLOWED_EXTENSIONS"] = STORAGE_CONFIG["allowed_extensions"]

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs(app.config["RESULTS_FOLDER"], exist_ok=True)

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
    print("  - admin / admin123 (role=admin)")
    print("  - operador / operador123 (role=operator)")


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

        model = YOLO(YOLO_CONFIG["model_path"])
        model.to(YOLO_CONFIG["device"])
        print("[SUCCESS] Modelo YOLO cargado en GPU (cuda:0).")
        return model
    except Exception as e:
        print(f"[ERROR] No se pudo cargar YOLO: {e}")
        return None


yolo_model = load_yolo_model()

# ======================== LIVE STATE ========================
state_lock = threading.Lock()
stream_lock = threading.Lock()

camera_source_mode = "fixed"  # fixed | ptz (autodescubrimiento ONVIF)

# Mitigación de aves:
# Requiere que la detección "persista" por N frames consecutivos antes de marcar `detected=True`
# y antes de activar tracking PTZ automático. Esto reduce falsos positivos por aves/ruido.
try:
    DETECTION_PERSISTENCE_FRAMES = max(1, int(os.environ.get("DETECTION_PERSISTENCE_FRAMES", "3")))
except Exception:
    DETECTION_PERSISTENCE_FRAMES = 3

# Autodescubrimiento de hardware (NO confiar en selector manual).
is_ptz_capable = False
auto_tracking_enabled = False
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


def _clamp(v: float, lo: float, hi: float) -> float:
    """Limita un valor float al rango [lo, hi]."""
    return float(max(lo, min(hi, v)))


def _bbox_area(bbox_xyxy: tuple[int, int, int, int]) -> int:
    """Área del bbox para priorización (Enjambre): bbox más grande => mayor prioridad."""
    x1, y1, x2, y2 = bbox_xyxy
    return max(0, int(x2) - int(x1)) * max(0, int(y2) - int(y1))


def _select_priority_detection(detection_list: list[dict]) -> dict | None:
    """
    Regla de priorización (Enjambre):
    Si hay múltiples detecciones, el tracking PTZ debe centrarse en el bbox MÁS GRANDE.
    """
    if not detection_list:
        return None
    return max(detection_list, key=lambda d: _bbox_area(tuple(d["bbox"])))


def _set_ptz_capable(value: bool, *, error: str | None = None) -> None:
    """
    Actualiza el estado global de capacidad PTZ.

    Importante:
    - Si el hardware NO es PTZ: se deshabilita `auto_tracking_enabled` por seguridad.
    - Esto es parte del "bloqueo de rutas de movimiento" cuando la cámara es fija.
    """
    global is_ptz_capable, camera_source_mode, _onvif_last_probe_error, auto_tracking_enabled
    with state_lock:
        is_ptz_capable = bool(value)
        _onvif_last_probe_error = error
        if not is_ptz_capable:
            auto_tracking_enabled = False
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


def _maybe_refresh_onvif_probe(max_age_s: float = 15.0) -> None:
    """Refresca Auto-Discovery en un hilo (no bloquea request) cuando el cache expira."""
    last = _onvif_last_probe_at
    if last is not None and (time.time() - last) < float(max_age_s):
        return
    threading.Thread(target=_probe_onvif_ptz_capability, daemon=True).start()


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
    """

    def __init__(self):
        """Inicializa cola, thread y estado de rate-limit."""
        self._q: queue.Queue[dict] = queue.Queue(maxsize=80)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._controller: PTZController | None = None
        self._last_cmd_at = 0.0

    def start(self):
        """Inicia el hilo worker (idempotente)."""
        if not self._thread.is_alive():
            self._thread.start()

    def enqueue_move(self, *, x: float, y: float, zoom: float = 0.0, duration_s: float = 0.15):
        """Encola un movimiento continuo (pan/tilt/zoom) con duración limitada."""
        try:
            self._q.put_nowait(
                {"type": "move", "x": float(x), "y": float(y), "zoom": float(zoom), "duration_s": float(duration_s)}
            )
        except Exception:
            pass

    def enqueue_direction(self, direction: str):
        """Encola un movimiento direccional (arriba/abajo/izq/der) para el joystick."""
        x, y, z = _ptz_vector(direction)
        self.enqueue_move(x=x, y=y, zoom=z, duration_s=0.15)

    def enqueue_stop(self):
        """Encola un stop PTZ (prioridad para evitar drift)."""
        try:
            self._q.put_nowait({"type": "stop"})
        except Exception:
            pass

    def _get_controller(self) -> PTZController | None:
        """Construye un controlador PTZ desde la configuración persistida (requiere app context)."""
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
        """Loop del worker: rate-limit y ejecución segura de comandos ONVIF PTZ."""
        while not self._stop.is_set():
            try:
                cmd = self._q.get(timeout=0.2)
            except queue.Empty:
                continue

            cmd_type = (cmd.get("type") or "").lower()

            # Rate limit (evita saturar PTZ) - sólo moves
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
                    print("[RTSP] Lectura fallida. Reintentando conexión...")
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


class _LiveVideoProcessor:
    """Ejecuta inferencia YOLO y actualiza el frame anotado para el stream MJPEG."""

    def __init__(self, reader: _RTSPLatestFrameReader):
        """Inicializa el pipeline live (inferencia + anotación + publicación de último JPEG)."""
        self.reader = reader
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._stop = threading.Event()
        self._last_ts = None
        self._frame_count = 0
        self._detection_times = []
        self._persistence = _DetectionPersistence(DETECTION_PERSISTENCE_FRAMES)

    def start(self):
        """Inicia el thread de procesamiento (idempotente)."""
        if not self._thread.is_alive():
            self._thread.start()

    def _run(self):
        """Loop principal: toma frames, corre YOLO, aplica mitigación aves y tracking PTZ."""
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
            except Exception:
                pass

            self._frame_count += 1

            detection_list = []
            if yolo_model is not None and (self._frame_count % max(1, VIDEO_CONFIG.get("inference_interval", 1)) == 0):
                try:
                    t0 = time.time()
                    results = yolo_model(
                        frame,
                        device=YOLO_CONFIG["device"],
                        conf=YOLO_CONFIG["confidence"],
                        verbose=YOLO_CONFIG["verbose"],
                    )
                    dt = time.time() - t0
                    self._detection_times.append(dt)
                    self._detection_times = self._detection_times[-30:]
                    frame, detection_list = draw_detections(frame, results)
                except Exception as e:
                    print(f"[YOLO][ERROR] {e}")
                    cv2.putText(frame, "Error en inferencia", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            # ---------------- Mitigación de aves (persistencia) ----------------
            # Solo se "confirma" detección tras N frames consecutivos con detecciones.
            # Esto afecta:
            # - La bandera `detected` y estado UI.
            # - El tracking PTZ automático (no mover ante falsos positivos instantáneos).
            confirmed, consecutive_hits = self._persistence.update(bool(detection_list))

            # ---------------- Tracking automático PTZ (hilo separado) ----------------
            with state_lock:
                mode = camera_source_mode
                tracking = bool(auto_tracking_enabled)
            # Regla de priorización (Enjambre): seleccionar bbox MÁS GRANDE.
            priority = _select_priority_detection(detection_list)
            if mode == "ptz" and tracking and confirmed and priority is not None:
                h, w = frame.shape[:2]
                dx, dy = _bbox_offset_norm(w, h, priority["bbox"])  # dy>0 => bbox abajo

                # Bloque clave: cálculo del vector de error para el movimiento PTZ.
                # - dx se usa para pan (derecha/izquierda)
                # - dy se invierte para tilt (arriba/abajo) por convención ONVIF
                # Umbral central evita jitter cuando el bbox ya está centrado.
                if abs(dx) > 0.12 or abs(dy) > 0.12:
                    k = 0.55  # ganancia proporcional (ajustable)
                    x = _clamp(dx * k, -0.6, 0.6)
                    y = _clamp((-dy) * k, -0.6, 0.6)
                    ptz_worker.enqueue_move(x=x, y=y, zoom=0.0, duration_s=0.12)

            # Estado UI
            with state_lock:
                current_detection_state["camera_source_mode"] = camera_source_mode
                current_detection_state["last_update"] = datetime.now().isoformat()
                if detection_list and confirmed:
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
            detection_list.append({"confidence": conf, "bbox": (x1, y1, x2, y2)})
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
    """Dashboard principal (manual + live)."""
    cfg = get_or_create_camera_config()
    active_tab = (request.args.get("tab") or "").strip().lower() or "live"
    if active_tab not in {"live", "manual"}:
        active_tab = "live"
    return render_template(
        "index.html",
        is_admin=(current_user.role == "admin"),
        camera_type=cfg.camera_type,
        current_user=current_user,
        active_tab=active_tab,
    )


@app.route("/admin/camera", methods=["GET", "POST"])
@login_required
@role_required("admin")
def admin_camera():
    """Panel admin para editar RTSP/ONVIF (persistido en DB)."""
    cfg = get_or_create_camera_config()

    if request.method == "POST":
        cfg.camera_type = (request.form.get("camera_type") or "fixed").lower()

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
        return redirect(url_for("admin_camera"))

    return render_template("admin_camera.html", cfg=cfg)


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


# ======================== STREAM + STATUS ========================
@app.route("/video_feed")
@login_required
def video_feed():
    """Entrega el stream MJPEG anotado."""
    return Response(
        process_rtsp_stream(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache"},
    )


@app.route("/detection_status")
@login_required
def detection_status():
    """Estado resumido (para badge/UI)."""
    with state_lock:
        return jsonify(dict(current_detection_state))


@app.get("/api/camera_status")
@login_required
def camera_status():
    """Expone si el hardware soporta PTZ (resultado de Auto-Discovery ONVIF)."""
    # Fail-safe: jamás responder 500 aquí. Ante cualquier problema de ONVIF (timeout, credenciales,
    # cámara sin PTZ, falta de dependencia), se asume cámara fija.
    try:
        _maybe_refresh_onvif_probe(max_age_s=15.0)
        with state_lock:
            return jsonify({"is_ptz_capable": bool(is_ptz_capable), "status": "ok"})
    except Exception as e:
        _set_ptz_capable(False, error=str(e))
        return jsonify({"is_ptz_capable": False, "status": "error"}), 200


@app.route("/api/auto_tracking", methods=["GET", "POST"])
@login_required
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
        return jsonify({"enabled": bool(auto_tracking_enabled)})


def _require_ptz_capable() -> None:
    """Bloquea rutas PTZ cuando el Auto-Discovery determina cámara fija."""
    with state_lock:
        ok = bool(is_ptz_capable)
    if not ok:
        abort(403)


@app.post("/ptz_move")
@login_required
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
def ptz_stop():
    """Stop PTZ; bloqueado si la cámara no es PTZ."""
    _require_ptz_capable()
    ptz_worker.enqueue_stop()
    return jsonify({"ok": True})


@app.route("/video_progress")
@login_required
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
def upload_detect():
    """Encola una detección manual (imagen/video) y retorna `job_id`."""
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No se subió archivo"}), 400
    f = request.files["file"]
    if not f or not f.filename:
        return jsonify({"success": False, "error": "Archivo sin nombre"}), 400
    if not allowed_file(f.filename):
        return jsonify({"success": False, "error": "Extensión no permitida"}), 400
    if yolo_model is None:
        return jsonify({"success": False, "error": "Modelo YOLO no disponible"}), 500

    filename = secure_filename(f.filename)
    ts = int(time.time())
    job_id = secrets.token_urlsafe(10)
    temp_name = f"{ts}_{job_id}_{filename}"
    temp_path = os.path.join(app.config["UPLOAD_FOLDER"], temp_name)
    f.save(temp_path)

    ext = filename.rsplit(".", 1)[1].lower()
    try:
        with job_lock:
            progress_by_job[job_id] = {"success": True, "job_id": job_id, "progress": 0, "status": "queued", "done": False}
        threading.Thread(target=_run_detection_job, args=(job_id, temp_path, ext), daemon=True).start()
        return jsonify({"success": True, "job_id": job_id})
    finally:
        # Limpieza: se realiza al finalizar el job.
        pass


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


def _run_detection_job(job_id: str, temp_path: str, ext: str):
    """Ejecuta el job de detección manual en un hilo (no bloquea request)."""
    try:
        _set_job_progress(job_id, 1, status="starting")
        if ext in {"jpg", "jpeg", "png"}:
            _process_image_and_persist(job_id, temp_path)
        elif ext in {"mp4", "avi", "mov"}:
            _process_video_and_persist(job_id, temp_path)
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

    results = yolo_model(image, device=YOLO_CONFIG["device"], conf=YOLO_CONFIG["confidence"], verbose=YOLO_CONFIG["verbose"])
    image, detection_list = draw_detections(image, results)

    out_name = f"result_{job_id}.jpg"
    out_path = os.path.join(app.config["RESULTS_FOLDER"], out_name)
    cv2.imwrite(out_path, image)

    avg_conf = float(np.mean([d["confidence"] for d in detection_list])) if detection_list else 0.0
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


def _process_video_and_persist(job_id: str, path: str):
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

            results = yolo_model(frame, device=YOLO_CONFIG["device"], conf=YOLO_CONFIG["confidence"], verbose=YOLO_CONFIG["verbose"])
            frame, detection_list = draw_detections(frame, results)

            total_detections += len(detection_list)
            if detection_list:
                total_conf += float(np.mean([d["confidence"] for d in detection_list]))

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
    _set_job_result(
        job_id,
        {
            "success": True,
            "result_type": "video",
            "result_url": f"/static/results/{out_name}",
            "frames_processed": frame_count,
            "total_detections": total_detections,
            "avg_confidence": float(avg_conf),
        },
    )


# ======================== INIT ========================
with app.app_context():
    db.create_all()
    cfg = get_or_create_camera_config()
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
