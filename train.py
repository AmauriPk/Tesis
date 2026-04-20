# train.py
# Script para entrenar el modelo YOLOv8 para detección de micro drones (RPAS Micro)
# Utiliza ultralytics para YOLO, con GPU NVIDIA RTX 4060 (device=0)
# Dataset en formato YOLO: imágenes en carpetas train/val, etiquetas .txt con class_id=0
# Incluye ejemplos negativos (imágenes sin .txt) para reducir falsos positivos

from ultralytics import YOLO
from pathlib import Path

def main():
    # Cargar el modelo base YOLOv8 (puedes cambiar a yolov8n.pt, yolov8s.pt, etc.)
    model = YOLO('yolo26n.pt')  # Modelo nano para prototipo, ajusta según necesidad
    dataset_yaml = Path(__file__).resolve().parent / 'dataset' / 'data.yaml'

    # Configurar el entrenamiento
    # Parámetros obligatorios: imgsz=640, epochs=100, device=0 (GPU)
    # Data augmentation multiescala: YOLO aplica automáticamente augmentations como flip, rotate, scale
    # Para objetos pequeños, se recomienda imgsz=640 y augmentations que incluyan scale
    results = model.train(
        data=str(dataset_yaml),  # Archivo YAML que define el dataset
        imgsz=640,         # Tamaño de imagen 640x640
        epochs=30,        # Número de épocas
        device=0,          # GPU 0 (RTX 4060)
        batch=-1,          # Ajusta según memoria GPU
        workers=4,         # Número de workers para data loading
        augment=True,      # Habilitar augmentations
        scale=0.5,         # Escala para multiescala (0.5 significa 0.5x a 1.5x)
        fliplr=0.5,        # Probabilidad de flip horizontal
        flipud=0.0,        # Sin flip vertical para drones
        mosaic=1.0,        # Mosaic augmentation para diversidad
        mixup=0.0          # Sin mixup para evitar confusión en clases únicas
    )

    # El modelo entrenado se guarda en runs/detect/train/weights/best.pt
    print("Entrenamiento completado. Modelo guardado en runs/detect/train/weights/best.pt")

if __name__ == "__main__":
    main()

# Estructura del archivo data.yaml:
# Debe estar en el directorio raíz del proyecto
# Contenido ejemplo:
# train: ./dataset/train/images  # Carpeta con imágenes de entrenamiento
# val: ./dataset/val/images      # Carpeta con imágenes de validación
# nc: 1                          # Número de clases
# names: ['RPAS Micro']          # Nombre de la clase
#
# Para ejemplos negativos: Coloca imágenes sin objetos en las carpetas train/val/images
# YOLO ignorará automáticamente las imágenes sin archivos .txt correspondientes
# Asegúrate de que las etiquetas .txt estén en el mismo directorio que las imágenes,
# con el mismo nombre base (ej. image1.jpg -> image1.txt)
# Formato de etiqueta: class_id x_center y_center width height (normalizado 0-1)
