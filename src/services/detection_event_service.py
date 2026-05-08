from __future__ import annotations

import os
import queue
import sqlite3
import threading
import time
from datetime import datetime

from config import _env_int
from src.system_core import FrameRecord


def _parse_iso_ts_to_epoch(ts_iso: str | None) -> float | None:
    if not ts_iso:
        return None
    try:
        return float(datetime.fromisoformat(str(ts_iso)).timestamp())
    except Exception:
        return None


def _ensure_detection_events_schema(con: sqlite3.Connection) -> None:
    con.execute("PRAGMA foreign_keys=ON;")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS detection_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            max_confidence REAL,
            detection_count INTEGER,
            best_bbox_text TEXT,
            best_evidence_path TEXT,
            status TEXT,
            source TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    con.commit()


class DetectionEventWriter:
    """
    Agrupa detecciones confirmadas en eventos (para UI defendible y eficiente).

    Importante: NO corre dentro del hilo de video/inferencia. Consume una cola.
    """

    def __init__(self, db_path: str, *, enabled: bool = True, gap_seconds: float = 3.0) -> None:
        self.db_path = str(db_path)
        self.enabled = bool(enabled)
        self.gap_seconds = float(gap_seconds)
        self._q: queue.Queue[FrameRecord] = queue.Queue(maxsize=5000)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

        self._active_event_id: int | None = None
        self._active_started_iso: str | None = None
        self._active_last_epoch: float | None = None
        self._active_last_iso: str | None = None
        self._active_max_conf: float = 0.0
        self._active_count: int = 0
        self._active_best_bbox_text: str | None = None
        self._active_best_evidence_path: str | None = None
        self._last_event_log_at: float = 0.0

        if self.enabled:
            try:
                os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            except Exception:
                pass
            self._thread.start()

    def enqueue(self, record: FrameRecord) -> None:
        if not self.enabled:
            return
        try:
            self._q.put_nowait(record)
        except queue.Full:
            # Evita bloquear el hilo de inferencia si la DB está lenta.
            pass

    def stop(self, timeout_s: float = 2.0) -> None:
        if not self.enabled:
            return
        self._stop.set()
        try:
            self._thread.join(timeout=float(timeout_s))
        except Exception:
            pass

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path, timeout=10, check_same_thread=False)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA journal_mode=WAL;")
            con.execute("PRAGMA synchronous=NORMAL;")
        except Exception as e:
            print(f"[EVENT_DB][WARN] pragma err={e}")
        _ensure_detection_events_schema(con)
        return con

    def _close_active_event(self, con: sqlite3.Connection) -> None:
        if self._active_event_id is None:
            return
        try:
            now_iso = datetime.now().isoformat()
            con.execute(
                """
                UPDATE detection_events
                SET ended_at=?, max_confidence=?, detection_count=?, best_bbox_text=?, best_evidence_path=?,
                    status='closed', updated_at=?
                WHERE id=?
                """,
                (
                    self._active_last_iso or now_iso,
                    float(self._active_max_conf),
                    int(self._active_count),
                    self._active_best_bbox_text,
                    self._active_best_evidence_path,
                    now_iso,
                    int(self._active_event_id),
                ),
            )
            con.commit()
            print(f"[EVENT] closed id={int(self._active_event_id)}")
        except Exception as e:
            print(f"[EVENT][ERROR] close_failed id={self._active_event_id} err={e}")
        finally:
            self._active_event_id = None
            self._active_started_iso = None
            self._active_last_epoch = None
            self._active_last_iso = None
            self._active_max_conf = 0.0
            self._active_count = 0
            self._active_best_bbox_text = None
            self._active_best_evidence_path = None

    def _create_active_event(self, con: sqlite3.Connection, *, started_at_iso: str, source: str | None) -> None:
        now_iso = datetime.now().isoformat()
        try:
            cur = con.cursor()
            cur.execute(
                """
                INSERT INTO detection_events
                (started_at, ended_at, max_confidence, detection_count, best_bbox_text, best_evidence_path, status, source, created_at, updated_at)
                VALUES (?, NULL, 0.0, 0, NULL, NULL, 'open', ?, ?, ?)
                """,
                (started_at_iso or now_iso, source, now_iso, now_iso),
            )
            con.commit()
            self._active_event_id = int(cur.lastrowid)
            self._active_started_iso = started_at_iso or now_iso
            self._active_last_epoch = _parse_iso_ts_to_epoch(str(started_at_iso)) or time.time()
            self._active_last_iso = started_at_iso or now_iso
            self._active_max_conf = 0.0
            self._active_count = 0
            self._active_best_bbox_text = None
            self._active_best_evidence_path = None
            print(f"[EVENT] created id={int(self._active_event_id)}")
        except Exception as e:
            print(f"[EVENT][ERROR] create_failed err={e}")
            self._active_event_id = None

    def _update_active_event(self, con: sqlite3.Connection) -> None:
        if self._active_event_id is None:
            return
        try:
            now_iso = datetime.now().isoformat()
            con.execute(
                """
                UPDATE detection_events
                SET ended_at=?, max_confidence=?, detection_count=?, best_bbox_text=?, best_evidence_path=?,
                    status='open', updated_at=?
                WHERE id=?
                """,
                (
                    self._active_last_iso or now_iso,
                    float(self._active_max_conf),
                    int(self._active_count),
                    self._active_best_bbox_text,
                    self._active_best_evidence_path,
                    now_iso,
                    int(self._active_event_id),
                ),
            )
            con.commit()
            # Evitar log spam: log cada 2s como máximo.
            now = time.time()
            if (now - float(self._last_event_log_at)) >= 2.0:
                self._last_event_log_at = now
                print(f"[EVENT] updated id={int(self._active_event_id)} max_conf={float(self._active_max_conf):.3f}")
        except Exception as e:
            print(f"[EVENT][ERROR] update_failed id={self._active_event_id} err={e}")

    def _run(self) -> None:
        con: sqlite3.Connection | None = None
        try:
            con = self._connect()

            # Backfill ligero: si no hay eventos todavía, crear algunos desde detections_v2
            try:
                cur = con.cursor()
                cur.execute("SELECT COUNT(1) FROM detection_events")
                n = int((cur.fetchone() or [0])[0] or 0)
                if n <= 0:
                    self._backfill_from_detections(con)
            except Exception as e:
                print(f"[EVENT][WARN] backfill_failed err={e}")

            while not self._stop.is_set():
                try:
                    r = self._q.get(timeout=0.25)
                except queue.Empty:
                    # Si hay evento abierto y expira el gap, cerrarlo.
                    if self._active_last_epoch is not None and self._active_event_id is not None:
                        now = time.time()
                        age = float(now - float(self._active_last_epoch))
                        if age > float(self.gap_seconds):
                            self._close_active_event(con)
                    continue
                except Exception as e:
                    print(f"[EVENT][ERROR] run_loop err={e}")
                    continue

                # Solo agrupar frames confirmados (con detecciones).
                try:
                    confirmed = bool(getattr(r, "confirmed", False))
                except Exception:
                    confirmed = False
                if not confirmed:
                    continue

                # Timestamp
                ts_iso = ""
                try:
                    ts_iso = str(getattr(r, "timestamp_iso", "") or "")
                except Exception:
                    ts_iso = ""
                ts_epoch = _parse_iso_ts_to_epoch(ts_iso) or time.time()

                # Si expira el gap entre detecciones, cerrar evento actual.
                if self._active_last_epoch is not None and (ts_epoch - float(self._active_last_epoch)) > float(self.gap_seconds):
                    self._close_active_event(con)

                if self._active_event_id is None:
                    src = None
                    try:
                        src = str(getattr(r, "source", "") or "") or None
                    except Exception:
                        src = None
                    self._create_active_event(con, started_at_iso=(ts_iso or datetime.now().isoformat()), source=src)

                # Acumular métricas
                self._active_last_epoch = float(ts_epoch)
                self._active_last_iso = ts_iso or self._active_last_iso or datetime.now().isoformat()
                self._active_count += 1

                # Detecciones: elegir mejor bbox/evidencia por max_confidence.
                try:
                    dets = list(getattr(r, "detections", []) or [])
                except Exception:
                    dets = []

                best_conf = 0.0
                best_bbox = None
                best_img = None
                for d in dets:
                    try:
                        conf = float(d.get("confidence") or 0.0)
                    except Exception:
                        conf = 0.0
                    if conf >= best_conf:
                        best_conf = conf
                        try:
                            bbox = d.get("bbox")
                            if bbox and len(bbox) == 4:
                                x1, y1, x2, y2 = [int(v) for v in bbox]
                                best_bbox = f"{x1},{y1},{x2},{y2}"
                        except Exception as e:
                            print(f"[EVENT][WARN] bbox_parse err={e}")
                        try:
                            p = d.get("evidence_path") or d.get("image_path") or None
                            if p:
                                best_img = str(p).replace("\\", "/")
                        except Exception as e:
                            print(f"[EVENT][WARN] evidence_path err={e}")

                if best_conf >= float(self._active_max_conf):
                    self._active_max_conf = float(best_conf)
                    self._active_best_bbox_text = best_bbox
                    self._active_best_evidence_path = best_img

                self._update_active_event(con)
        except Exception as e:
            print(f"[EVENT][ERROR] fatal err={e}")
        finally:
            if con is not None:
                try:
                    self._close_active_event(con)
                except Exception:
                    pass
                try:
                    con.close()
                except Exception:
                    pass

    def _backfill_from_detections(self, con: sqlite3.Connection) -> None:
        """
        Construye eventos a partir de detections_v2 existentes (solo una vez si la tabla está vacía).
        """
        gap_s = float(self.gap_seconds)
        try:
            backfill_limit = int(_env_int("EVENT_BACKFILL_LIMIT", 2000))
        except Exception:
            backfill_limit = 2000
        backfill_limit = max(100, min(10000, int(backfill_limit)))

        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {str(r[0]) for r in (cur.fetchall() or [])}
        if "detections_v2" not in tables:
            return

        cur.execute(
            """
            SELECT id, timestamp, confidence, x1, y1, x2, y2, class_name, source, camera_mode, image_path
            FROM detections_v2
            WHERE confirmed = 1
            ORDER BY id ASC
            LIMIT ?
            """,
            (int(backfill_limit),),
        )
        rows = cur.fetchall() or []

        active_id = None
        last_epoch = None
        last_iso = None
        max_conf = 0.0
        count = 0
        best_bbox = None
        best_img = None

        def _flush_close():
            nonlocal active_id, max_conf, count, best_bbox, best_img, last_iso
            if active_id is None:
                return
            now_iso = datetime.now().isoformat()
            con.execute(
                """
                UPDATE detection_events
                SET ended_at=?, max_confidence=?, detection_count=?, best_bbox_text=?, best_evidence_path=?,
                    status='closed', updated_at=?
                WHERE id=?
                """,
                (last_iso, float(max_conf), int(count), best_bbox, best_img, now_iso, int(active_id)),
            )
            con.commit()
            active_id = None

        for r in rows:
            ts_iso = str(r["timestamp"] or "")
            ts_epoch = _parse_iso_ts_to_epoch(ts_iso) or time.time()
            if last_epoch is not None and (ts_epoch - float(last_epoch)) > gap_s:
                _flush_close()
            if active_id is None:
                now_iso = datetime.now().isoformat()
                cur2 = con.cursor()
                cur2.execute(
                    """
                    INSERT INTO detection_events
                    (started_at, ended_at, max_confidence, detection_count, best_bbox_text, best_evidence_path, status, source, created_at, updated_at)
                    VALUES (?, NULL, 0.0, 0, NULL, NULL, 'open', ?, ?, ?)
                    """,
                    (ts_iso or datetime.now().isoformat(), (r["source"] or None), now_iso, now_iso),
                )
                con.commit()
                active_id = int(cur2.lastrowid)
                max_conf = 0.0
                count = 0
                best_bbox = None
                best_img = None

            last_epoch = ts_epoch
            last_iso = ts_iso or last_iso or datetime.now().isoformat()
            count += 1
            try:
                conf = float(r["confidence"] or 0.0)
            except Exception:
                conf = 0.0
            if conf >= max_conf:
                max_conf = conf
                try:
                    x1, y1, x2, y2 = int(r["x1"]), int(r["y1"]), int(r["x2"]), int(r["y2"])
                    best_bbox = f"{x1},{y1},{x2},{y2}"
                except Exception:
                    pass
                try:
                    p = r["image_path"] or None
                    if p:
                        best_img = str(p).replace("\\", "/")
                except Exception:
                    pass

            now_iso = datetime.now().isoformat()
            con.execute(
                """
                UPDATE detection_events
                SET ended_at=?, max_confidence=?, detection_count=?, best_bbox_text=?, best_evidence_path=?,
                    status='open', updated_at=?
                WHERE id=?
                """,
                (last_iso, float(max_conf), int(count), best_bbox, best_img, now_iso, int(active_id)),
            )
            con.commit()

        _flush_close()
        print(f"[EVENT] backfill done events_ready=1 rows={len(rows)}")

