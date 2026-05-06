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
    Vector de centrado PTZ (pan/tilt) basado en offset del bbox.
    """
    dx, dy = bbox_offset_norm(frame_w, frame_h, bbox_xyxy)
    tol = float(clamp(float(tolerance_frac), 0.01, 0.90))

    def _map(d: float) -> float:
        ad = abs(float(d))
        if ad <= tol:
            return 0.0
        scaled = (ad - tol) / max(1e-6, 1.0 - tol)
        return float(clamp(scaled, 0.0, 1.0))

    x_mag = _map(dx)
    y_mag = _map(dy)

    x = x_mag * (1.0 if dx >= 0 else -1.0)
    y = y_mag * (1.0 if dy >= 0 else -1.0)

    x = float(clamp(x * float(max_speed), -float(max_speed), float(max_speed)))
    y = float(clamp(y * float(max_speed), -float(max_speed), float(max_speed)))
    return x, y


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

                if not self._current_url:
                    time.sleep(0.5)
                    continue

                if cap is None or not cap.isOpened():
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
                        time.sleep(1.0)
                        continue

                ret, frame = cap.read()
                if not ret or frame is None:
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
                if (
                    str(self.get_camera_mode()) == "ptz"
                    and bool(self.is_tracking_enabled())
                    and bool(confirmed)
                    and bool(self.is_camera_configured_ptz())
                    and self.ptz_move is not None
                ):
                    priority = select_priority_detection(detection_list)
                    if priority is not None:
                        h, w = frame.shape[:2]
                        try:
                            tolerance_frac = float(os.environ.get("PTZ_CENTER_TOLERANCE_FRAC", "0.15"))
                        except Exception:
                            tolerance_frac = 0.20
                        x, y = ptz_centering_vector(
                            int(w),
                            int(h),
                            tuple(priority["bbox"]),
                            tolerance_frac=tolerance_frac,
                            max_speed=0.60,
                        )

                        if not hasattr(self, "_last_ptz_cmd"):
                            self._last_ptz_cmd = (0.0, 0.0)
                        lx, ly = getattr(self, "_last_ptz_cmd")
                        alpha = 0.55
                        sx = (alpha * float(x)) + ((1.0 - alpha) * float(lx))
                        sy = (alpha * float(y)) + ((1.0 - alpha) * float(ly))
                        self._last_ptz_cmd = (sx, sy)

                        if abs(sx) > 0.001 or abs(sy) > 0.001:
                            self.ptz_move(
                                x=float(clamp(sx, -0.60, 0.60)),
                                y=float(clamp(sy, -0.60, 0.60)),
                                zoom=0.0,
                                duration_s=0.12,
                            )
                        else:
                            if self.ptz_stop is not None and (abs(lx) > 0.02 or abs(ly) > 0.02):
                                self.ptz_stop()
            except Exception:
                pass

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
