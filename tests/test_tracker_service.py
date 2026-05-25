"""Smoke tests para SORTTracker (tracker_service)."""
from __future__ import annotations

import pytest
from src.services.tracker_service import SORTTracker


def _det(x1, y1, x2, y2, cls="RPAS", conf=0.9):
    return {"bbox": (x1, y1, x2, y2), "class_name": cls, "confidence": conf}


class TestSORTTrackerBasic:
    def test_empty_frame_returns_empty(self):
        t = SORTTracker()
        assert t.update([]) == []

    def test_single_detection_gets_track_id(self):
        t = SORTTracker()
        dets = t.update([_det(0, 0, 100, 100)])
        assert len(dets) == 1
        assert dets[0]["track_id"] is not None

    def test_same_object_keeps_track_id(self):
        t = SORTTracker(iou_threshold=0.30)
        dets1 = t.update([_det(0, 0, 100, 100)])
        tid1 = dets1[0]["track_id"]
        # slightly shifted — high IoU, same track
        dets2 = t.update([_det(5, 5, 105, 105)])
        tid2 = dets2[0]["track_id"]
        assert tid1 == tid2

    def test_disjoint_detection_gets_new_track_id(self):
        t = SORTTracker(iou_threshold=0.30)
        dets1 = t.update([_det(0, 0, 50, 50)])
        tid1 = dets1[0]["track_id"]
        # completely non-overlapping
        dets2 = t.update([_det(500, 500, 600, 600)])
        tid2 = dets2[0]["track_id"]
        assert tid1 != tid2

    def test_track_pruned_after_max_misses(self):
        t = SORTTracker(max_misses=3)
        t.update([_det(0, 0, 100, 100)])
        assert t.active_track_count == 1
        for _ in range(3):
            t.update([])
        # 3 misses: still alive (misses <= max_misses)
        assert t.active_track_count == 1
        t.update([])  # 4th empty frame → pruned
        assert t.active_track_count == 0

    def test_reset_clears_tracks(self):
        t = SORTTracker()
        t.update([_det(0, 0, 100, 100)])
        assert t.active_track_count == 1
        t.reset()
        assert t.active_track_count == 0

    def test_two_objects_get_distinct_ids(self):
        t = SORTTracker()
        dets = t.update([_det(0, 0, 50, 50), _det(500, 0, 550, 50)])
        ids = {d["track_id"] for d in dets}
        assert len(ids) == 2
