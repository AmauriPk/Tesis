from __future__ import annotations

import os
import queue
import secrets
import shutil
import subprocess
import threading
import time
from datetime import datetime
from functools import wraps
import json

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


@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(User, int(user_id))


def role_required(*roles: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if current_user.role not in roles:
                flash("Acceso denegado: permisos insuficientes.", "danger")
                return redirect(url_for("index"))
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]


def get_or_create_camera_config() -> CameraConfig:
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

camera_source_mode = "fixed"  # fixed | ptz (por DB; override admin permitido)

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


def _bbox_off_center(frame_w: int, frame_h: int, bbox_xyxy):
    x1, y1, x2, y2 = bbox_xyxy
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0

    tol_w = 0.20 * frame_w
    tol_h = 0.20 * frame_h
    center_x = frame_w / 2.0
    center_y = frame_h / 2.0

    dx = cx - center_x
    dy = cy - center_y

    if abs(dx) <= tol_w and abs(dy) <= tol_h:
        return None

    if abs(dx) >= abs(dy):
        return "left" if dx < 0 else "right"
    return "up" if dy < 0 else "down"


def _ptz_vector(direction: str):
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
        self._q: queue.Queue[str] = queue.Queue(maxsize=50)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._controller: PTZController | None = None
        self._last_cmd_at = 0.0

    def start(self):
        if not self._thread.is_alive():
            self._thread.start()

    def enqueue(self, direction: str):
        try:
            self._q.put_nowait(direction)
        except Exception:
            pass

    def _get_controller(self) -> PTZController | None:
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
        while not self._stop.is_set():
            try:
                direction = self._q.get(timeout=0.2)
            except queue.Empty:
                continue

            # Rate limit (evita saturar PTZ)
            now = time.time()
            if now - self._last_cmd_at < 0.25:
                continue
            self._last_cmd_at = now

            try:
                if self._controller is None:
                    self._controller = self._get_controller()
                if self._controller is None:
                    continue
                x, y, z = _ptz_vector(direction)
                self._controller.continuous_move(x=x, y=y, zoom=z, duration_s=0.15)
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
        self._lock = threading.Lock()
        self._frame = None
        self._ts = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._current_url = None

    def start(self):
        if not self._thread.is_alive():
            self._thread.start()

    def get_latest(self):
        with self._lock:
            return self._frame, self._ts

    def _get_rtsp_url(self) -> str | None:
        # Los hilos no tienen app context por defecto.
        with app.app_context():
            cfg = get_or_create_camera_config()
            url = cfg.effective_rtsp_url()
            return url or RTSP_CONFIG.get("url")

    def _run(self):
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


class _LiveVideoProcessor:
    def __init__(self, reader: _RTSPLatestFrameReader):
        self.reader = reader
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._stop = threading.Event()
        self._last_ts = None
        self._frame_count = 0
        self._detection_times = []

    def start(self):
        if not self._thread.is_alive():
            self._thread.start()

    def _run(self):
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

            try:
                frame = cv2.resize(frame, (VIDEO_CONFIG["width"], VIDEO_CONFIG["height"]))
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

            # Regla adaptativa: si PTZ y bbox fuera del centro -> encolar comando en hilo PTZ
            with state_lock:
                mode = camera_source_mode
            if mode == "ptz" and detection_list:
                best = max(detection_list, key=lambda d: d["confidence"])
                h, w = frame.shape[:2]
                direction = _bbox_off_center(w, h, best["bbox"])
                if direction:
                    ptz_worker.enqueue(direction)

            # Estado UI
            with state_lock:
                current_detection_state["camera_source_mode"] = camera_source_mode
                current_detection_state["last_update"] = datetime.now().isoformat()
                if detection_list:
                    avg_conf = float(np.mean([d["confidence"] for d in detection_list]))
                    current_detection_state["status"] = "Alerta: Dron detectado"
                    current_detection_state["avg_confidence"] = avg_conf
                    current_detection_state["detected"] = True
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
    global _live_threads_started
    if _live_threads_started:
        return
    _rtsp_reader.start()
    _live_processor.start()
    _live_threads_started = True


def draw_detections(frame, results):
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
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("index"))
        flash("Credenciales inválidas.", "danger")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
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
    cfg = get_or_create_camera_config()
    return render_template(
        "index.html",
        is_admin=(current_user.role == "admin"),
        camera_type=cfg.camera_type,
        current_user=current_user,
    )


@app.route("/admin/camera", methods=["GET", "POST"])
@login_required
@role_required("admin")
def admin_camera():
    cfg = get_or_create_camera_config()

    if request.method == "POST":
        cfg.camera_type = (request.form.get("camera_type") or "fixed").lower()

        cfg.rtsp_url = (request.form.get("rtsp_url") or "").strip() or None
        cfg.rtsp_username = (request.form.get("rtsp_username") or "").strip() or None
        cfg.rtsp_password = (request.form.get("rtsp_password") or "").strip() or None

        cfg.onvif_host = (request.form.get("onvif_host") or "").strip() or None
        cfg.onvif_port = int(request.form.get("onvif_port") or 80)
        cfg.onvif_username = (request.form.get("onvif_username") or "").strip() or None
        cfg.onvif_password = (request.form.get("onvif_password") or "").strip() or None

        db.session.commit()
        with state_lock:
            global camera_source_mode
            camera_source_mode = "ptz" if (cfg.camera_type == "ptz") else "fixed"
            current_detection_state["camera_source_mode"] = camera_source_mode
        flash("Configuración de cámara guardada.", "success")
        return redirect(url_for("admin_camera"))

    return render_template("admin_camera.html", cfg=cfg)


@app.route("/admin/camera/test", methods=["POST"])
@login_required
@role_required("admin")
def admin_camera_test():
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
    # Override sólo para Administrador (Operador no puede cambiar tipo de cámara).
    if current_user.role == "admin":
        source = (request.args.get("source") or "").strip().lower()
        if source in {"fixed", "ptz"}:
            global camera_source_mode
            with state_lock:
                camera_source_mode = source
                current_detection_state["camera_source_mode"] = camera_source_mode
    return Response(process_rtsp_stream(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/set_camera_source", methods=["POST"])
@login_required
def set_camera_source():
    if current_user.role != "admin":
        return jsonify({"success": False, "error": "Acceso denegado."}), 403
    payload = request.get_json(silent=True) or request.form or {}
    source = str(payload.get("source", "")).strip().lower()
    if source not in {"fixed", "ptz"}:
        return jsonify({"success": False, "error": "Modo inválido. Usa 'fixed' o 'ptz'."}), 400

    global camera_source_mode
    with state_lock:
        camera_source_mode = source
        current_detection_state["camera_source_mode"] = camera_source_mode
    return jsonify({"success": True, "camera_source_mode": camera_source_mode})


@app.route("/detection_status")
@login_required
def detection_status():
    with state_lock:
        return jsonify(dict(current_detection_state))


@app.route("/video_progress")
@login_required
def video_progress():
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


@app.route("/progress/<job_id>")
@login_required
def progress(job_id: str):
    with job_lock:
        p = progress_by_job.get(job_id)
        r = result_by_job.get(job_id)
    if not p:
        return jsonify({"success": False, "error": "Job no encontrado"}), 404
    payload = dict(p)
    if r:
        payload.update(r)
    return jsonify(payload)


@app.route("/progress_stream/<job_id>")
@login_required
def progress_stream(job_id: str):
    def gen():
        last = None
        while True:
            with job_lock:
                p = progress_by_job.get(job_id)
                r = result_by_job.get(job_id)
            if not p:
                yield f"data: {json.dumps({'success': False, 'error': 'Job no encontrado'})}\n\n"
                break
            payload = dict(p)
            if r:
                payload.update(r)
            msg = json.dumps(payload)
            if msg != last:
                yield f"data: {msg}\n\n"
                last = msg
            if p.get("done"):
                break
            time.sleep(0.25)

    return Response(
        gen(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ======================== UPLOAD DETECT (persist results) ========================
@app.route("/upload_detect", methods=["POST"])
@login_required
def upload_detect():
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
    with job_lock:
        if job_id not in progress_by_job:
            progress_by_job[job_id] = {"success": True, "job_id": job_id}
        progress_by_job[job_id]["progress"] = int(max(0, min(100, progress)))
        if status is not None:
            progress_by_job[job_id]["status"] = status
        if done is not None:
            progress_by_job[job_id]["done"] = bool(done)


def _set_job_result(job_id: str, payload: dict):
    with job_lock:
        result_by_job[job_id] = payload


def _run_detection_job(job_id: str, temp_path: str, ext: str):
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
    with state_lock:
        camera_source_mode = "ptz" if (cfg.camera_type == "ptz") else "fixed"
        current_detection_state["camera_source_mode"] = camera_source_mode


if __name__ == "__main__":
    print(f"[INFO] Servidor: http://localhost:{FLASK_CONFIG['port']}")
    app.run(
        debug=FLASK_CONFIG["debug"],
        use_reloader=bool(FLASK_CONFIG.get("debug")),
        host=FLASK_CONFIG["host"],
        port=FLASK_CONFIG["port"],
        threaded=bool(FLASK_CONFIG.get("threaded", True)),
    )
