"""
train_yolo26.py
===============
Script reproducible para entrenar tu modelo YOLO26 con tu dataset local (formato YOLO).

Objetivo:
- Entrenar usando `dataset/data.yaml`.
- Producir pesos `best.pt` listos para usarse en `app.py` vía `YOLO_MODEL_PATH`.

Ejemplo:
  python train_yolo26.py --data dataset/data.yaml --model yolo26s.pt --epochs 100 --imgsz 640 --batch 16 --device 0

Salida típica (Ultralytics):
  runs/detect/<name>/weights/best.pt

Después, en el servidor (antes de iniciar Flask):
  PowerShell (sesión actual):
    $env:YOLO_MODEL_PATH="runs/detect/<name>/weights/best.pt"
  Persistente en Windows:
    setx YOLO_MODEL_PATH "runs/detect/<name>/weights/best.pt"
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError("Falta PyYAML. Instala: pip install pyyaml") from e

    return yaml.safe_load(path.read_text(encoding="utf-8", errors="replace")) or {}


def _dump_yaml(path: Path, payload: dict[str, Any]) -> None:
    try:
        import yaml  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError("Falta PyYAML. Instala: pip install pyyaml") from e

    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _resolve_data_yaml_to_absolute(data_yaml: Path) -> Path:
    """
    Para evitar ambigüedades de rutas relativas entre versiones,
    genera un YAML temporal con rutas ABSOLUTAS para train/val/test.
    """

    payload = _load_yaml(data_yaml)
    base = data_yaml.parent.resolve()

    def _abs(p: Any) -> str:
        if p is None:
            return ""
        p_str = str(p)
        path = Path(p_str)
        if path.is_absolute():
            return str(path)
        return str((base / path).resolve())

    for key in ("train", "val", "test"):
        if key in payload:
            payload[key] = _abs(payload[key])

    tmp = data_yaml.parent / "_data_abs.yaml"
    _dump_yaml(tmp, payload)
    return tmp.resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description="Entrenamiento YOLO26 (Ultralytics) con dataset local")
    parser.add_argument("--data", default="dataset/data.yaml", help="Ruta al data.yaml del dataset")
    parser.add_argument("--model", default="yolo26s.pt", help="Pesos base/preentrenados (p.ej. yolo26s.pt)")
    parser.add_argument("--epochs", type=int, default=100, help="Número de épocas")
    parser.add_argument("--imgsz", type=int, default=640, help="Tamaño de imagen (imgsz)")
    parser.add_argument("--batch", type=int, default=16, help="Batch size")
    parser.add_argument("--device", default="0", help="Dispositivo (0, 0,1, cpu, etc.)")
    parser.add_argument("--project", default="runs/detect", help="Directorio base de salida (Ultralytics)")
    parser.add_argument("--name", default="rpas_micro_train", help="Nombre del experimento (carpeta dentro de project)")
    parser.add_argument("--seed", type=int, default=42, help="Semilla para reproducibilidad")
    args = parser.parse_args()

    try:
        from ultralytics import YOLO  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError("Falta ultralytics. Instala: pip install ultralytics") from e

    data_yaml = Path(args.data)
    if not data_yaml.exists():
        raise FileNotFoundError(f"No existe data.yaml: {data_yaml}")

    model_path = Path(args.model)
    if not model_path.exists():
        raise FileNotFoundError(f"No existe el modelo base: {model_path}")

    data_abs = _resolve_data_yaml_to_absolute(data_yaml)

    model = YOLO(str(model_path))
    _ = model.train(
        data=str(data_abs),
        epochs=int(args.epochs),
        imgsz=int(args.imgsz),
        batch=int(args.batch),
        device=str(args.device),
        project=str(args.project),
        name=str(args.name),
        seed=int(args.seed),
        verbose=True,
    )

    best = Path(args.project) / args.name / "weights" / "best.pt"
    last = Path(args.project) / args.name / "weights" / "last.pt"

    print("\n[OK] Entrenamiento finalizado.")
    if best.exists():
        print(f"[OK] best.pt: {best}")
        print(f"[SUGERENCIA] PowerShell: $env:YOLO_MODEL_PATH=\"{best}\"")
        print(f"[SUGERENCIA] Windows persistente: setx YOLO_MODEL_PATH \"{best}\"")
    if last.exists():
        print(f"[INFO] last.pt: {last}")

    try:
        if data_abs.name == "_data_abs.yaml" and data_abs.exists():
            data_abs.unlink()
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
