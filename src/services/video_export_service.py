"""
Módulo      : video_export_service.py
Rol         : Exportación y transcodificación de video procesado por el pipeline
              de análisis manual. Abstrae la complejidad de codecs (cv2.VideoWriter
              con fallback de codecs) y la conversión a MP4 reproducible en
              navegador vía FFmpeg (libx264 → mpeg4 → descarga).
Conectado con: config.py (STORAGE_CONFIG['ffmpeg_bin']), cv2, subprocess,
              imageio_ffmpeg (opcional — resolución alternativa de FFmpeg).
Usado por   : src/routes/analysis.py (_process_video_and_persist — jobs manuales).
Hilos       : Los jobs de análisis corren en hilos separados (ver analysis.py);
              este módulo no mantiene estado propio.
Base de datos: No accede a ninguna DB.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess

import cv2

logger = logging.getLogger(__name__)

try:
    import imageio_ffmpeg  # type: ignore
except Exception:
    imageio_ffmpeg = None


def resolve_ffmpeg_bin() -> str | None:
    """
    Resuelve un ejecutable ffmpeg en este orden:
    1) env FFMPEG_BIN (si existe en disco)
    2) shutil.which("ffmpeg")
    3) imageio_ffmpeg.get_ffmpeg_exe() (si está instalado)
    """
    from config import STORAGE_CONFIG
    env_path = str(STORAGE_CONFIG.get("ffmpeg_bin", "")).strip()
    if env_path:
        try:
            if os.path.exists(env_path):
                logger.info("video_transcode using FFMPEG_BIN=%s", env_path)
                return env_path
        except Exception:
            pass

    try:
        p = shutil.which("ffmpeg")
        if p:
            logger.info("video_transcode using PATH ffmpeg=%s", p)
            return p
    except Exception:
        pass

    if imageio_ffmpeg is not None:
        try:
            p = imageio_ffmpeg.get_ffmpeg_exe()  # type: ignore[attr-defined]
            if p and os.path.exists(p):
                logger.info("video_transcode using imageio_ffmpeg=%s", p)
                return str(p)
        except Exception as e:
            logger.warning("video_transcode imageio_ffmpeg unavailable: %s", str(e) or e.__class__.__name__)

    logger.error("ffmpeg no encontrado. Instale FFmpeg, configure FFMPEG_BIN o instale imageio-ffmpeg.")
    return None


def create_video_writer(output_path: str, fps: float, width: int, height: int):
    """
    Abre un ``cv2.VideoWriter`` probando codecs en orden: mp4v → XVID → MJPG.

    La secuencia de fallback existe porque no todos los entornos tienen los
    codecs instalados; XVID/MJPG son más compatibles en sistemas sin libx264.

    Args:
        output_path: Ruta de salida preferida (p.ej. ``result_abc.mp4``).
        fps: Fotogramas por segundo del video de salida.
        width: Ancho en píxeles.
        height: Alto en píxeles.

    Returns:
        Tupla ``(writer, path_efectivo, codec_usado)`` si se pudo abrir el
        writer, o ``(None, None, None)`` si todos los codecs fallaron.
    """
    candidates = [
        ("mp4v", output_path),
        ("XVID", output_path.replace(".mp4", ".avi")),
        ("MJPG", output_path.replace(".mp4", ".avi")),
    ]

    tried = []
    for codec, path in candidates:
        tried.append(codec)
        try:
            fourcc = cv2.VideoWriter_fourcc(*codec)
            out = cv2.VideoWriter(path, fourcc, float(fps), (int(width), int(height)))
            opened = bool(out is not None and out.isOpened())
            logger.debug("video_writer codec=%s opened=%s path=%s", codec, bool(opened), path)
            if opened:
                return out, path, codec
            try:
                out.release()
            except Exception:
                pass
            if codec != candidates[-1][0]:
                logger.warning("video_writer codec=%s falló, intentando siguiente codec", codec)
        except Exception as e:
            if codec != candidates[-1][0]:
                logger.warning("video_writer codec=%s falló (%s), intentando siguiente codec", codec, str(e) or e.__class__.__name__)
            continue

    logger.error("video_writer no se pudo inicializar ningún codec")
    return None, None, None


def transcode_to_browser_mp4(input_path: str, output_path: str) -> tuple[bool, str | None]:
    """
    Transcodifica ``input_path`` a un MP4 reproducible en navegador (H.264/yuv420p).

    Intenta ``libx264`` primero (mayor compatibilidad con Chrome/Edge/Safari);
    si falla, prueba ``mpeg4`` como fallback. El flag ``+faststart`` mueve
    los metadatos al inicio del archivo para permitir streaming progresivo.

    Args:
        input_path: Ruta del video raw generado por ``create_video_writer``.
        output_path: Ruta de destino para el MP4 final.

    Returns:
        Tupla ``(ok, reason)`` donde ``ok`` es True si la transcodificación
        produjo un archivo válido, y ``reason`` es None (éxito),
        ``"ffmpeg_missing"`` o ``"transcode_failed"`` (fallo).
    """
    in_path = str(input_path)
    out_path = str(output_path)

    logger.info("video_transcode input=%s output=%s", in_path, out_path)

    ffmpeg_bin = resolve_ffmpeg_bin()

    if not ffmpeg_bin:
        logger.warning("video_transcode success=False reason=ffmpeg_missing")
        return False, "ffmpeg_missing"

    for vcodec in ("libx264", "mpeg4"):
        try:
            cmd = [
                ffmpeg_bin,
                "-y",
                "-i",
                in_path,
                "-vcodec",
                vcodec,
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-an",
                out_path,
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            ok = bool(os.path.exists(out_path) and int(os.path.getsize(out_path) or 0) > 0)
            logger.info("video_transcode success=%s codec=%s output=%s", bool(ok), vcodec, out_path)
            return bool(ok), (None if ok else "transcode_failed")
        except Exception as e:
            logger.warning("video_transcode codec=%s failed: %s", vcodec, str(e) or e.__class__.__name__)
            continue

    logger.warning("video_transcode success=False")
    return False, "transcode_failed"


def make_browser_compatible_mp4(input_path: str, output_path: str) -> tuple[bool, str | None]:
    """Wrapper semántico: genera un MP4 final compatible con navegador."""
    try:
        return transcode_to_browser_mp4(input_path, output_path)
    except Exception as e:
        logger.error("video_transcode error: %s", str(e) or e.__class__.__name__)
        return False, "exception"

