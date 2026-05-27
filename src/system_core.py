"""
Módulo      : system_core.py
Rol         : Núcleo compartido del sistema SIRAN. Agrupa en un solo módulo los
              helpers de entorno, las entidades SQLAlchemy (User, CameraConfig),
              el control ONVIF (PTZController), el dataclass de frame (FrameRecord)
              y el escritor asíncrono de telemetría (MetricsDBWriter). Se importa
              desde config.py, app.py y todos los servicios.
Conectado con: config.py (solo sus env-helpers son re-exportados),
              src/services/crypto_service.py (_EncryptedString),
              flask_sqlalchemy, flask_login, werkzeug.security, onvif-zeep.
Usado por   : app.py (db, User, CameraConfig, PTZController, FrameRecord,
              MetricsDBWriter), src/services/* y src/routes/*.
Hilos       : MetricsDBWriter corre un hilo daemon de escritura por lotes.
              PTZController es instanciado por PTZCommandWorker en su propio hilo.
Base de datos: detections.db (MetricsDBWriter vía _open_db en WAL mode),
              app.db (SQLAlchemy — User, CameraConfig).
"""

from __future__ import annotations

import logging
import os
import queue
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import TypeDecorator, String as _SAString
from werkzeug.security import check_password_hash, generate_password_hash

from src.services.crypto_service import decrypt as _decrypt, encrypt as _encrypt


class _EncryptedString(TypeDecorator):
    """
    Tipo SQLAlchemy personalizado que cifra en escritura y descifra en lectura.

    Responsabilidad: ser invisible para el resto del modelo — CameraConfig usa
    columnas normales pero los valores en SQLite siempre llegan cifrados.
    Ciclo de vida  : instanciado como tipo de columna; vive mientras la app corre.
    Atributos clave: ``impl = String`` (almacenamiento base), ``cache_ok = True``
                     (requerido por SQLAlchemy 1.4+ para cache de queries).
    """
    impl = _SAString
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return _encrypt(str(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return _decrypt(str(value))


# ======================== ENTORNO / UTILIDADES ========================


def env_bool(name: str, default: bool) -> bool:
    """
    Lee una variable de entorno y la interpreta como booleano.

    Args:
        name: Nombre de la variable de entorno.
        default: Valor si la variable no está definida o tiene valor inválido.

    Returns:
        True para "1/true/t/yes/y/on"; False para "0/false/f/no/n/off";
        ``default`` si el valor no encaja con ninguna de las variantes.
    """
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip().lower()
    if value in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "f", "no", "n", "off"}:
        return False
    return default


def env_int(name: str, default: int) -> int:
    """
    Lee una variable de entorno y la convierte a entero.

    Args:
        name: Nombre de la variable de entorno.
        default: Valor si la variable no está definida o no es un entero válido.

    Returns:
        Entero parseado, o ``default`` ante cualquier excepción de conversión.
    """
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value.strip())
    except (ValueError, TypeError):
        return default


def env_float(name: str, default: float) -> float:
    """
    Lee una variable de entorno y la convierte a float.

    Args:
        name: Nombre de la variable de entorno.
        default: Valor si la variable no está definida o no es un float válido.

    Returns:
        Float parseado, o ``default`` ante cualquier excepción de conversión.
    """
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value.strip())
    except (ValueError, TypeError):
        return default


def clamp(value: float, min_val: float, max_val: float) -> float:
    """
    Limita ``value`` al rango ``[min_val, max_val]``.

    Usado intensivamente en el control PTZ para que los vectores de velocidad
    nunca excedan los límites del hardware ONVIF (±1.0).

    Args:
        value: Valor a limitar.
        min_val: Límite inferior.
        max_val: Límite superior.

    Returns:
        ``value`` dentro del rango ``[min_val, max_val]``.
    """
    return float(max(min_val, min(max_val, float(value))))


def bbox_area(bbox: tuple[int, int, int, int]) -> int:
    """
    Área en píxeles de un bounding box xyxy.

    Args:
        bbox: Tupla ``(x1, y1, x2, y2)`` en coordenadas de pixel.

    Returns:
        Área en píxeles cuadrados (mínimo 0).
    """
    x1, y1, x2, y2 = bbox
    return max(0, int(x2) - int(x1)) * max(0, int(y2) - int(y1))


def select_priority_detection(detection_list: list[dict[str, Any]]) -> dict[str, Any] | None:
    """
    Selecciona la detección de mayor área para el seguimiento PTZ.

    Regla de priorización de enjambre (Regla 5 de app.py): el tracking PTZ
    se centra en el bounding box MÁS GRANDE — asume que el UAV más cercano
    o el más amenazante es el que ocupa más área en el encuadre.

    Args:
        detection_list: Lista de detecciones con clave ``"bbox"`` (xyxy).

    Returns:
        La detección con mayor área, o None si la lista está vacía.
    """
    if not detection_list:
        return None
    return max(detection_list, key=lambda d: bbox_area(tuple(d["bbox"])))


def iou_pair(a: tuple, b: tuple) -> float:
    """IoU entre dos bboxes individuales en coordenadas xyxy."""
    xi1 = max(a[0], b[0])
    yi1 = max(a[1], b[1])
    xi2 = min(a[2], b[2])
    yi2 = min(a[3], b[3])
    inter = max(0, xi2 - xi1) * max(0, yi2 - yi1)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def iou_matrix(bboxes_a: list, bboxes_b: list) -> "Any":
    """Matriz IoU entre dos listas de bboxes xyxy. Requiere numpy."""
    import numpy as np
    mat = np.zeros((len(bboxes_a), len(bboxes_b)), dtype=np.float32)
    for i, a in enumerate(bboxes_a):
        for j, b in enumerate(bboxes_b):
            mat[i, j] = iou_pair(a, b)
    return mat


def _open_db(path: str, *, timeout: float = 10.0) -> sqlite3.Connection:
    """
    Abre una conexión SQLite con configuración optimizada para escrituras concurrentes.

    WAL (Write-Ahead Log) permite lecturas y escrituras simultáneas desde múltiples
    hilos sin bloqueos exclusivos — crítico porque MetricsDBWriter, DetectionEventWriter
    y las rutas Flask consultan detections.db al mismo tiempo.

    Args:
        path: Ruta al archivo SQLite.
        timeout: Segundos de espera ante bloqueos (default 10 s).

    Returns:
        Conexión SQLite con check_same_thread=False (seguro con GIL + WAL).
    """
    con = sqlite3.connect(str(path), timeout=float(timeout), check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    return con


# ======================== DB (SQLAlchemy) ========================

db = SQLAlchemy()


class User(db.Model, UserMixin):
    """
    Entidad de usuario de la aplicación (autenticación Flask-Login).

    Responsabilidad: autenticar operadores y administradores.
    Ciclo de vida  : creado por bootstrap_users() en primera ejecución; persistido
                     en app.db tabla ``users``.
    Atributos clave: ``role`` (``"admin"`` | ``"operator"``), ``username``, ``password_hash``.
    """
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="operator")  # admin | operator
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class CameraConfig(db.Model):
    """
    Configuración de cámara persistida en app.db (singleton — una sola fila).

    Responsabilidad: almacenar URL RTSP, credenciales ONVIF y tipo de cámara
                     (fija/PTZ) de forma persistente entre reinicios.
    Ciclo de vida  : creado/leído por CameraConfigService.get_or_create_camera_config()
                     en cada arranque.
    Atributos clave: ``camera_type`` ("fixed"|"ptz"), ``rtsp_url``, ``onvif_host``,
                     ``onvif_password`` (cifrado via _EncryptedString).
    """
    __tablename__ = "camera_config"

    id = db.Column(db.Integer, primary_key=True)
    camera_type = db.Column(db.String(10), nullable=False, default="fixed")

    rtsp_url = db.Column(db.String(500), nullable=True)
    rtsp_username = db.Column(db.String(120), nullable=True)
    rtsp_password = db.Column(_EncryptedString(500), nullable=True)

    onvif_host = db.Column(db.String(120), nullable=True)
    onvif_port = db.Column(db.Integer, nullable=False, default=80)
    onvif_username = db.Column(db.String(120), nullable=True)
    onvif_password = db.Column(_EncryptedString(500), nullable=True)

    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def effective_rtsp_url(self) -> str | None:
        """
        Construye la URL RTSP con credenciales embebidas si no ya las tiene.

        Inyectar user:pass en la URL es la forma más compatible con OpenCV
        para streams RTSP autenticados — muchas cámaras IP no aceptan Basic Auth
        por cabeceras HTTP, solo en la URL.

        Returns:
            URL RTSP con credenciales, o None si rtsp_url no está configurada.
        """
        if not self.rtsp_url:
            return None
        if "://" not in self.rtsp_url:
            return self.rtsp_url
        if "@" in self.rtsp_url:
            return self.rtsp_url
        if self.rtsp_username and self.rtsp_password:
            scheme, rest = self.rtsp_url.split("://", 1)
            return f"{scheme}://{self.rtsp_username}:{self.rtsp_password}@{rest}"
        return self.rtsp_url


# ======================== PTZ (ONVIF) ========================


class PTZController:
    """
    Controlador ONVIF para cámaras PTZ (Pan-Tilt-Zoom).

    Responsabilidad: abstraer la comunicación ONVIF/WSDL para enviar comandos
                     ContinuousMove y Stop. Gestiona la sesión ONVIF con reconexión
                     automática ante fallos Zeep.
    Ciclo de vida  : instanciado por PTZCommandWorker y admin_camera routes;
                     la conexión ONVIF se establece lazy en el primer comando.
    Atributos clave: ``host``, ``port``, ``username``, ``password``,
                     ``_ptz`` (servicio ONVIF), ``_profile`` (perfil seleccionado).
    """
    def __init__(
        self,
        host: str,
        port: int = 80,
        username: str | None = None,
        password: str | None = None,
        *,
        preferred_profile_token: str | None = None,
    ):
        self.host = host
        self.port = port
        self.username = username or ""
        self.password = password or ""
        self.preferred_profile_token = (preferred_profile_token or "").strip() or None
        self._ptz = None
        self._media = None
        self._profile = None
        self._is_moving = False

    def _reset_session(self) -> None:
        self._ptz = None
        self._media = None
        self._profile = None
        self._is_moving = False

    def connect(self) -> None:
        try:
            from onvif import ONVIFCamera  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError("Dependencia ONVIF no instalada. Instala `onvif-zeep`.") from e

        cam = ONVIFCamera(self.host, self.port, self.username, self.password)
        self._media = cam.create_media_service()
        self._ptz = cam.create_ptz_service()
        profiles = self._media.GetProfiles()
        if not profiles:
            raise RuntimeError("No se encontraron perfiles ONVIF.")
        chosen = None
        if self.preferred_profile_token:
            for p in profiles:
                if getattr(p, "token", None) == self.preferred_profile_token:
                    chosen = p
                    break
        if chosen is None:
            candidates = [p for p in profiles if getattr(p, "token", None) and getattr(p, "PTZConfiguration", None) is not None]
            if candidates:
                def _score(p) -> int:
                    try:
                        enc = getattr(p, "VideoEncoderConfiguration", None)
                        res = getattr(enc, "Resolution", None) if enc is not None else None
                        w = int(getattr(res, "Width", 0) or 0) if res is not None else 0
                        h = int(getattr(res, "Height", 0) or 0) if res is not None else 0
                        return max(0, w) * max(0, h)
                    except Exception:
                        return 0

                chosen = max(candidates, key=_score)
        self._profile = chosen or profiles[0]

    def test_connection(self) -> dict:
        start = time.time()
        self.connect()
        elapsed_ms = int((time.time() - start) * 1000)
        return {"ok": True, "elapsed_ms": elapsed_ms}

    def continuous_move(self, x: float = 0.0, y: float = 0.0, zoom: float = 0.0, duration_s: float = 0.2) -> None:
        if abs(float(x)) < 1e-6 and abs(float(y)) < 1e-6 and abs(float(zoom)) < 1e-6:
            self.stop()
            return

        if not self._ptz or not self._profile:
            self.connect()

        def _send_once() -> None:
            request = self._ptz.create_type("ContinuousMove")
            request.ProfileToken = self._profile.token

            try:
                status = self._ptz.GetStatus({"ProfileToken": self._profile.token})
            except Exception as e:
                raise RuntimeError(
                    "No se pudo obtener status.Position para construir Velocity compatible con Hikvision."
                ) from e

            position = getattr(status, "Position", None) if status is not None else None
            if position is None:
                raise RuntimeError("No se pudo obtener status.Position para construir Velocity compatible con Hikvision.")

            request.Velocity = position

            if hasattr(request.Velocity, "PanTilt") and request.Velocity.PanTilt is not None:
                request.Velocity.PanTilt.space = None
                request.Velocity.PanTilt.x = float(x)
                request.Velocity.PanTilt.y = float(y)

            if hasattr(request.Velocity, "Zoom") and request.Velocity.Zoom is not None:
                request.Velocity.Zoom.space = None
                request.Velocity.Zoom.x = float(zoom) if zoom is not None else 0.0

            self._ptz.ContinuousMove(request)
            self._is_moving = True

        try:
            _send_once()
        except Exception as e:
            fault_cls = None
            try:
                from zeep.exceptions import Fault as fault_cls  # type: ignore
            except Exception:
                fault_cls = None

            if fault_cls is not None and isinstance(e, fault_cls):
                msg = (str(e) or "").lower()
                if "locked" in msg:
                    raise RuntimeError("Hardware bloqueado: requiere reinicio fisico.") from e
                self._reset_session()
                self.connect()
                _send_once()
            else:
                raise

        time.sleep(max(0.05, float(duration_s)))
        self.stop()

    def stop(self) -> None:
        if not self._ptz or not self._profile:
            return
        if not self._is_moving:
            return
        req = self._ptz.create_type("Stop")
        req.ProfileToken = self._profile.token
        req.PanTilt = True
        req.Zoom = True
        self._ptz.Stop(req)
        self._is_moving = False


# ======================== TELEMETRÍA (SQLite) ========================


@dataclass(frozen=True, slots=True)
class FrameRecord:
    """
    Moneda de intercambio entre el pipeline de video y los escritores de DB.

    Responsabilidad: transportar todos los datos de un frame procesado en un
                     objeto inmutable (frozen) para que los escritores async
                     puedan serializarlo sin riesgo de race conditions.
    Ciclo de vida  : creado en LiveVideoProcessor._run() por cada frame inferido,
                     encolado en MetricsDBWriter y DetectionEventWriter.
    Atributos clave: ``inference_ms`` (latencia de inferencia), ``detections``
                     (lista de dicts con bbox/confidence), ``confirmed`` (bool).
    """
    timestamp_iso: str
    source: str
    inference_ms: float
    frame_w: int
    frame_h: int
    detections: list[dict[str, Any]]
    confirmed: bool
    camera_mode: str


class MetricsDBWriter:
    """
    Escritor asíncrono de telemetría de frames a detections.db.

    Responsabilidad: desacoplar el pipeline de video de las escrituras SQLite.
                     Emplea una cola in-memory (queue.Queue) y un hilo daemon
                     que realiza inserciones por lotes para minimizar latencia.
    Ciclo de vida  : instanciado en app.py al arranque; el hilo daemon inicia
                     automáticamente si enabled=True; termina via stop().
    Atributos clave: ``_q`` (cola de FrameRecord), ``_stop`` (Event de apagado).
    """
    def __init__(self, db_path: str, *, enabled: bool = True, queue_max: int = 5000) -> None:
        self.db_path = str(db_path)
        self.enabled = bool(enabled)
        self._q: queue.Queue[FrameRecord] = queue.Queue(maxsize=max(1, int(queue_max)))
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

        if self.enabled:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._thread.start()

    def stop(self, *, timeout_s: float = 2.0) -> None:
        if not self.enabled:
            return
        self._stop.set()
        self._thread.join(timeout=float(timeout_s))

    def enqueue(self, record: FrameRecord) -> None:
        if not self.enabled:
            return
        try:
            self._q.put_nowait(record)
        except queue.Full:
            return

    def _connect(self) -> sqlite3.Connection:
        return _open_db(self.db_path, timeout=30.0)

    def _ensure_schema(self, con: sqlite3.Connection) -> None:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS inference_frames (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                source TEXT,
                inference_ms REAL,
                frame_w INTEGER,
                frame_h INTEGER,
                detections_count INTEGER,
                confirmed INTEGER,
                camera_mode TEXT
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS detections_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                class_name TEXT,
                confidence REAL,
                x1 INTEGER,
                y1 INTEGER,
                x2 INTEGER,
                y2 INTEGER,
                source TEXT,
                inference_ms REAL,
                frame_w INTEGER,
                frame_h INTEGER,
                confirmed INTEGER,
                camera_mode TEXT,
                image_path TEXT,
                track_id INTEGER
            )
            """
        )
        # Migración: agregar track_id si la tabla ya existe sin esa columna
        try:
            con.execute("ALTER TABLE detections_v2 ADD COLUMN track_id INTEGER")
            con.commit()
        except sqlite3.OperationalError:
            pass  # columna ya existe

        con.commit()

    def _run(self) -> None:
        con: sqlite3.Connection | None = None
        try:
            con = self._connect()
            self._ensure_schema(con)

            pending: list[FrameRecord] = []
            last_flush = time.time()

            def _flush() -> None:
                nonlocal pending, last_flush
                if not pending:
                    return
                cur = con.cursor()
                try:
                    cur.executemany(
                        """
                        INSERT INTO inference_frames
                        (timestamp, source, inference_ms, frame_w, frame_h, detections_count, confirmed, camera_mode)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        [
                            (
                                r.timestamp_iso,
                                r.source,
                                float(r.inference_ms) if r.inference_ms is not None else None,
                                int(r.frame_w) if r.frame_w is not None else None,
                                int(r.frame_h) if r.frame_h is not None else None,
                                int(len(r.detections)),
                                1 if r.confirmed else 0,
                                r.camera_mode,
                            )
                            for r in pending
                        ],
                    )

                    det_rows = [
                        (
                            r.timestamp_iso,
                            d.get("class_name"),
                            d.get("confidence"),
                            (d.get("bbox") or (None, None, None, None))[0],
                            (d.get("bbox") or (None, None, None, None))[1],
                            (d.get("bbox") or (None, None, None, None))[2],
                            (d.get("bbox") or (None, None, None, None))[3],
                            r.source,
                            float(r.inference_ms) if r.inference_ms is not None else None,
                            int(r.frame_w) if r.frame_w is not None else None,
                            int(r.frame_h) if r.frame_h is not None else None,
                            1 if r.confirmed else 0,
                            r.camera_mode,
                            d.get("image_path"),
                            d.get("track_id"),
                        )
                        for r in pending
                        for d in r.detections
                    ]
                    if det_rows:
                        cur.executemany(
                            """
                            INSERT INTO detections_v2
                            (timestamp, class_name, confidence, x1, y1, x2, y2, source, inference_ms, frame_w, frame_h, confirmed, camera_mode, image_path, track_id)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            det_rows,
                        )

                    con.commit()
                except (sqlite3.DatabaseError, sqlite3.IntegrityError, sqlite3.OperationalError) as e:
                    logger.error("MetricsDB insert error: %s", e)
                    try:
                        con.rollback()
                    except sqlite3.Error:
                        pass
                finally:
                    pending = []
                    last_flush = time.time()

            while not self._stop.is_set():
                try:
                    pending.append(self._q.get(timeout=0.25))
                except queue.Empty:
                    pass

                if len(pending) >= 100 or (pending and (time.time() - last_flush) >= 1.0):
                    _flush()

            _flush()
        finally:
            try:
                if con is not None:
                    con.close()
            except sqlite3.Error:
                pass
