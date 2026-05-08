from __future__ import annotations

import base64
import heapq
import os
import secrets
import threading
import time
from datetime import datetime
from typing import Any

import cv2  # type: ignore
import numpy as np  # type: ignore
from flask import Blueprint, jsonify, request
from flask_login import login_required
from werkzeug.utils import secure_filename

from src.services.video_export_service import create_video_writer, make_browser_compatible_mp4
from src.system_core import FrameRecord
from src.video_processor import draw_detections

analysis_bp = Blueprint("analysis", __name__)

_deps: dict[str, Any] = {}
_routes_initialized = False

# Helper para errores claros cuando falten dependencias inyectadas.
def _get_dep(key: str):
    try:
        return _deps[key]
    except KeyError as exc:
        raise RuntimeError(f"Dependencia faltante en analysis: {key}") from exc

# Estado de jobs de inferencia manual (solo usado por /upload_detect y /video_progress).
job_lock = threading.Lock()
progress_by_job: dict[str, dict] = {}
result_by_job: dict[str, dict] = {}


def init_analysis_routes(**deps: Any) -> None:
    """
    Inicializa dependencias y registra las rutas en el Blueprint.

    Evita imports circulares con `app.py` al recibir referencias explícitas.
    """
    global _deps, _routes_initialized
    _deps = dict(deps or {})

    if _routes_initialized:
        return
    _routes_initialized = True

    role_required = _get_dep("role_required")

    @analysis_bp.route("/video_progress")
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
    @analysis_bp.route("/upload_detect", methods=["POST"])
    @login_required
    @role_required("operator")
    def upload_detect():
        """Encola una detección manual (imagen/video) y retorna `job_id`."""
        try:
            if "file" not in request.files:
                return (
                    jsonify(
                        {"success": False, "status": "error", "message": "No se subió archivo", "error": "No se subió archivo"}
                    ),
                    400,
                )
            f = request.files["file"]
            if not f or not f.filename:
                return (
                    jsonify(
                        {"success": False, "status": "error", "message": "Archivo sin nombre", "error": "Archivo sin nombre"}
                    ),
                    400,
                )
            if not _get_dep("allowed_file")(f.filename):
                return (
                    jsonify(
                        {
                            "success": False,
                            "status": "error",
                            "message": "Extensión no permitida",
                            "error": "Extensión no permitida",
                        }
                    ),
                    400,
                )
            if _get_dep("yolo_model") is None:
                return (
                    jsonify(
                        {
                            "success": False,
                            "status": "error",
                            "message": "Modelo YOLO no disponible",
                            "error": "Modelo YOLO no disponible",
                        }
                    ),
                    500,
                )

            filename = secure_filename(f.filename)
            ts = int(time.time())
            job_id = secrets.token_urlsafe(10)
            temp_name = f"{ts}_{job_id}_{filename}"
            os.makedirs(_get_dep("app").config["UPLOAD_FOLDER"], exist_ok=True)
            temp_path = os.path.join(_get_dep("app").config["UPLOAD_FOLDER"], temp_name)
            f.save(temp_path)

            ext = filename.rsplit(".", 1)[1].lower()
            analysis_root = None
            clean_dir = None
            bb_dir = None
            if ext in {"mp4", "avi", "mov"}:
                stem = os.path.splitext(filename)[0].strip() or "video"
                ts_folder = datetime.now().strftime("%Y%m%d_%H%M")
                folder_base = f"{stem}_{ts_folder}"
                analysis_root = os.path.join(_get_dep("app").config["DATASET_RECOLECCION_FOLDER"], folder_base)
                if os.path.exists(analysis_root):
                    analysis_root = os.path.join(_get_dep("app").config["DATASET_RECOLECCION_FOLDER"], f"{folder_base}_{job_id[:6]}")
                clean_dir = os.path.join(analysis_root, "limpias")
                bb_dir = os.path.join(analysis_root, "con_bounding_box")
                os.makedirs(clean_dir, exist_ok=True)
                os.makedirs(bb_dir, exist_ok=True)

            with job_lock:
                progress_by_job[job_id] = {"success": True, "job_id": job_id, "progress": 0, "status": "queued", "done": False}
            threading.Thread(
                target=_run_detection_job, args=(job_id, temp_path, ext, filename, clean_dir, bb_dir), daemon=True
            ).start()
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

    params = _get_dep("get_model_params")()
    t0 = time.time()
    results = _get_dep("yolo_model")(
        image,
        device=_get_dep("YOLO_CONFIG")["device"],
        conf=float(params.get("confidence_threshold", _get_dep("YOLO_CONFIG")["confidence"])),
        iou=float(params.get("iou_threshold", 0.45)),
        verbose=_get_dep("YOLO_CONFIG")["verbose"],
    )
    inference_ms = float((time.time() - t0) * 1000.0)
    image, detection_list = draw_detections(image, results)

    out_name = f"result_{job_id}.jpg"
    out_path = os.path.join(_get_dep("app").config["RESULTS_FOLDER"], out_name)
    cv2.imwrite(out_path, image)

    avg_conf = float(np.mean([d["confidence"] for d in detection_list])) if detection_list else 0.0

    # Telemetría (persistencia en detections_v2/inference_frames)
    try:
        h, w = image.shape[:2]
        with _get_dep("state_lock"):
            cam_mode = str(_get_dep("get_camera_source_mode")())
        _get_dep("metrics_writer").enqueue(
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


def _persist_top_detections_images(clean_dir: str, bb_dir: str, top_items: list[tuple[float, int, bytes, bytes]]) -> list[dict]:
    """Guarda Top 10 en limpio + con bounding box y devuelve al frontend SOLO las imágenes con bounding box.

    - Archivo: `conf_98_5_frame_145.jpg`
    - JSON: usa `image_base64` para renderizar en la galería/modal sin exponer el dataset por /static.
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

    fps = cap.get(cv2.CAP_PROP_FPS) or _get_dep("VIDEO_CONFIG")["fps"]
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or _get_dep("VIDEO_CONFIG")["width"]
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or _get_dep("VIDEO_CONFIG")["height"]
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    if width > 1280 or height > 720:
        scale = min(1280 / width, 720 / height)
        width = int(width * scale)
        height = int(height * scale)

    raw_name = f"result_{job_id}_raw.mp4"
    raw_path = os.path.join(_get_dep("app").config["RESULTS_FOLDER"], raw_name)
    browser_name = f"result_{job_id}_browser.mp4"
    browser_path = os.path.join(_get_dep("app").config["RESULTS_FOLDER"], browser_name)

    out, wrote_to, used = create_video_writer(raw_path, fps, width, height)
    print("[VIDEO_WRITER]", f"raw_path={wrote_to}")
    video_output_warning = None
    if out is None:
        video_output_warning = "No se pudo inicializar VideoWriter; se omitió el video de salida."

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

            params = _get_dep("get_model_params")()
            results = _get_dep("yolo_model")(
                frame,
                device=_get_dep("YOLO_CONFIG")["device"],
                conf=float(params.get("confidence_threshold", _get_dep("YOLO_CONFIG")["confidence"])),
                iou=float(params.get("iou_threshold", 0.45)),
                verbose=_get_dep("YOLO_CONFIG")["verbose"],
            )
            frame, detection_list = draw_detections(frame, results)

            total_detections += len(detection_list)
            if detection_list:
                total_conf += float(np.mean([d["confidence"] for d in detection_list]))
                best_conf = float(max(d["confidence"] for d in detection_list))
                bb_frame = frame
                ok_clean, clean_buf = cv2.imencode(".jpg", clean_frame, [cv2.IMWRITE_JPEG_QUALITY, _get_dep("VIDEO_CONFIG")["jpeg_quality"]])
                ok_bb, bb_buf = cv2.imencode(".jpg", bb_frame, [cv2.IMWRITE_JPEG_QUALITY, _get_dep("VIDEO_CONFIG")["jpeg_quality"]])
                if ok_clean and ok_bb:
                    frame_no = frame_count + 1
                    item = (best_conf, int(frame_no), clean_buf.tobytes(), bb_buf.tobytes())
                    if len(top_heap) < top_n:
                        heapq.heappush(top_heap, item)
                    elif best_conf > top_heap[0][0]:
                        heapq.heapreplace(top_heap, item)

            if out is not None:
                out.write(frame)
            frame_count += 1

            if iterator is not None:
                iterator.update(1)

            if total_frames > 0 and frame_count % 3 == 0:
                _set_job_progress(job_id, int((frame_count / total_frames) * 100), status="processing")
            elif total_frames <= 0 and frame_count % 15 == 0:
                approx = min(95, 5 + int(frame_count / max(1, int(_get_dep("VIDEO_CONFIG").get("fps", 30)))))
                _set_job_progress(job_id, approx, status="processing")
    finally:
        try:
            if iterator is not None:
                iterator.close()
        except Exception:
            pass
        cap.release()
        try:
            if out is not None:
                out.release()
        except Exception:
            pass

    # Validar salida de video (existencia/tamaño). Si no existe o pesa 0, no marcar como reproducible.
    result_video_path = wrote_to if (out is not None and wrote_to) else None
    result_video_size = 0
    if result_video_path:
        try:
            if os.path.exists(result_video_path):
                result_video_size = int(os.path.getsize(result_video_path) or 0)
        except Exception:
            result_video_size = 0

    print(f"[VIDEO_OUTPUT] raw_path={result_video_path} size={int(result_video_size)}")
    if result_video_path and int(result_video_size) <= 0:
        video_output_warning = "No se pudo generar un video reproducible de salida (archivo vacío)."
        result_video_path = None

    # Intentar SIEMPRE generar un MP4 compatible con navegador vía ffmpeg (aunque el raw sea .mp4 mp4v).
    final_video_path = None
    final_mime = None
    final_playable = False
    if result_video_path:
        ok = False
        reason = None
        try:
            ok, reason = make_browser_compatible_mp4(result_video_path, browser_path)
        except Exception:
            ok, reason = False, "exception"
        if ok and os.path.exists(browser_path) and int(os.path.getsize(browser_path) or 0) > 0 and str(browser_path).endswith("_browser.mp4"):
            final_video_path = browser_path
            final_mime = "video/mp4"
            final_playable = True
            try:
                sz = int(os.path.getsize(browser_path) or 0)
            except Exception:
                sz = 0
            print(f"[VIDEO_OUTPUT] browser_path={browser_path} size={int(sz)} playable=True")
        else:
            # Fallback: no tenemos mp4 browser-playable; permitir descarga del raw.
            final_video_path = result_video_path
            ext = os.path.splitext(str(final_video_path).lower())[1]
            final_mime = "video/mp4" if ext == ".mp4" else ("video/x-msvideo" if ext == ".avi" else "application/octet-stream")
            final_playable = False
            if not video_output_warning:
                if reason == "ffmpeg_missing":
                    video_output_warning = (
                        "FFmpeg no está instalado o no está en PATH. El video se generó, pero solo puede descargarse. "
                        "Instale FFmpeg o configure FFMPEG_BIN para verlo en el navegador."
                    )
                else:
                    video_output_warning = (
                        "El video fue generado, pero no se pudo convertir a un formato reproducible en navegador. Use Descargar."
                    )
            print("[VIDEO_OUTPUT][WARN] browser playable mp4 unavailable; download only")

    print(f"[VIDEO_OUTPUT] playable={bool(final_playable)} mime={final_mime}")

    avg_conf = (total_conf / max(1, frame_count)) if frame_count else 0.0
    top_items = sorted(top_heap, key=lambda x: x[0], reverse=True)

    if not clean_dir or not bb_dir:
        stem = os.path.splitext(original_filename or "")[0].strip() or "video"
        ts_folder = datetime.now().strftime("%Y%m%d_%H%M")
        folder_base = f"{stem}_{ts_folder}"
        analysis_root = os.path.join(_get_dep("app").config["DATASET_RECOLECCION_FOLDER"], folder_base)
        if os.path.exists(analysis_root):
            analysis_root = os.path.join(_get_dep("app").config["DATASET_RECOLECCION_FOLDER"], f"{folder_base}_{job_id[:6]}")
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
            # Compat legacy:
            "result_url": (("/" + os.path.relpath(final_video_path, _get_dep("app").root_path).replace("\\", "/")) if final_video_path else None),
            # Nuevo contrato (UI puede decidir si renderiza <video> o solo descarga)
            "result_video_url": (("/" + os.path.relpath(final_video_path, _get_dep("app").root_path).replace("\\", "/")) if final_video_path else None),
            "result_video_path": (os.path.relpath(final_video_path, _get_dep("app").root_path).replace("\\", "/") if final_video_path else None),
            "result_video_mime": final_mime,
            "result_video_playable": bool(final_playable),
            "result_video_raw_url": (("/" + os.path.relpath(result_video_path, _get_dep("app").root_path).replace("\\", "/")) if result_video_path else None),
            "result_video_browser_url": (("/" + os.path.relpath(browser_path, _get_dep("app").root_path).replace("\\", "/")) if os.path.exists(browser_path) else None),
            "video_output_warning": video_output_warning,
            "top_detections": top_detections,
            "frames_processed": frame_count,
            "total_detections": total_detections,
            "avg_confidence": float(avg_conf),
        },
    )
