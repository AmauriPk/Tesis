"""
Servicio de exportación/conversión de video procesado.

Responsabilidades:
- Inicializar cv2.VideoWriter con fallback de codecs.
- Resolver el ejecutable FFmpeg disponible en el entorno.
- Transcodificar un video raw a MP4 compatible con navegador.
- Validar que un archivo de video de salida exista y tenga contenido.

No depende de variables globales de app.py ni de Flask.
"""
from __future__ import annotations

import os
import shutil
import subprocess

import cv2

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
    env_path = (os.environ.get("FFMPEG_BIN") or "").strip()
    if env_path:
        try:
            if os.path.exists(env_path):
                print(f"[VIDEO_TRANSCODE] using FFMPEG_BIN={env_path}")
                return env_path
        except Exception:
            pass

    try:
        p = shutil.which("ffmpeg")
        if p:
            print(f"[VIDEO_TRANSCODE] using PATH ffmpeg={p}")
            return p
    except Exception:
        pass

    if imageio_ffmpeg is not None:
        try:
            p = imageio_ffmpeg.get_ffmpeg_exe()  # type: ignore[attr-defined]
            if p and os.path.exists(p):
                print(f"[VIDEO_TRANSCODE] using imageio_ffmpeg={p}")
                return str(p)
        except Exception as e:
            print(f"[VIDEO_TRANSCODE][WARN] imageio_ffmpeg unavailable err={str(e) or e.__class__.__name__}")

    print("[VIDEO_TRANSCODE][ERROR] ffmpeg no encontrado. Instale FFmpeg, configure FFMPEG_BIN o instale imageio-ffmpeg.")
    return None


def create_video_writer(output_path: str, fps: float, width: int, height: int):
    """
    Intenta abrir un cv2.VideoWriter con fallback de codecs.

    Devuelve (writer, path_efectivo, codec_usado) o (None, None, None) si falla todo.
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
            print("[VIDEO_WRITER]", f"codec={codec} opened={bool(opened)} path={path}")
            if opened:
                return out, path, codec
            try:
                out.release()
            except Exception:
                pass
            if codec != candidates[-1][0]:
                print("[VIDEO_WRITER][WARN]", f"{codec} falló, intentando siguiente codec")
        except Exception as e:
            if codec != candidates[-1][0]:
                print("[VIDEO_WRITER][WARN]", f"{codec} falló ({str(e) or e.__class__.__name__}), intentando siguiente codec")
            continue

    print("[VIDEO_WRITER][ERROR] no se pudo inicializar ningún codec")
    return None, None, None


def transcode_to_browser_mp4(input_path: str, output_path: str) -> tuple[bool, str | None]:
    """
    Intenta transcodificar `input_path` a un MP4 reproducible en navegador.

    - No debe romper el análisis si falla.
    - Preferimos libx264; fallback mpeg4 si libx264 no está disponible.
    """
    in_path = str(input_path)
    out_path = str(output_path)

    print(f"[VIDEO_TRANSCODE] input={in_path} output={out_path}")

    ffmpeg_bin = resolve_ffmpeg_bin()

    if not ffmpeg_bin:
        print("[VIDEO_TRANSCODE] success=False reason=ffmpeg_missing")
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
            print(f"[VIDEO_TRANSCODE] success={bool(ok)} codec={vcodec} output={out_path}")
            return bool(ok), (None if ok else "transcode_failed")
        except Exception as e:
            print(f"[VIDEO_TRANSCODE][WARN] codec={vcodec} failed err={str(e) or e.__class__.__name__}")
            continue

    print("[VIDEO_TRANSCODE] success=False")
    return False, "transcode_failed"


def make_browser_compatible_mp4(input_path: str, output_path: str) -> tuple[bool, str | None]:
    """Wrapper semántico: genera un MP4 final compatible con navegador."""
    try:
        return transcode_to_browser_mp4(input_path, output_path)
    except Exception as e:
        print(f"[VIDEO_TRANSCODE][ERROR] {str(e) or e.__class__.__name__}")
        return False, "exception"


def is_valid_video_file(path: str | None) -> bool:
    """Devuelve True si `path` existe y tiene tamaño > 0."""
    if not path:
        return False
    try:
        return os.path.exists(path) and int(os.path.getsize(path) or 0) > 0
    except Exception:
        return False
