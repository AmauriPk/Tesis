# SIRAN — Sistema Integrado de Reconocimiento de Aeronaves No Tripuladas

> **Prototipo de tesis de ingeniería** | Visión artificial + PTZ + Flask  
> Nombre interno de desarrollo: DEPURA

---

## Descripción

SIRAN es un prototipo de sistema de visión artificial para la detección, seguimiento, análisis y registro de aeronaves no tripuladas (drones/UAS). Integra:

- Inferencia YOLO en tiempo real sobre stream RTSP
- Control automático de cámara PTZ vía ONVIF (tracking del objetivo)
- Modo de patrullaje/inspección automática
- Análisis manual de imágenes y videos
- Registro de eventos de detección con evidencias visuales
- Interfaz web con autenticación y roles

---

## Tecnologías principales

| Tecnología | Versión | Uso |
|---|---|---|
| Python | 3.11+ | Lenguaje principal |
| Flask | 2.3.x | Framework web |
| OpenCV | 4.8.x | Procesamiento de video/imagen |
| Ultralytics YOLO | 8.x | Detección de drones |
| PyTorch + CUDA | — | Inferencia en GPU |
| onvif-zeep | 0.2.x | Control PTZ ONVIF |
| SQLite | — | Base de datos local |
| FFmpeg | — | Transcodificación de video (opcional) |

---

## Requisitos previos

- Python 3.11 o superior
- (Opcional) GPU NVIDIA con CUDA para inferencia acelerada
- (Opcional) FFmpeg instalado en el sistema para compatibilidad de video en navegador
- Cámara IP con soporte RTSP (y ONVIF si se requiere control PTZ)

---

## Instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/AmauriPk/Tesis.git
cd Tesis

# 2. Crear y activar entorno virtual
python -m venv venv_new
# Windows:
venv_new\Scripts\activate
# Linux/macOS:
source venv_new/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
copy .env.example .env
# Editar .env con los valores correctos
```

---

## Configuración

Copiar `.env.example` a `.env` y configurar los valores:

```env
# Cámara RTSP
RTSP_URL=rtsp://IP:554/stream
RTSP_USERNAME=usuario
RTSP_PASSWORD=contraseña

# Control PTZ (ONVIF)
ONVIF_HOST=IP_de_la_camara
ONVIF_PORT=80
ONVIF_USERNAME=admin
ONVIF_PASSWORD=contraseña

# Modelo YOLO
YOLO_MODEL_PATH=runs/detect/weights/best.pt
YOLO_DEVICE=cuda:0

# Flask
FLASK_SECRET_KEY=cambia-esta-clave-en-produccion
FLASK_PORT=5000

# Contraseñas de usuarios (CAMBIAR ANTES DE DESPLEGAR)
DEFAULT_ADMIN_PASSWORD=admin123
DEFAULT_OPERATOR_PASSWORD=operador123
```

> **IMPORTANTE:** Cambiar las contraseñas por defecto antes de usar el sistema en red.

---

## Ejecución

```bash
# Activar el entorno virtual primero
venv_new\Scripts\activate

# Iniciar el servidor
python app.py
```

El sistema estará disponible en `http://localhost:5000`

---

## Usuarios por defecto

| Usuario | Rol | Contraseña por defecto |
|---|---|---|
| `admin` | Administrador | `admin123` (cambiar) |
| `operador` | Operador | `operador123` (cambiar) |

---

## Variables de entorno importantes

| Variable | Default | Descripción |
|---|---|---|
| `RTSP_URL` | `0` (webcam) | URL del stream RTSP de la cámara |
| `YOLO_MODEL_PATH` | `runs/detect/weights/best.pt` | Ruta al modelo YOLO entrenado |
| `YOLO_DEVICE` | `cuda:0` | Device para inferencia (cuda:0 o cpu) |
| `YOLO_CONFIDENCE` | `0.8` | Umbral de confianza inicial |
| `FLASK_SECRET_KEY` | `dev-secret` | Clave secreta de Flask (cambiar en producción) |
| `FFMPEG_BIN` | — | Ruta manual al ejecutable FFmpeg (opcional) |
| `FLASK_DEBUG` | `False` | Modo debug (nunca True en producción) |

---

## Estructura del proyecto

```
Proyecto01/
├── app.py                  # Servidor principal Flask
├── config.py               # Configuración central
├── requirements.txt        # Dependencias Python
├── .env.example            # Plantilla de configuración
├── src/
│   ├── system_core.py      # Modelos DB, PTZ, métricas
│   ├── video_processor.py  # Stream RTSP y procesamiento
│   └── services/
│       └── video_export_service.py  # Exportación de video
├── templates/              # Plantillas HTML (Flask/Jinja2)
├── static/                 # CSS, JavaScript
├── docs/
│   └── tesis/              # Documentación de tesis
└── instance/               # Base de datos SQLite (generada)
```

---

## Uso básico

### Como operador
1. Iniciar sesión con usuario `operador`
2. Pestaña **En Vivo**: visualizar stream con detecciones
3. Activar **Tracking automático** para seguir drones detectados
4. Pestaña **Análisis Manual**: subir imágenes o videos para análisis offline
5. Panel de **Alertas**: revisar detecciones recientes con evidencias

### Como administrador
1. Iniciar sesión con usuario `admin`
2. Configurar RTSP/ONVIF en el panel de cámara
3. Ajustar parámetros del modelo YOLO (confianza, IoU)
4. Gestionar dataset: clasificar imágenes capturadas
5. Exportar eventos de detección como CSV

---

## Advertencias de seguridad

- **No usar contraseñas por defecto** (`admin123`, `operador123`) en entornos de red
- **No exponer el sistema en Internet** sin configurar HTTPS
- **No subir archivos sensibles** al repositorio: `.env`, `config_camara.json`, `*.db`, `*.pt`
- El endpoint `/__diag` solo está disponible en modo debug y localhost

---

## Archivos que NO deben subirse al repositorio

Los siguientes archivos están en `.gitignore`:

```
.env
config_camara.json
*.db, *.db-shm, *.db-wal
*.pt, *.pth, *.onnx
venv_new/
uploads/
static/results/
static/evidence/
static/top_detections/
dataset_recoleccion/
dataset_entrenamiento/
runs/
```

---

## Estado del proyecto

**Estado:** Prototipo funcional de investigación

El sistema está en estado de prototipo. Las funcionalidades principales están implementadas y validadas en condiciones controladas de laboratorio. No está diseñado para despliegue en producción sin las mejoras de seguridad documentadas.

Ver `docs/tesis/limitaciones_y_alcances.md` para detalles.

---

## Notas para tesis

- Nombre formal del sistema: **SIRAN — Sistema Integrado de Reconocimiento de Aeronaves No Tripuladas**
- Documentación completa disponible en `docs/tesis/`
- El refactor del código se realiza de forma incremental; el historial de commits documenta cada paso
- El análisis de errores y plan de mejoras está en `docs/tesis/analisis_errores_y_mejoras.md`
