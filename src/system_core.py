"""Sirve para utilidades del sistema, entidades DB, control PTZ y telemetrÃ­a en un solo mÃ³dulo."""

from __future__ import annotations

import os
import queue
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash


# ======================== ENTORNO / UTILIDADES ========================


def env_bool(name: str, default: bool) -> bool:
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
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value.strip())
    except (ValueError, TypeError):
        return default


def env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value.strip())
    except (ValueError, TypeError):
        return default


def clamp(value: float, min_val: float, max_val: float) -> float:
    return float(max(min_val, min(max_val, float(value))))


def safe_join_path(*parts: str) -> str:
    import os.path

    joined = os.path.join(*parts)
    normalized = os.path.normpath(joined)
    if ".." in normalized.split(os.sep):
        raise ValueError(f"Path traversal detected: {joined}")
    return normalized.replace("\\", "/")


def validate_bbox(bbox: tuple[int, int, int, int]) -> bool:
    x1, y1, x2, y2 = bbox
    return int(x1) < int(x2) and int(y1) < int(y2)


def bbox_area(bbox: tuple[int, int, int, int]) -> int:
    x1, y1, x2, y2 = bbox
    return max(0, int(x2) - int(x1)) * max(0, int(y2) - int(y1))


def select_priority_detection(detection_list: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not detection_list:
        return None
    return max(detection_list, key=lambda d: bbox_area(tuple(d["bbox"])))


def normalize_url_with_credentials(
    base_url: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> str:
    if not base_url or "://" not in base_url:
        return base_url
    if "@" in base_url:
        return base_url
    if username and password:
        scheme, rest = base_url.split("://", 1)
        return f"{scheme}://{username}:{password}@{rest}"
    return base_url


def graceful_shutdown_handler(stop_signals: list) -> None:
    for signal_obj in stop_signals:
        if hasattr(signal_obj, "set"):
            signal_obj.set()


def should_allow_ptz_move(*, is_ptz_capable: bool) -> bool:
    return bool(is_ptz_capable)


def assert_ptz_capable(*, is_ptz_capable: bool) -> None:
    if not should_allow_ptz_move(is_ptz_capable=is_ptz_capable):
        raise PermissionError("PTZ no disponible (fail-safe ONVIF: cÃ¡mara fija).")


# ======================== DB (SQLAlchemy) ========================

db = SQLAlchemy()


class User(db.Model, UserMixin):
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
    __tablename__ = "camera_config"

    id = db.Column(db.Integer, primary_key=True)
    camera_type = db.Column(db.String(10), nullable=False, default="fixed")

    rtsp_url = db.Column(db.String(500), nullable=True)
    rtsp_username = db.Column(db.String(120), nullable=True)
    rtsp_password = db.Column(db.String(120), nullable=True)

    onvif_host = db.Column(db.String(120), nullable=True)
    onvif_port = db.Column(db.Integer, nullable=False, default=80)
    onvif_username = db.Column(db.String(120), nullable=True)
    onvif_password = db.Column(db.String(120), nullable=True)

    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def effective_rtsp_url(self) -> str | None:
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


# ======================== TELEMETRÃA (SQLite) ========================


@dataclass(frozen=True, slots=True)
class FrameRecord:
    timestamp_iso: str
    source: str
    inference_ms: float
    frame_w: int
    frame_h: int
    detections: list[dict[str, Any]]
    confirmed: bool
    camera_mode: str


class MetricsDBWriter:
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
        con = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA synchronous=NORMAL;")
        con.execute("PRAGMA foreign_keys=ON;")
        return con

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
                image_path TEXT
            )
            """
        )
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
                        )
                        for r in pending
                        for d in r.detections
                    ]
                    if det_rows:
                        cur.executemany(
                            """
                            INSERT INTO detections_v2
                            (timestamp, class_name, confidence, x1, y1, x2, y2, source, inference_ms, frame_w, frame_h, confirmed, camera_mode, image_path)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            det_rows,
                        )

                    con.commit()
                except (sqlite3.DatabaseError, sqlite3.IntegrityError, sqlite3.OperationalError) as e:
                    print(f"[METRICS_DB] Insert error: {e}")
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
