"""
src/video_processor.py
======================
Procesamiento de flujo de video: lectura RTSP, ejecuciÃ³n del modelo de visiÃ³n,
persistencia por frames, telemetrÃ­a y publicaciÃ³n MJPEG.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional

import cv2
import numpy as np

from src.system_core import clamp, select_priority_detection

try:
    import torch
except Exception:  # pragma: no cover
    torch = None


def draw_detections(
    frame: np.ndarray,
    results: Any,
    *,
    label: str = "RPAS Micro",
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """Dibuja bounding boxes y retorna una lista normalizada de detecciones."""
    detection_list: list[dict[str, Any]] = []
    for result in results:
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            continue
        for box in boxes:
            xyxy = box.xyxy[0].cpu().numpy().astype(int)
            x1, y1, x2, y2 = map(int, xyxy)
            conf = float(box.conf[0].cpu().numpy())
            color = (0, 255, 0)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            label_txt = f"{label} {conf:.0%}"
            label_size, _ = cv2.getTextSize(label_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(frame, (x1, max(0, y1 - 25)), (x1 + label_size[0], y1), color, -1)
            cv2.putText(
                frame,
                label_txt,
                (x1, max(15, y1 - 7)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 0, 0),
                2,
            )
            detection_list.append(
                {"class_name": label, "confidence": conf, "bbox": (x1, y1, x2, y2)}
            )
    return frame, detection_list


def overlay_fps(frame: np.ndarray, detection_times_s: list[float]) -> None:
    """Anota FPS estimado sobre el frame (in-place)."""
    if not detection_times_s:
        return
    avg = float(np.mean(detection_times_s))
    fps = (1.0 / avg) if avg > 0 else 0.0
    cv2.putText(
        frame,
        f"FPS: {fps:.1f}",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0),
        2,
    )


def bbox_iou_xyxy(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    """Calcula IoU para bboxes en formato (x1, y1, x2, y2)."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b

    ix1 = max(int(ax1), int(bx1))
    iy1 = max(int(ay1), int(by1))
    ix2 = min(int(ax2), int(bx2))
    iy2 = min(int(ay2), int(by2))

    iw = max(0, ix2 - ix1)
    ih = max(0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0

    a_area = max(0, int(ax2) - int(ax1)) * max(0, int(ay2) - int(ay1))
    b_area = max(0, int(bx2) - int(bx1)) * max(0, int(by2) - int(by1))
    union = a_area + b_area - inter
    return float(inter / union) if union > 0 else 0.0


def dedupe_overlapping_detections(
    detections: list[dict[str, Any]],
    *,
    iou_threshold: float,
) -> list[dict[str, Any]]:
    """
    Reduce cajas redundantes dentro de un mismo frame usando IoU.

    Mantiene la detecciÃ³n con mayor confianza cuando hay solapamiento alto.
    """
    if not detections:
        return []

    thr = float(clamp(float(iou_threshold), 0.10, 0.90))
    ordered = sorted(detections, key=lambda d: float(d.get("confidence", 0.0)), reverse=True)

    kept: list[dict[str, Any]] = []
    for det in ordered:
        bbox = det.get("bbox")
        if not bbox:
            continue
        bb = tuple(bbox)
        if any(bbox_iou_xyxy(bb, tuple(k["bbox"])) >= thr for k in kept):
            continue
        kept.append(det)
    return kept


def bbox_offset_norm(frame_w: int, frame_h: int, bbox_xyxy: tuple[int, int, int, int]) -> tuple[float, float]:
    """Offset del centro del bbox respecto al centro del frame, normalizado a [-1..1]."""
    x1, y1, x2, y2 = bbox_xyxy
    cx = (float(x1) + float(x2)) / 2.0
    cy = (float(y1) + float(y2)) / 2.0
    dx = (cx - (float(frame_w) / 2.0)) / max(1.0, float(frame_w) / 2.0)
    dy = (cy - (float(frame_h) / 2.0)) / max(1.0, float(frame_h) / 2.0)
    return float(dx), float(dy)


def ptz_centering_vector(
    frame_w: int,
    frame_h: int,
    bbox_xyxy: tuple[int, int, int, int],
    *,
    tolerance_frac: float = 0.15,
    max_speed: float = 0.60,
) -> tuple[float, float]:
    """
    Tracking PTZ simple por zonas (estable):
    - Centro del bbox vs centro del frame.
    - Deadzone configurable por `tolerance_frac` del frame por eje.
    - Fuera => velocidad constante en magnitud `max_speed`.
    - Respeta PTZ_INVERT_PAN / PTZ_INVERT_TILT.
    """
    fw = max(1, int(frame_w))
    fh = max(1, int(frame_h))
    x1, y1, x2, y2 = bbox_xyxy

    cx = (float(x1) + float(x2)) / 2.0
    cy = (float(y1) + float(y2)) / 2.0
    fx = float(fw) / 2.0
    fy = float(fh) / 2.0

    tol = float(clamp(float(tolerance_frac), 0.01, 0.90))
    deadzone_x = float(fw) * float(tol)
    deadzone_y = float(fh) * float(tol)

    spd = float(abs(float(max_speed)))

    pan = 0.0
    if cx < (fx - deadzone_x):
        pan = -float(spd)
    elif cx > (fx + deadzone_x):
        pan = float(spd)

    tilt = 0.0
    if cy < (fy - deadzone_y):
        tilt = float(spd)
    elif cy > (fy + deadzone_y):
        tilt = -float(spd)

    if os.environ.get("PTZ_INVERT_PAN", "").strip().lower() in {"1", "true", "t", "yes", "y", "on"}:
        pan = -1.0 * float(pan)
    if os.environ.get("PTZ_INVERT_TILT", "").strip().lower() in {"1", "true", "t", "yes", "y", "on"}:
        tilt = -1.0 * float(tilt)

    return float(pan), float(tilt)


def _apply_min_ptz_speed(value: float, min_speed: float = 0.08, max_speed: float = 0.25) -> float:
    if abs(float(value)) < 1e-6:
        return 0.0
    sign = 1.0 if float(value) > 0 else -1.0
    return float(sign) * float(min(max(abs(float(value)), float(min_speed)), float(max_speed)))


class RTSPLatestFrameReader:
    """Lee RTSP en un hilo y conserva sÃ³lo el Ãºltimo frame (drop de frames si hay lag)."""

    def __init__(
        self,
        *,
        get_rtsp_url: Callable[[], Optional[str]],
        video_config: dict[str, Any],
        rtsp_config: dict[str, Any],
    ) -> None:
        self._get_rtsp_url = get_rtsp_url
        self._video_config = dict(video_config)
        self._rtsp_config = dict(rtsp_config)

        self._lock = threading.Lock()
        self._frame: Optional[np.ndarray] = None
        self._ts: Optional[float] = None
        self._last_frame_at: Optional[float] = None
        self._reconnect_count = 0
        self._last_error: Optional[str] = None
        self._is_connected = False
        self._last_reconnect_log_at = 0.0
        self._last_timeout_log_at = 0.0

        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._current_url: Optional[str] = None

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self, *, timeout_s: float = 5.0) -> None:
        self._stop.set()
        self._thread.join(timeout=float(timeout_s))

    def get_latest(self) -> tuple[Optional[np.ndarray], Optional[float]]:
        with self._lock:
            return self._frame, self._ts

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            now = time.time()
            last_frame_at = self._last_frame_at
            age_s = None if last_frame_at is None else float(now - float(last_frame_at))
            return {
                "is_connected": bool(self._is_connected),
                "current_url": str(self._current_url or ""),
                "last_frame_at": last_frame_at,
                "last_frame_age_s": age_s,
                "reconnect_count": int(self._reconnect_count),
                "last_error": (str(self._last_error) if self._last_error else None),
            }

    def _run(self) -> None:
        cap: cv2.VideoCapture | None = None
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
                        with self._lock:
                            self._is_connected = False

                if not self._current_url:
                    time.sleep(0.5)
                    continue

                if cap is None or not cap.isOpened():
                    with self._lock:
                        self._reconnect_count += 1
                        self._last_error = None
                        self._is_connected = False
                    now = time.time()
                    if (now - float(self._last_reconnect_log_at)) >= 2.0:
                        print("[RTSP] reconnecting...")
                        self._last_reconnect_log_at = now
                    src: Any = self._current_url
                    if isinstance(src, str) and src.strip().isdigit():
                        try:
                            src = int(src.strip())
                        except Exception:
                            src = self._current_url
                    cap = cv2.VideoCapture(src)
                    if cap.isOpened():
                        timeout_ms = int(float(self._rtsp_config.get("timeout", 10)) * 1000.0)
                        try:
                            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms)
                        except Exception:
                            pass
                        try:
                            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_ms)
                        except Exception:
                            pass
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(self._video_config.get("width", 1280)))
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(self._video_config.get("height", 720)))
                        cap.set(cv2.CAP_PROP_FPS, int(self._video_config.get("fps", 30)))
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, int(self._rtsp_config.get("buffer_size", 1)))
                    else:
                        with self._lock:
                            self._last_error = "open failed"
                        time.sleep(1.0)
                        continue

                ret, frame = cap.read()
                if not ret or frame is None:
                    with self._lock:
                        self._last_error = "no frame/timeout"
                        self._is_connected = False
                    now = time.time()
                    if (now - float(self._last_timeout_log_at)) >= 2.5:
                        print("[RTSP] timeout/no frame")
                        self._last_timeout_log_at = now
                    try:
                        cap.release()
                    except Exception:
                        pass
                    cap = None
                    time.sleep(0.5)
                    continue

                ts = time.time()
                was_connected = False
                with self._lock:
                    self._frame = frame
                    self._ts = ts
                    self._last_frame_at = ts
                    was_connected = bool(self._is_connected)
                    self._is_connected = True
                    self._last_error = None
                if not was_connected:
                    print("[RTSP] connected")
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass
            with self._lock:
                self._is_connected = False


class DetectionPersistence:
    """Confirma detecciÃ³n tras N frames consecutivos con detecciones."""

    def __init__(self, required_consecutive_frames: int) -> None:
        self.required_consecutive_frames = max(1, int(required_consecutive_frames))
        self._consecutive_hits = 0

    def update(self, has_detection: bool) -> tuple[bool, int]:
        if has_detection:
            self._consecutive_hits += 1
        else:
            self._consecutive_hits = 0
        confirmed = self._consecutive_hits >= self.required_consecutive_frames
        return confirmed, self._consecutive_hits

    def set_required_consecutive_frames(self, required_consecutive_frames: int) -> None:
        self.required_consecutive_frames = max(1, int(required_consecutive_frames))
        self._consecutive_hits = 0


@dataclass(slots=True)
class LiveStreamDeps:
    video_config: dict[str, Any]
    yolo_config: dict[str, Any]
    detections_folder_rel: str
    app_root_path: str
    jpeg_placeholder_text: str = "Conectando a RTSP..."


class LiveVideoProcessor:
    """
    Pipeline live:
    - consume frames
    - ejecuta modelo de visiÃ³n por intervalos
    - confirma por persistencia
    - publica Ãºltimo JPEG para MJPEG
    """

    def __init__(
        self,
        *,
        reader: RTSPLatestFrameReader,
        model: Any,
        deps: LiveStreamDeps,
        get_model_params: Callable[[], dict[str, Any]],
        metrics_enqueue: Optional[Callable[[Any], None]] = None,
        make_frame_record: Optional[Callable[..., Any]] = None,
        get_camera_mode: Optional[Callable[[], str]] = None,
        is_tracking_enabled: Optional[Callable[[], bool]] = None,
        is_camera_configured_ptz: Optional[Callable[[], bool]] = None,
        ptz_move: Optional[Callable[..., None]] = None,
        ptz_stop: Optional[Callable[[], None]] = None,
        state_lock: Optional[threading.Lock] = None,
        detection_state: Optional[dict[str, Any]] = None,
        ui_persistence_frames: int = 3,
    ) -> None:
        self.reader = reader
        self.model = model
        self.deps = deps
        self.get_model_params = get_model_params

        self.metrics_enqueue = metrics_enqueue
        self.make_frame_record = make_frame_record

        self.get_camera_mode = get_camera_mode or (lambda: "unknown")
        self.is_tracking_enabled = is_tracking_enabled or (lambda: False)
        self.is_camera_configured_ptz = is_camera_configured_ptz or (lambda: False)
        self.ptz_move = ptz_move
        self.ptz_stop = ptz_stop

        self.state_lock = state_lock
        self.detection_state = detection_state
        self.ui_persistence_frames = max(1, int(ui_persistence_frames))

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._stop = threading.Event()
        self._last_ts: Optional[float] = None
        self._frame_count = 0
        self._detection_times: list[float] = []
        self._persistence = DetectionPersistence(int(self.get_model_params().get("persistence_frames", 3)))
        self._last_tracking_cmd_at = 0.0
        self._last_tracking_cmd = (0.0, 0.0)
        self._ptz_auto_was_moving = False
        self._last_tracking_error_log_at = 0.0

        self._evidence_saved_for_active_detection = False
        self._last_evidence_saved_at = 0.0

        self._stream_lock = threading.Lock()
        self._latest_jpeg: Optional[bytes] = None
        self._latest_ts: Optional[float] = None

        self._started = False

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()
        self._started = True

    def stop(self, *, timeout_s: float = 5.0) -> None:
        self._stop.set()
        self._thread.join(timeout=float(timeout_s))

    def ensure_started(self) -> None:
        if not self._started:
            self.reader.start()
            self.start()

    def get_latest(self) -> tuple[Optional[bytes], Optional[float]]:
        with self._stream_lock:
            return self._latest_jpeg, self._latest_ts

    def mjpeg_generator(self) -> Any:
        self.ensure_started()

        h = int(self.deps.video_config.get("height", 720))
        w = int(self.deps.video_config.get("width", 1280))
        placeholder = np.zeros((h, w, 3), dtype=np.uint8)
        cv2.putText(
            placeholder,
            str(self.deps.jpeg_placeholder_text),
            (30, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 255, 255),
            2,
        )
        _, ph_buf = cv2.imencode(".jpg", placeholder, [cv2.IMWRITE_JPEG_QUALITY, 80])
        ph_bytes = ph_buf.tobytes()

        last_sent_ts: Optional[float] = None
        while True:
            jpeg, ts = self.get_latest()
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
                b"Content-Length: "
                + str(len(frame_bytes)).encode()
                + b"\r\n\r\n"
                + frame_bytes
                + b"\r\n"
            )

    def _save_evidence(self, frame: np.ndarray, detection_list: list[dict[str, Any]]) -> None:
        now = time.time()
        if self._evidence_saved_for_active_detection:
            return
        if (now - float(self._last_evidence_saved_at)) < 1.0:
            return

        rel_folder = self.deps.detections_folder_rel.replace("\\", "/")
        abs_folder = os.path.join(self.deps.app_root_path, rel_folder)
        os.makedirs(abs_folder, exist_ok=True)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        fname = f"live_alert_{stamp}.jpg"
        rel_path = os.path.join(rel_folder, fname).replace("\\", "/")
        abs_path = os.path.join(self.deps.app_root_path, rel_path)

        ok = bool(cv2.imwrite(abs_path, frame))
        if not ok:
            return

        for det in detection_list:
            if isinstance(det, dict) and not det.get("image_path"):
                det["image_path"] = rel_path
        self._evidence_saved_for_active_detection = True
        self._last_evidence_saved_at = now

    def _update_ui_state(
        self,
        *,
        confirmed: bool,
        consecutive_hits: int,
        detection_list: list[dict[str, Any]],
    ) -> None:
        if self.state_lock is None or self.detection_state is None:
            return

        with self.state_lock:
            self.detection_state["camera_source_mode"] = str(self.get_camera_mode())
            self.detection_state["last_update"] = datetime.now().isoformat()

            if detection_list and confirmed:
                avg_conf = float(np.mean([float(d["confidence"]) for d in detection_list]))
                self.detection_state["status"] = "Alerta: Dron detectado"
                self.detection_state["avg_confidence"] = avg_conf
                self.detection_state["detected"] = True
                self.detection_state["detection_count"] = len(detection_list)
            elif detection_list and not confirmed:
                avg_conf = float(np.mean([float(d["confidence"]) for d in detection_list]))
                self.detection_state["status"] = (
                    f"Validando detecciÃ³n ({int(consecutive_hits)}/{int(self.ui_persistence_frames)})"
                )
                self.detection_state["avg_confidence"] = avg_conf
                self.detection_state["detected"] = False
                self.detection_state["detection_count"] = len(detection_list)
            else:
                self.detection_state["status"] = "Zona despejada"
                self.detection_state["avg_confidence"] = 0.0
                self.detection_state["detected"] = False
                self.detection_state["detection_count"] = 0

    def _run(self) -> None:
        while not self._stop.is_set():
            frame, ts = self.reader.get_latest()
            if frame is None or ts is None:
                time.sleep(0.02)
                continue
            if ts == self._last_ts:
                time.sleep(0.005)
                continue
            self._last_ts = ts

            target_w = int(self.deps.video_config.get("width", 1280))
            target_h = int(self.deps.video_config.get("height", 720))
            try:
                if frame.shape[1] != target_w or frame.shape[0] != target_h:
                    frame = cv2.resize(frame, (target_w, target_h))
            except cv2.error:
                time.sleep(0.01)
                continue
            except (AttributeError, TypeError):
                time.sleep(0.01)
                continue

            self._frame_count += 1

            detection_list: list[dict[str, Any]] = []
            inference_ms: float | None = None

            interval = int(self.deps.video_config.get("inference_interval", 1) or 1)
            if self.model is not None and (self._frame_count % max(1, interval) == 0):
                try:
                    params = dict(self.get_model_params() or {})
                    required = int(params.get("persistence_frames", 3))
                    if required != int(self._persistence.required_consecutive_frames):
                        self._persistence.set_required_consecutive_frames(required)

                    iou_value = float(params.get("iou_threshold", 0.45))
                    iou_value = float(clamp(iou_value, 0.45, 0.90))

                    t0 = time.time()
                    device_value = (
                        "cuda:0"
                        if torch is not None and bool(getattr(torch, "cuda", None)) and torch.cuda.is_available()
                        else "cpu"
                    )
                    results = self.model(
                        frame,
                        device=device_value,
                        conf=float(params.get("confidence_threshold", self.deps.yolo_config.get("confidence", 0.6))),
                        iou=float(iou_value),
                        augment=False,
                        verbose=bool(self.deps.yolo_config.get("verbose", False)),
                    )
                    dt = float(time.time() - t0)
                    inference_ms = float(dt * 1000.0)
                    self._detection_times.append(dt)
                    self._detection_times = self._detection_times[-30:]
                    frame, detection_list = draw_detections(frame, results)
                    detection_list = dedupe_overlapping_detections(detection_list, iou_threshold=float(iou_value))
                except cv2.error:
                    pass
                except RuntimeError:
                    pass
                except Exception:
                    cv2.putText(
                        frame,
                        "Error en inferencia",
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 0, 255),
                        2,
                    )

            confirmed, consecutive_hits = self._persistence.update(bool(detection_list))

            if detection_list and confirmed:
                try:
                    self._save_evidence(frame, detection_list)
                except Exception:
                    pass
            else:
                self._evidence_saved_for_active_detection = False

            if inference_ms is not None and self.metrics_enqueue and self.make_frame_record:
                try:
                    h, w = frame.shape[:2]
                except Exception:
                    h, w = 0, 0

                try:
                    record = self.make_frame_record(
                        timestamp_iso=datetime.fromtimestamp(float(ts)).isoformat(),
                        source="rtsp",
                        inference_ms=float(inference_ms),
                        frame_w=int(w),
                        frame_h=int(h),
                        detections=list(detection_list),
                        confirmed=bool(confirmed),
                        camera_mode=str(self.get_camera_mode()),
                    )
                    self.metrics_enqueue(record)
                except Exception:
                    pass

            # PTZ tracking (opcional)
            try:
                tracking_active = (
                    str(self.get_camera_mode()) == "ptz"
                    and bool(self.is_tracking_enabled())
                    and bool(confirmed)
                    and bool(self.is_camera_configured_ptz())
                    and self.ptz_move is not None
                )
                if not tracking_active:
                    if bool(self._ptz_auto_was_moving) and self.ptz_stop is not None:
                        self.ptz_stop()
                        print("[TRACKING_CMD]", "stop reason=tracking_inactive")
                    self._ptz_auto_was_moving = False
                if tracking_active:
                    priority = select_priority_detection(detection_list)
                    if priority is not None:
                        h, w = frame.shape[:2]
                        try:
                            deadzone_frac = float(os.environ.get("PTZ_TRACKING_DEADZONE_FRAC", "0.10"))
                        except Exception:
                            deadzone_frac = 0.10
                        deadzone_frac = float(clamp(deadzone_frac, 0.05, 0.25))

                        try:
                            duration_s = float(os.environ.get("PTZ_TRACKING_DURATION", "0.35"))
                        except Exception:
                            duration_s = 0.35
                        duration_s = float(clamp(duration_s, 0.10, 1.00))

                        try:
                            min_speed = float(os.environ.get("PTZ_TRACKING_MIN_SPEED", "0.12"))
                        except Exception:
                            min_speed = 0.12
                        min_speed = float(clamp(min_speed, 0.05, 0.30))

                        try:
                            max_speed_env = float(os.environ.get("PTZ_TRACKING_MAX_SPEED", "0.45"))
                        except Exception:
                            max_speed_env = 0.45
                        max_speed_env = float(clamp(max_speed_env, 0.10, 0.70))

                        try:
                            base_speed = float(os.environ.get("PTZ_TRACKING_SPEED", "0.35"))
                        except Exception:
                            base_speed = 0.35
                        base_speed = float(clamp(base_speed, 0.10, 0.70))
                        max_speed = float(min(float(base_speed), float(max_speed_env)))

                        try:
                            command_interval = float(os.environ.get("PTZ_TRACKING_COMMAND_INTERVAL", "0.35"))
                        except Exception:
                            command_interval = 0.35
                        command_interval = float(clamp(command_interval, 0.20, 1.00))

                        now = time.time()
                        if (now - float(self._last_tracking_cmd_at)) < float(command_interval):
                            continue

                        bbox = tuple(priority["bbox"])
                        dx, dy = bbox_offset_norm(int(w), int(h), bbox)

                        detected_flag = False
                        try:
                            if self.state_lock is not None and self.detection_state is not None:
                                with self.state_lock:
                                    detected_flag = bool(self.detection_state.get("detected", False))
                        except Exception:
                            detected_flag = False

                        if not detected_flag:
                            if bool(self._ptz_auto_was_moving) and self.ptz_stop is not None:
                                self.ptz_stop()
                                print("[TRACKING_CMD]", "stop reason=not_detected")
                            self._ptz_auto_was_moving = False
                            self._last_tracking_cmd_at = now
                            continue

                        x, y = ptz_centering_vector(
                            int(w),
                            int(h),
                            bbox,
                            tolerance_frac=float(deadzone_frac),
                            max_speed=float(max_speed),
                        )
                        pan_cmd = float(x)
                        tilt_cmd = float(y)

                        def _apply_min_max(v: float) -> float:
                            if abs(float(v)) < 1e-6:
                                return 0.0
                            sign = 1.0 if float(v) > 0 else -1.0
                            mag = float(min(max(abs(float(v)), float(min_speed)), float(max_speed)))
                            return float(sign) * float(mag)

                        pan_cmd = _apply_min_max(pan_cmd)
                        tilt_cmd = _apply_min_max(tilt_cmd)

                        if abs(float(pan_cmd)) < 1e-6 and abs(float(tilt_cmd)) < 1e-6:
                            if bool(self._ptz_auto_was_moving) and self.ptz_stop is not None:
                                self.ptz_stop()
                                print("[TRACKING_CMD]", "stop reason=centered")
                            self._ptz_auto_was_moving = False
                            self._last_tracking_cmd_at = now
                            continue

                        if (float(pan_cmd), float(tilt_cmd)) != tuple(self._last_tracking_cmd):
                            self.ptz_move(
                                x=float(clamp(pan_cmd, -float(max_speed_env), float(max_speed_env))),
                                y=float(clamp(tilt_cmd, -float(max_speed_env), float(max_speed_env))),
                                zoom=0.0,
                                duration_s=float(duration_s),
                            )
                            self._last_tracking_cmd = (float(pan_cmd), float(tilt_cmd))
                            self._ptz_auto_was_moving = True
                            self._last_tracking_cmd_at = now
                            print(
                                "[TRACKING_CMD]",
                                f"bbox={bbox} err=({float(dx):.3f},{float(dy):.3f}) pan_cmd={float(pan_cmd):.3f} "
                                f"tilt_cmd={float(tilt_cmd):.3f} duration={float(duration_s):.2f} interval={float(command_interval):.2f}",
                            )
                        else:
                            # Mismo comando: actualizar timestamp para mantener rate limit y no saturar.
                            self._last_tracking_cmd_at = now
            except Exception as e:
                now = time.time()
                if (now - float(self._last_tracking_error_log_at)) > 2.0:
                    print(f"[TRACKING][ERROR] {e}")
                    self._last_tracking_error_log_at = now

            self._update_ui_state(confirmed=confirmed, consecutive_hits=consecutive_hits, detection_list=detection_list)

            overlay_fps(frame, self._detection_times)

            ok, buf = cv2.imencode(
                ".jpg",
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, int(self.deps.video_config.get("jpeg_quality", 80))],
            )
            if ok:
                with self._stream_lock:
                    self._latest_jpeg = buf.tobytes()
                    self._latest_ts = ts
