"""
Módulo      : tracker_service.py
Rol         : Tracker multi-objeto SORT simplificado. Asigna IDs persistentes a
              detecciones entre frames consecutivos usando IoU + asignación húngara
              (linear_sum_assignment de scipy). Sin Kalman filter — matching directo.
Conectado con: src/system_core.py (iou_matrix), scipy.optimize, numpy.
Usado por   : src/video_processor.py (LiveVideoProcessor instancia SORTTracker
              y llama update() en cada frame de inferencia).
Hilos       : El tracker corre dentro del hilo LiveVideoProcessor._run() —
              no es thread-safe (no necesario: acceso desde un único hilo).
Base de datos: No accede a DB; los track_ids se propagan en los dicts de
              detección que MetricsDBWriter persiste en detections_v2.
"""
from __future__ import annotations

import logging
import time

import numpy as np
from scipy.optimize import linear_sum_assignment

from src.system_core import iou_matrix as _iou_matrix

logger = logging.getLogger(__name__)


class Track:
    """
    Objeto rastreado individual con ID único y estado de vida (hits/misses).

    Responsabilidad: mantener el bounding box actualizado y decidir cuándo
                     un track debe eliminarse (cuando misses > max_misses).
    Ciclo de vida  : creado por SORTTracker al detectar un objeto nuevo;
                     destruido cuando ``misses > max_misses``.
    Atributos clave: ``track_id`` (entero incremental global), ``hits`` (matches
                     acumulados), ``misses`` (frames consecutivos sin match).
    """

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
    Tracker SORT simplificado — múltiples objetos, IDs persistentes por IoU.

    Responsabilidad: asignar ``track_id`` a las detecciones de cada frame
                     de forma consistente entre frames consecutivos.
    Ciclo de vida  : instanciado en LiveVideoProcessor.__init__(); reset() se
                     llama automáticamente al reconectar el RTSP para evitar
                     IDs obsoletos de la sesión anterior.

    Atributos:
        iou_threshold: IoU mínimo para considerar un match (RO-06: default 0.30).
        max_misses: Frames sin match antes de eliminar un track (default 3).
        min_hits: Hits mínimos para confirmar un track nuevo (default 1).
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
