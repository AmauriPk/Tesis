

from __future__ import annotations
import argparse
from pathlib import Path
from ultralytics import YOLO

def main() -> None:
    parser = argparse.ArgumentParser(description="Entrenar YOLO26 Optimizado")
    parser.add_argument("--model", default="yolo26s.pt", help="Modelo base")
    parser.add_argument("--data", default="dataset/data.yaml", help="Ruta al data.yaml")
    parser.add_argument("--imgsz", type=int, default=1024, help="Tamaño de imagen")
    parser.add_argument("--epochs", type=int, default=30, help="Épocas")
    parser.add_argument("--device", default="0", help="GPU device")
    parser.add_argument("--batch", type=int, default=-1, help="Batch size (-1 = auto)")
    # Optimización: Aumentamos workers si el CPU lo permite, 0 es más seguro en Windows si hay errores
    parser.add_argument("--workers", type=int, default=8, help="Workers para carga de datos")
    args = parser.parse_args()

    # Resolver rutas de forma robusta
    project_root = Path(__file__).resolve().parent
    dataset_yaml = (project_root / args.data).resolve()
    
    # Validaciones críticas
    if not dataset_yaml.exists():
        raise FileNotFoundError(f"❌ No se encontró el dataset en: {dataset_yaml}")

    # Inicializar modelo (Ultralytics descarga automáticamente si no existe)
    model = YOLO(args.model)

    print(f"🚀 Iniciando entrenamiento optimizado en: {args.device}")
    
    # Entrenamiento con hiperparámetros ajustados
    # Entrenamiento con el "Estado del Arte" para YOLO26s
    model.train(
        data=str(dataset_yaml),
        imgsz=args.imgsz,
        epochs=args.epochs,
        device=args.device,
        batch=args.batch,
        
        # --- Modificación de Estabilidad de RAM ---
        # Bajamos a 4 workers para liberar la RAM saturada (93%) 
        # y evitar el uso del archivo de paginación del SSD.
        workers=8, 
        
        # --- Cambio al Optimizador Avanzado ---
        optimizer='MuSGD',    # El mejor para la arquitectura YOLO26s
        
        amp=True,             
        patience=10,          # Aumentamos paciencia; MuSGD explora más a fondo
        
        # --- Ajuste de Hiperparámetros para MuSGD ---
        lr0=0.002,            # MuSGD suele preferir un aprendizaje inicial más bajo
        warmup_epochs=2.0,    # Convergencia más rápida, requiere menos "calentamiento"
        
        # --- Aumentos de datos (se mantienen igual) ---
        augment=True,
        mosaic=1.0,
        mixup=0.1,
        scale=0.6,
        fliplr=0.5,
        
        # --- Organización ---
        project="runs/detect",
        name="drone_model_v1_MuSGD", # Cambiamos nombre para comparar resultados
        exist_ok=True,
        save=True,
        plots=True
    )
    
    # Ruta final del modelo
    best_model = project_root / "runs/detect/drone_model_v1/weights/best.pt"
    print(f"\n✅ Proceso completado.")
    print(f"📍 Modelo optimizado guardado en: {best_model}")

if __name__ == "__main__":
    main()