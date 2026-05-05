"""
metrics_logger.py
=================
Persistencia de métricas/telemetría del sistema de detección.

Este módulo implementa escritura asíncrona a SQLite para evitar que la inferencia
en tiempo real se bloquee por I/O.

Tablas:
- `inference_frames`: 1 registro por frame inferido (latencia/FPS real).
- `detections_v2`: 1 registro por bbox detectado (clase, confianza, bbox, etc.).

Se mantiene separado de `app.py` para:
- reducir acoplamiento
- facilitar pruebas y mantenimiento
"""

from __future__ import annotations

import queue
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
    """
    Writer asíncrono:
    - `enqueue()` agrega un FrameRecord
    - un hilo consume e inserta en SQLite por batch
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
        """
        Encola un registro sin bloquear el pipeline.
        Si la cola está llena, se descarta (fail-safe de performance).
        """

        if not self.enabled:
            return
        try:
            self._q.put_nowait(record)
        except queue.Full:
            # Drop: preferimos perder logs a degradar FPS en vivo.
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
                    # Inserta frames
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

                    # Inserta detecciones (1 por bbox)
                    det_rows: list[tuple[Any, ...]] = []
                    for r in pending:
                        for d in r.detections:
                            bbox = d.get("bbox") or (None, None, None, None)
                            x1, y1, x2, y2 = bbox
                            det_rows.append(
                                (
                                    r.timestamp_iso,
                                    d.get("class_name"),
                                    d.get("confidence"),
                                    x1,
                                    y1,
                                    x2,
                                    y2,
                                    r.source,
                                    float(r.inference_ms) if r.inference_ms is not None else None,
                                    int(r.frame_w) if r.frame_w is not None else None,
                                    int(r.frame_h) if r.frame_h is not None else None,
                                    1 if r.confirmed else 0,
                                    r.camera_mode,
                                    d.get("image_path"),
                                )
                            )
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
                except Exception:
                    # Fail-safe: si algo sale mal con DB, no detenemos el sistema.
                    try:
                        con.rollback()
                    except Exception:
                        pass
                finally:
                    pending = []
                    last_flush = time.time()

            while not self._stop.is_set():
                try:
                    item = self._q.get(timeout=0.25)
                    pending.append(item)
                except queue.Empty:
                    pass

                # Flush por tamaño o por tiempo.
                if len(pending) >= 100 or (pending and (time.time() - last_flush) >= 1.0):
                    _flush()

            # Flush final
            _flush()
        finally:
            try:
                if con is not None:
                    con.close()
            except Exception:
                pass

