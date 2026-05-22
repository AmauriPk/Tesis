"""
Tracker SORT simplificado — asignación de IDs entre frames via IoU + Hungarian.
Sin Kalman filter — matching directo entre detecciones consecutivas.
Cumple RO-06 (track_id por objeto) a nivel de pipeline de detección.
"""
from __future__ import annotations

import logging
import time

import numpy as np
from scipy.optimize import linear_sum_assignment

logger = logging.getLogger(__name__)


def _iou_matrix(bboxes_a: list, bboxes_b: list) -> np.ndarray:
    """Matriz IoU entre dos listas de bboxes (x1,y1,x2,y2). Shape: (len_a, len_b)."""
    mat = np.zeros((len(bboxes_a), len(bboxes_b)), dtype=np.float32)
    for i, a in enumerate(bboxes_a):
        for j, b in enumerate(bboxes_b):
            xi1 = max(a[0], b[0])
            yi1 = max(a[1], b[1])
            xi2 = min(a[2], b[2])
            yi2 = min(a[3], b[3])
            inter = max(0, xi2 - xi1) * max(0, yi2 - yi1)
            area_a = (a[2] - a[0]) * (a[3] - a[1])
            area_b = (b[2] - b[0]) * (b[3] - b[1])
            union = area_a + area_b - inter
            mat[i, j] = inter / union if union > 0 else 0.0
    return mat


class Track:
    """Objeto rastreado con ID único y estado de vida."""

    _next_id = 1

    def __init__(self, bbox: tuple, class_name: str, confidence: float):
        self.track_id   = Track._next_id
        Track._next_id += 1
        self.bbox       = bbox
        self.class_name = class_name
        self.confidence = confidence
        self.age        = 1
        self.hits       = 1
        self.misses     = 0
        self.last_seen  = time.time()

    def update(self, bbox: tuple, confidence: float) -> None:
        self.bbox       = bbox
        self.confidence = confidence
        self.hits      += 1
        self.misses     = 0
        self.last_seen  = time.time()
        self.age       += 1


class SORTTracker:
    """
    Tracker SORT simplificado.

    iou_threshold — IoU mínimo para considerar match (default 0.30)
    max_misses    — frames sin match antes de eliminar track (default 3)
    min_hits      — hits mínimos para que un track sea confirmado (default 1)
    """

    def __init__(
        self,
        iou_threshold: float = 0.30,
        max_misses: int = 3,
        min_hits: int = 1,
    ):
        self.iou_threshold = float(iou_threshold)
        self.max_misses    = int(max_misses)
        self.min_hits      = int(min_hits)
        self._tracks: list[Track] = []

    def update(self, detections: list[dict]) -> list[dict]:
        """
        Recibe lista de detecciones del frame actual.
        Retorna la misma lista con campo 'track_id' agregado a cada detección.
        """
        if not detections:
            for t in self._tracks:
                t.misses += 1
                t.age    += 1
            self._tracks = [t for t in self._tracks if t.misses <= self.max_misses]
            return detections

        det_bboxes = [d["bbox"] for d in detections]

        if not self._tracks:
            for d in detections:
                trk = Track(d["bbox"], d.get("class_name", "RPAS"), float(d.get("confidence", 0.0)))
                self._tracks.append(trk)
                d["track_id"] = trk.track_id
            return detections

        trk_bboxes = [t.bbox for t in self._tracks]
        iou_mat    = _iou_matrix(trk_bboxes, det_bboxes)
        cost_mat   = 1.0 - iou_mat
        row_ind, col_ind = linear_sum_assignment(cost_mat)

        matched_trk: set[int] = set()
        matched_det: set[int] = set()
        track_id_map: dict[int, int] = {}

        for r, c in zip(row_ind, col_ind):
            if iou_mat[r, c] >= self.iou_threshold:
                self._tracks[r].update(det_bboxes[c], float(detections[c].get("confidence", 0.0)))
                track_id_map[c] = self._tracks[r].track_id
                matched_trk.add(r)
                matched_det.add(c)

        for r, t in enumerate(self._tracks):
            if r not in matched_trk:
                t.misses += 1
                t.age    += 1

        for c, d in enumerate(detections):
            if c not in matched_det:
                trk = Track(d["bbox"], d.get("class_name", "RPAS"), float(d.get("confidence", 0.0)))
                self._tracks.append(trk)
                track_id_map[c] = trk.track_id

        self._tracks = [t for t in self._tracks if t.misses <= self.max_misses]

        for c, d in enumerate(detections):
            d["track_id"] = track_id_map.get(c)

        logger.debug(
            "Tracker: %d tracks activos, %d detecciones, %d matches",
            len(self._tracks), len(detections), len(matched_det),
        )
        return detections

    def reset(self) -> None:
        self._tracks.clear()
        logger.info("SORTTracker reiniciado")

    @property
    def active_track_count(self) -> int:
        return len(self._tracks)
