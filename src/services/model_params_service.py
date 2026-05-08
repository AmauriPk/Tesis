from __future__ import annotations

import os
import threading
from typing import Callable


class ModelParamsService:
    def __init__(self, *, env_float: Callable[[str, float], float], env_int: Callable[[str, int], int]):
        self._env_float = env_float
        self._env_int = env_int
        self.lock = threading.Lock()
        self.model_params = {
            "confidence_threshold": float(self._env_float("CONFIDENCE_THRESHOLD", 0.60)),
            "persistence_frames": int(max(1, self._env_int("PERSISTENCE_FRAMES", 3))),
            "iou_threshold": float(self._env_float("IOU_THRESHOLD", 0.45)),
        }

    def get_model_params(self) -> dict:
        with self.lock:
            return dict(self.model_params)

    def update_model_params(self, *, confidence_threshold: float, persistence_frames: int, iou_threshold: float) -> dict:
        with self.lock:
            self.model_params["confidence_threshold"] = float(confidence_threshold)
            self.model_params["persistence_frames"] = int(max(1, int(persistence_frames)))
            self.model_params["iou_threshold"] = float(iou_threshold)
            return dict(self.model_params)

    def get_detection_persistence_frames(self) -> int:
        """
        Mitigación de aves:
        Requiere que la detección "persista" por N frames consecutivos antes de marcar `detected=True`.
        """
        try:
            raw_dpf = os.environ.get("DETECTION_PERSISTENCE_FRAMES", "3").strip()
            return max(1, int(raw_dpf))
        except (ValueError, TypeError) as e:
            print(f"[WARN] DETECTION_PERSISTENCE_FRAMES='{raw_dpf}' invalid: {e}, using default=3")
            return 3

