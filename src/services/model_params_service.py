"""
Módulo      : model_params_service.py
Rol         : Gestión thread-safe de los parámetros operativos del modelo YOLO
              (confidence_threshold, persistence_frames, iou_threshold).
              Permite al Administrador ajustar el comportamiento de detección
              en caliente (hot update) sin reiniciar el servidor.
Conectado con: config.py (env_float/env_int para inicializar valores desde env),
              src/routes/model_params.py (llama update_model_params en POST).
Usado por   : app.py (instancia, expone get_model_params al LiveVideoProcessor),
              src/routes/analysis.py (lee params para jobs manuales).
Hilos       : self.lock (threading.Lock) protege lecturas/escrituras de model_params.
Base de datos: No accede a ninguna DB.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Callable

logger = logging.getLogger(__name__)


class ModelParamsService:
    """
    Almacén thread-safe de parámetros operativos del modelo de detección.

    Responsabilidad: ser la única fuente de verdad de confidence_threshold,
                     persistence_frames e iou_threshold en tiempo de ejecución.
    Ciclo de vida  : instanciado en app.py al arranque; nunca se recrea.
    Atributos clave: ``model_params`` (dict mutable), ``lock`` (RLock compartido
                     con app.py para que otras áreas puedan leerlo con él).
    """
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
        """
        Devuelve una copia del diccionario de parámetros actuales.

        Returns:
            Dict con ``confidence_threshold``, ``persistence_frames`` e ``iou_threshold``.
        """
        with self.lock:
            return dict(self.model_params)

    def update_model_params(self, *, confidence_threshold: float, persistence_frames: int, iou_threshold: float) -> dict:
        """
        Actualiza los tres parámetros operativos de forma atómica (bajo lock).

        El LiveVideoProcessor lee get_model_params() en cada frame, por lo que
        el cambio toma efecto en el siguiente frame procesado — no requiere reinicio.

        Args:
            confidence_threshold: Umbral de confianza YOLO (0.10–1.00).
            persistence_frames: Frames consecutivos para confirmar detección (1–10).
            iou_threshold: Umbral IoU para NMS en YOLO (0.10–1.00).

        Returns:
            Copia del diccionario actualizado.
        """
        with self.lock:
            self.model_params["confidence_threshold"] = float(confidence_threshold)
            self.model_params["persistence_frames"] = int(max(1, int(persistence_frames)))
            self.model_params["iou_threshold"] = float(iou_threshold)
            return dict(self.model_params)

    def get_detection_persistence_frames(self) -> int:
        """Frames consecutivos requeridos antes de marcar detected=True (mitigación de aves)."""
        try:
            raw = os.environ.get("DETECTION_PERSISTENCE_FRAMES", "3").strip()
            return max(1, int(raw))
        except (ValueError, TypeError):
            return 3

