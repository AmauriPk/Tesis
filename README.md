# RPAS Micro – Prototipo de Detección de Drones (YOLO26 + RTSP/ONVIF)

Este repositorio implementa una plataforma web de **detección de drones (RPAS Micro)** basada en el **Modelo de Prototipado** (Pressman & Maxim, 2020). El sistema integra adquisición de video por **RTSP**, inferencia en **GPU** con un modelo **YOLO26 end-to-end (sin etapa NMS)** mediante `ultralytics`, y un mecanismo de **Auto-Discovery** de capacidades **ONVIF** para habilitar (o bloquear) el control de cámaras **PTZ** de forma *fail-safe*.

## Objetivo

Proveer una interfaz web responsiva para:

- Visualización en vivo del flujo RTSP (stream multipart).
- Detección asíncrona de RPAS Micro con YOLO26 (GPU estricta).
- Señalización de alertas y estado operativo.
- Control PTZ **condicionado por autodescubrimiento** (el sistema no confía en un selector manual de “PTZ/Fija”).

## Stack tecnológico

- **Backend:** Python + Flask.
- **IA (GPU):** `ultralytics` ejecutando YOLO26 sobre CUDA (`cuda:0`).
- **Visión:** OpenCV.
- **Video:** RTSP (cámaras IP), entrega web por `multipart/x-mixed-replace`.
- **ONVIF / PTZ:** `onvif-zeep` (interrogación automática de capacidades y control PTZ asíncrono).
- **Frontend:** HTML/Bootstrap + JavaScript (UI condicional por capacidades detectadas).
- **Persistencia:** SQLite (SQLAlchemy).

## Requisitos previos

### Hardware

- GPU NVIDIA con soporte CUDA (p.ej. **RTX 4060**) y drivers instalados.
- Red local con acceso a la cámara IP (RTSP/ONVIF).

### Software

- Python 3.10+ (recomendado 3.11).
- `pip` actualizado.
- (Opcional) FFmpeg instalado si se requiere transcodificación para resultados de video exportados.

### Dependencias Python

Instaladas desde `requirements.txt`, incluyendo:

- `Flask`, `Flask-Login`, `Flask-SQLAlchemy`
- `opencv-python`
- `ultralytics`
- `onvif-zeep`
- `ffmpeg-python` (opcional según entorno)

## Instalación

1. Crear entorno virtual e instalar dependencias:

   - Windows (PowerShell):
     - Crear venv: `python -m venv venv_new`
     - Activar: `.\venv_new\Scripts\Activate.ps1`
   - Linux/macOS:
     - Crear venv: `python3 -m venv venv_new`
     - Activar: `source venv_new/bin/activate`

   Luego instalar:
   - `python -m pip install -r requirements.txt`

2. Verificar configuración base:

   - `config.py` contiene parámetros RTSP/YOLO/Flask por defecto.
   - El modelo YOLO se carga desde `YOLO_CONFIG["model_path"]`; debe existir un archivo `.pt` en esa ruta.

## Ejecución

### Opción A: Inicio directo

- Ejecutar: `python app.py`
- El servidor expone la URL indicada en consola (por defecto `http://localhost:5000`).

### Opción B: Script de arranque (Windows)

- Ejecutar: `.\start_server.ps1`

## Acceso y configuración operativa

- El sistema utiliza autenticación por sesión (Flask-Login).
- En el primer arranque se crean usuarios iniciales (si la base está vacía):
  - `admin / admin123` (rol: `admin`)
  - `operador / operador123` (rol: `operator`)

Una vez autenticado, el rol `admin` puede acceder a la configuración de cámara desde la interfaz.

## Auto-Discovery ONVIF (PTZ vs Fija)

El backend interroga automáticamente el dispositivo ONVIF (capabilities y/o disponibilidad del servicio PTZ). El resultado se refleja en un estado booleano:

- Si ONVIF confirma capacidades PTZ → el sistema habilita control PTZ y tracking.
- Si ONVIF falla por cualquier motivo (conexión, credenciales, servicio ausente) → el sistema asume cámara fija (**fail-safe**) y bloquea cualquier comando PTZ.

En el frontend, el panel PTZ (joystick/botones y switch de tracking) se muestra únicamente cuando el backend reporta `is_ptz_capable = true`.

## Notas de seguridad y operación

- Se recomienda reemplazar credenciales y secretos por variables de entorno (p.ej. `FLASK_SECRET_KEY`) y eliminar valores embebidos en `config.py` antes de cualquier despliegue.
- Para uso en red, se recomienda ejecutar detrás de un reverse proxy (TLS, control de acceso, rate limiting).
- En caso de cámaras PTZ, el control se ejecuta en hilos separados para evitar degradación del stream y la inferencia.

## Documentación técnica complementaria

- API REST: `Documentacion/api_rest.md`
- Arquitectura de módulos: `Documentacion/arquitectura_modulos.md`

## Entrenamiento del modelo (dataset propio)

El dataset está en `dataset/` (formato YOLO) y el YAML principal es `dataset/data.yaml`.

Entrenar (Ultralytics):
- Opción simple (misma idea que tu `train.py`): `python train.py`
- Opción parametrizable/reproducible: `python train_yolo26.py --data dataset/data.yaml --model yolo26s.pt --epochs 100 --imgsz 640 --batch 16 --device 0 --name rpas_micro_train`

Pesos generados:
- `runs/detect/train/weights/best.pt` (si usas `train.py`)
- `runs/detect/rpas_micro_train/weights/best.pt` (si usas `train_yolo26.py`)

Para usar esos pesos en el backend, define:
- PowerShell (sesión actual): `$env:YOLO_MODEL_PATH="runs/detect/rpas_micro_train/weights/best.pt"`
- Windows persistente: `setx YOLO_MODEL_PATH "runs/detect/rpas_micro_train/weights/best.pt"`
