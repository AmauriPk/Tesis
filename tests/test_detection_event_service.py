"""Smoke tests para DetectionEventWriter y _ensure_detection_events_schema."""
from __future__ import annotations

import sqlite3
import tempfile
import time
from datetime import datetime
from pathlib import Path

import pytest

from src.services.detection_event_service import (
    DetectionEventWriter,
    _ensure_detection_events_schema,
)
from src.system_core import FrameRecord, _open_db


def _frame(confirmed=True, detections=None, confidence=0.95):
    return FrameRecord(
        timestamp_iso=datetime.now().isoformat(),
        source="test",
        inference_ms=10.0,
        frame_w=1280,
        frame_h=720,
        detections=detections or [{"class_name": "RPAS", "confidence": confidence, "bbox": (0, 0, 50, 50)}],
        confirmed=confirmed,
        camera_mode="ptz",
    )


class TestEnsureSchema:
    def test_creates_table(self, tmp_path):
        db = str(tmp_path / "events.db")
        con = _open_db(db)
        _ensure_detection_events_schema(con)
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        assert "detection_events" in tables
        con.close()

    def test_idempotent(self, tmp_path):
        db = str(tmp_path / "events.db")
        con = _open_db(db)
        _ensure_detection_events_schema(con)
        _ensure_detection_events_schema(con)  # should not raise
        con.close()


class TestDetectionEventWriterDisabled:
    def test_enqueue_noop_when_disabled(self):
        writer = DetectionEventWriter(":memory:", enabled=False)
        writer.enqueue(_frame())
        writer.stop()

    def test_stop_noop_when_disabled(self):
        writer = DetectionEventWriter(":memory:", enabled=False)
        writer.stop()


class TestDetectionEventWriterEnabled:
    def test_confirmed_frame_creates_event(self, tmp_path):
        db = str(tmp_path / "det_events.db")
        writer = DetectionEventWriter(db, enabled=True, gap_seconds=1.0)
        writer.enqueue(_frame(confirmed=True))
        time.sleep(0.5)  # let worker flush
        writer.stop(timeout_s=2.0)

        con = _open_db(db)
        _ensure_detection_events_schema(con)
        rows = con.execute("SELECT * FROM detection_events").fetchall()
        con.close()
        assert len(rows) >= 1

    def test_unconfirmed_frame_creates_no_event(self, tmp_path):
        db = str(tmp_path / "det_events2.db")
        writer = DetectionEventWriter(db, enabled=True, gap_seconds=1.0)
        writer.enqueue(_frame(confirmed=False))
        time.sleep(0.4)
        writer.stop(timeout_s=2.0)

        con = _open_db(db)
        _ensure_detection_events_schema(con)
        count = con.execute("SELECT COUNT(1) FROM detection_events").fetchone()[0]
        con.close()
        assert count == 0
