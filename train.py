from __future__ import annotations

import argparse
import platform
from pathlib import Path

from ultralytics import YOLO


def build_parser() -> argparse.ArgumentParser:
    """Construye los argumentos de consola para entrenar el modelo YOLO."""
    parser = argparse.ArgumentParser(description="Entrenar modelo YOLO para deteccion de drones")

    parser.add_argument("--model", default="yolo26s.pt", help="Modelo base, por ejemplo yolo26s.pt o yolov8s.pt")
    parser.add_argument("--data", default="dataset/data.yaml", help="Ruta al archivo data.yaml")
    parser.add_argument("--imgsz", type=int, default=1024, help="Tamano de imagen para entrenamiento")
    parser.add_argument("--epochs", type=int, default=30, help="Numero de epocas")
    parser.add_argument("--device", default="0", help="Dispositivo de entrenamiento: 0 para GPU o cpu")
    parser.add_argument("--batch", type=int, default=-1, help="Batch size; -1 usa auto batch de Ultralytics")
    parser.add_argument("--workers", type=int, default=4, help="Workers para carga de datos; en Windows 0 o 4 suele ser mas estable")
    parser.add_argument("--optimizer", default="auto", help="Optimizador: auto, SGD, AdamW, etc. Usa MuSGD solo si tu version lo soporta")
    parser.add_argument("--patience", type=int, default=10, help="Paciencia para early stopping")
    parser.add_argument("--project", default="runs/detect", help="Carpeta donde se guardan los resultados")
    parser.add_argument("--name", default="drone_model_v1", help="Nombre del experimento")
    parser.add_argument("--resume", action="store_true", help="Continuar entrenamiento desde el ultimo checkpoint si aplica")
    parser.add_argument("--cache", action="store_true", help="Usar cache de dataset; no recomendado si hay poca RAM")

    return parser


def main() -> None:
    """Ejecuta el entrenamiento YOLO usando rutas relativas al proyecto."""
    parser = build_parser()
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    dataset_yaml = (project_root / args.data).resolve()

    if not dataset_yaml.exists():
        raise FileNotFoundError(f"No se encontro el archivo data.yaml en: {dataset_yaml}")

    workers = int(args.workers)
    if platform.system().lower() == "windows" and workers > 4:
        print("[WARN] En Windows, workers altos pueden saturar RAM o causar fallos. Considera --workers 0 o --workers 4.")

    print("=" * 72)
    print("ENTRENAMIENTO YOLO - SIRAN")
    print(f"Proyecto raiz: {project_root}")
    print(f"Dataset YAML: {dataset_yaml}")
    print(f"Modelo base: {args.model}")
    print(f"Device: {args.device}")
    print(f"Epochs: {args.epochs}")
    print(f"Image size: {args.imgsz}")
    print(f"Batch: {args.batch}")
    print(f"Workers: {workers}")
    print(f"Optimizer: {args.optimizer}")
    print(f"Output: {args.project}/{args.name}")
    print("=" * 72)

    model = YOLO(args.model)

    model.train(
        data=str(dataset_yaml),
        imgsz=int(args.imgsz),
        epochs=int(args.epochs),
        device=str(args.device),
        batch=int(args.batch),
        workers=workers,
        optimizer=str(args.optimizer),
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
    )

    best_model = project_root / args.project / args.name / "weights" / "best.pt"
    last_model = project_root / args.project / args.name / "weights" / "last.pt"

    print("\nEntrenamiento finalizado.")
    if best_model.exists():
        print(f"Modelo best.pt guardado en: {best_model}")
    else:
        print(f"No se encontro best.pt en: {best_model}")

    if last_model.exists():
        print(f"Modelo last.pt guardado en: {last_model}")


if __name__ == "__main__":
    main()
