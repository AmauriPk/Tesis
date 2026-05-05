"""
backend_rules.py
================
Reglas puras (sin efectos secundarios) reutilizables por el backend y por tests.

Motivación:
- El backend principal (Flask) contiene hilos, workers y estado global; importarlo en tests
  puede disparar efectos secundarios no deseados.
- Estas funciones encapsulan lógica crítica del prototipo para poder validarla con pytest
  de forma rápida y determinista.

Reglas implementadas (según el prototipo):
1) Regla "Enjambre": si hay múltiples detecciones, priorizar el bbox MÁS GRANDE.
2) Fail-safe ONVIF: si la cámara NO es PTZ (fija), rechazar cualquier movimiento mecánico.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class Detection:
    """
    Representación mínima de una detección para reglas de priorización.

    Nota:
    - En el backend real, una detección suele ser un dict tipo:
      {"confidence": float, "bbox": (x1, y1, x2, y2), ...}
    - Aquí se define una forma explícita para facilitar pruebas y validaciones.
    """

    bbox: tuple[int, int, int, int]
    confidence: float | None = None
    cls: str | None = None


def bbox_area(bbox_xyxy: tuple[int, int, int, int]) -> int:
    """
    Calcula el área (en píxeles^2) de un bounding box en formato XYXY.

    Args:
        bbox_xyxy: (x1, y1, x2, y2)

    Returns:
        Área no-negativa. Si x2 < x1 o y2 < y1, el área se considera 0.
    """

    x1, y1, x2, y2 = bbox_xyxy
    return max(0, int(x2) - int(x1)) * max(0, int(y2) - int(y1))


def select_priority_detection(detection_list: list[dict[str, Any]] | Iterable[Detection]) -> Any | None:
    """
    Regla "Enjambre": prioriza el bbox MÁS GRANDE.

    - Si `detection_list` está vacío, retorna None.
    - Acepta:
      - lista de dicts (backend): cada dict debe tener clave "bbox".
      - iterable de `Detection` (tests / uso estructurado).
    """

    detections = list(detection_list)
    if not detections:
        return None

    first = detections[0]
    if isinstance(first, Detection):
        return max(detections, key=lambda d: bbox_area(d.bbox))

    # Asumimos dict (backend).
    return max(detections, key=lambda d: bbox_area(tuple(d["bbox"])))


def should_allow_ptz_move(*, is_ptz_capable: bool) -> bool:
    """
    Fail-safe ONVIF:
    - Si el autodescubrimiento ONVIF determina que NO hay PTZ, el movimiento debe bloquearse.
    """

    return bool(is_ptz_capable)


def assert_ptz_capable(*, is_ptz_capable: bool) -> None:
    """
    Variante para backend:
    - Lanza PermissionError si la cámara no es PTZ.
    - Permite que Flask convierta esto en HTTP 403 o la capa superior lo maneje.
    """

    if not should_allow_ptz_move(is_ptz_capable=is_ptz_capable):
        raise PermissionError("PTZ no disponible (fail-safe ONVIF: cámara fija).")
    
