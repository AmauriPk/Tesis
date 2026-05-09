from __future__ import annotations

"""
SIRAN - Script de entrenamiento YOLO (Ultralytics)

Ejemplos:
  - Entrenamiento normal:
      py train.py
  - Entrenamiento con data.yaml específico:
      py train.py --data dataset_entrenamiento/data.yaml
  - Entrenamiento estable si hay poca RAM:
      py train.py --workers 0 --batch 8
  - Entrenamiento largo:
      py train.py --epochs 150 --patience 30
  - Probar AdamW:
      py train.py --optimizer AdamW --name drone_adamw
  - Probar SGD:
      py train.py --optimizer SGD --name drone_sgd
  - Probar MuSGD (si tu versión lo soporta):
      py train.py --optimizer MuSGD --name drone_musgd
"""

import argparse
import platform
import time
from pathlib import Path

from ultralytics import YOLO


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Entrenamiento YOLO para detección de drones (SIRAN)")
    p.add_argument("--model", default="yolo26s.pt", help="Modelo base (e.g., yolo26s.pt, yolov8s.pt, yolov8m.pt)")
    p.add_argument("--data", default="dataset/data.yaml", help="Ruta relativa/absoluta a data.yaml")
    p.add_argument("--imgsz", type=int, default=1024, help="Tamaño de imagen (imgsz)")
    p.add_argument("--epochs", type=int, default=100, help="Épocas de entrenamiento")
    p.add_argument("--device", default="0", help="Dispositivo (e.g., 0, 0,1, cpu)")
    p.add_argument("--batch", type=int, default=-1, help="Batch size (-1 = auto batch de Ultralytics)")
    p.add_argument("--workers", type=int, default=4, help="Workers de DataLoader (Windows recomendado <= 4)")
    p.add_argument(
        "--optimizer",
        default="auto",
        help="Optimizer (auto, AdamW, SGD, MuSGD, ... según versión Ultralytics)",
    )
    p.add_argument("--patience", type=int, default=30, help="Early stopping patience")
    p.add_argument("--project", default="runs/detect", help="Carpeta de salida (project)")
    p.add_argument("--name", default="drone_model_v1", help="Nombre del experimento (name)")
    p.add_argument("--resume", action="store_true", help="Reanudar entrenamiento desde el último checkpoint")
    p.add_argument("--cache", action="store_true", help="Cache dataset (puede consumir RAM); default False")

    # Default True pero con opción de apagarlo explícitamente.
    p.add_argument(
        "--pretrained",
        dest="pretrained",
        action="store_true",
        default=True,
        help="Usar weights preentrenados (default: True)",
    )
    p.add_argument("--no-pretrained", dest="pretrained", action="store_false", help="No usar weights preentrenados")
    return p


def main() -> int:
    args = _build_parser().parse_args()

    project_root = Path(__file__).resolve().parent
    dataset_yaml = (project_root / args.data).resolve() if not Path(args.data).is_absolute() else Path(args.data).resolve()

    if not dataset_yaml.exists():
        raise FileNotFoundError(f"data.yaml no existe: {dataset_yaml}")

    if platform.system().lower().startswith("win") and int(args.workers) > 4:
        print("[WARN] En Windows se recomienda workers<=4 por estabilidad. Actualmente:", int(args.workers))

    if int(args.batch) == -1:
        print("[INFO] batch=-1 => Ultralytics usará auto batch.")

    optimizer = str(args.optimizer or "auto").strip() or "auto"

    print("=== SIRAN YOLO TRAIN ===")
    print("[CONFIG] project_root:", project_root)
    print("[CONFIG] data.yaml:", dataset_yaml)
    print("[CONFIG] model:", args.model)
    print("[CONFIG] device:", args.device)
    print("[CONFIG] epochs:", int(args.epochs))
    print("[CONFIG] imgsz:", int(args.imgsz))
    print("[CONFIG] batch:", int(args.batch))
    print("[CONFIG] workers:", int(args.workers))
    print("[CONFIG] optimizer:", optimizer)
    print("[CONFIG] patience:", int(args.patience))
    print("[CONFIG] project/name:", f"{args.project}/{args.name}")
    print("[CONFIG] resume:", bool(args.resume))
    print("[CONFIG] cache:", bool(args.cache))
    print("[CONFIG] pretrained:", bool(args.pretrained))

    t0 = time.time()
    model = YOLO(args.model)

    results = model.train(
        data=str(dataset_yaml),
        imgsz=int(args.imgsz),
        epochs=int(args.epochs),
        device=args.device,
        batch=int(args.batch),
        workers=int(args.workers),
        optimizer=optimizer,
        amp=True,
        patience=int(args.patience),
        lr0=0.002,
        warmup_epochs=2.0,
        augment=True,
        mosaic=1.0,
        mixup=0.1,
        scale=0.6,
        fliplr=0.5,
        project=str(args.project),
        name=str(args.name),
        exist_ok=True,
        save=True,
        plots=True,
        cache=bool(args.cache),
        resume=bool(args.resume),
        pretrained=bool(args.pretrained),
    )

    dt = time.time() - t0
    print(f"[DONE] Entrenamiento finalizado en {dt:.1f}s")

    run_dir = project_root / str(args.project) / str(args.name)
    weights_dir = run_dir / "weights"
    best_pt = weights_dir / "best.pt"
    last_pt = weights_dir / "last.pt"
    if best_pt.exists():
        print("[OUTPUT] best.pt:", best_pt)
    else:
        print("[OUTPUT][WARN] best.pt no encontrado en:", best_pt)
    if last_pt.exists():
        print("[OUTPUT] last.pt:", last_pt)
    else:
        print("[OUTPUT][WARN] last.pt no encontrado en:", last_pt)

    _ = results
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

