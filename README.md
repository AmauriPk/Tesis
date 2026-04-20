# Prototipo de Detección de Micro Drones (RPAS Micro)

Este proyecto implementa un sistema de detección en tiempo real de micro drones usando YOLOv8, con aceleración GPU en NVIDIA RTX 5070 Laptop GPU (CUDA 12.4).

## Requisitos

- Python 3.11
- GPU NVIDIA con CUDA 12.4 (RTX 40 series o superior)
- Cámara IP Hikvision DS-2DE5425IWG1-E conectada vía RTSP

## Instalación

1. Crear entorno virtual:
   ```
   python -m venv venv_new
   ```

2. Activar entorno virtual:
   - Windows: `venv_new\Scripts\activate` (o usar `.\venv_new\Scripts\python.exe` directamente)
   - Linux/Mac: `source venv_new/bin/activate`

3. Instalar dependencias:
   ```
   .\venv_new\Scripts\python.exe -m pip install -r requirements.txt
   ```

   Para PyTorch con CUDA (necesario para GPU):
   ```
   .\venv_new\Scripts\python.exe -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
   ```

4. Verificar instalación:
   ```
   .\venv_new\Scripts\python.exe check_env.py
   ```
   Debería mostrar "✓ YOLO funciona en cuda"

## Estructura del Dataset

- Formato YOLO
- Una clase: "RPAS Micro" (class_id = 0)
- Incluir imágenes negativas (sin etiquetas .txt) para reducir falsos positivos

Estructura esperada:
```
dataset/
├── train/
│   ├── images/  # Imágenes de entrenamiento
│   └── labels/  # Etiquetas .txt correspondientes
├── val/
│   ├── images/  # Imágenes de validación
│   └── labels/  # Etiquetas .txt correspondientes
```

Archivo `data.yaml` (ya creado):
```
train: ./dataset/train/images
val: ./dataset/val/images
nc: 1
names: ['RPAS Micro']
```

## Entrenamiento

1. Coloca tu dataset en la carpeta `dataset/`
2. Ejecuta el entrenamiento:
   ```
   python train.py
   ```

Parámetros configurados:
- imgsz: 640x640
- epochs: 100
- device: 0 (GPU)
- Augmentations: multiescala, flip, mosaic, etc.

El modelo entrenado se guardará en `runs/detect/train/weights/best.pt`

## Inferencia en Tiempo Real

1. Ajusta la URL RTSP en `detect.py`:
   ```python
   rtsp_url = "rtsp://usuario:password@IP:puerto/Streaming/Channels/101"
   ```

2. Ejecuta la detección:
   ```
   python detect.py
   ```

Características:
- Procesamiento frame-by-frame
- Bounding boxes con etiqueta y confianza
- Lógica de zona central para simular control PTZ
- Registro en SQLite (`detections.db`) para detecciones > 0.60

## Integración con Flask

El código está modularizado:
- `load_model()`: Carga el modelo
- `process_frame()`: Procesa un frame
- `save_detection()`: Guarda en DB

Para Flask, usa hilos para el procesamiento de video.

## Notas Técnicas

- Tolerancia de zona central: 20% del ancho/alto de la imagen
- Persistencia: Solo registra si confianza > 0.60
- Base de datos: SQLite con tabla detections (fecha, hora, confianza, coordenadas)

## Solución de Problemas

- Si CUDA no está disponible, el código funcionará en CPU (más lento)
- Verifica la URL RTSP de tu cámara Hikvision
- Asegura que el dataset esté en formato YOLO correctoA<Zqsw!2|1|32>