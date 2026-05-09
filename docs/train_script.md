# Script de entrenamiento: `train.py`

## Para qué sirve

Entrena un modelo YOLO (Ultralytics) para detección de drones usando un `data.yaml` existente, guardando resultados en `runs/detect/`.

No modifica `app.py`, `config.py`, `src/` ni el dataset; solo ejecuta entrenamiento.

## Cómo ejecutarlo

Desde la raíz del proyecto:

- Entrenamiento normal:
  - `py train.py`

## Parámetros principales

- `--model` (default: `yolo26s.pt`)
  - Cambia el modelo base: `yolov8s.pt`, `yolov8m.pt`, etc.
- `--data` (default: `dataset/data.yaml`)
  - Ruta a tu archivo `data.yaml`.
- `--imgsz` (default: `1024`)
- `--epochs` (default: `100`)
- `--device` (default: `0`)
  - `0` usa la primera GPU; `cpu` para forzar CPU.
- `--batch` (default: `-1`)
  - `-1` = auto batch de Ultralytics.
- `--workers` (default: `4`)
  - En Windows se recomienda `<=4`.
- `--optimizer` (default: `auto`)
  - Permite `auto`, `AdamW`, `SGD`, `MuSGD` (si tu versión lo soporta).
- `--patience` (default: `30`)
- `--project` (default: `runs/detect`)
- `--name` (default: `drone_model_v1`)
- `--resume`
  - Reanuda entrenamiento si existe el run.
- `--cache`
  - Cachea dataset (puede consumir RAM).
- `--pretrained` / `--no-pretrained`
  - Default: pretrained habilitado.

## Ejemplos

- `data.yaml` específico:
  - `py train.py --data dataset_entrenamiento/data.yaml`
- Estable con poca RAM:
  - `py train.py --workers 0 --batch 8`
- Entrenamiento largo:
  - `py train.py --epochs 150 --patience 30`
- AdamW:
  - `py train.py --optimizer AdamW --name drone_adamw`
- SGD:
  - `py train.py --optimizer SGD --name drone_sgd`
- MuSGD (si falla, vuelve a `auto`):
  - `py train.py --optimizer MuSGD --name drone_musgd`

## Si no encuentra `data.yaml`

El script lanza:

- `FileNotFoundError: data.yaml no existe: <ruta>`

Verifica que `--data` apunte a un archivo real.

## Si `MuSGD` falla

Algunas versiones de Ultralytics no reconocen `MuSGD`. En ese caso:

- Usa `--optimizer auto` o `--optimizer AdamW` / `--optimizer SGD`.

## Salidas (best.pt / last.pt)

Ultralytics guarda los pesos típicamente en:

- `runs/detect/<name>/weights/best.pt`
- `runs/detect/<name>/weights/last.pt`

El script imprime las rutas al finalizar si existen.

## Recomendaciones Windows/GPU

- Mantén `--workers 4` o menor.
- Si hay problemas de RAM:
  - `--workers 0 --batch 8`
- Asegura que el entorno (venv) tenga `ultralytics` instalado y que tu CUDA esté disponible si usas GPU.

