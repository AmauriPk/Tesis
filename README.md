# SIRAN — Sistema Integrado de Reconocimiento de Aeronaves No Tripuladas

> **Prototipo de tesis de Ingeniería Militar en Computación e Informática**  
> Visión artificial + YOLO + cámara IP/PTZ + RTSP + ONVIF + Flask

---

## 1. Descripción general

SIRAN es un prototipo de software para la detección, seguimiento, análisis y registro de RPAS Micro mediante visión artificial. El sistema está orientado a apoyar actividades de vigilancia y protección mediante una cámara IP/PTZ y un modelo YOLO entrenado para identificar drones en imágenes y video.

El proyecto integra:

- Detección de RPAS Micro con modelo YOLO entrenado.
- Procesamiento de video en tiempo real desde cámara RTSP.
- Confirmación de detecciones por persistencia temporal.
- Control PTZ manual y seguimiento automático mediante ONVIF.
- Readquisición PTZ cuando el objetivo se pierde temporalmente.
- Análisis offline de imágenes y videos.
- Registro de métricas, eventos, alertas y evidencias visuales.
- Interfaz web con roles de operador y administrador.
- Scripts de evaluación para alimentar el Capítulo IV de la tesis.

---

## 2. Relación con la tesis

Este repositorio corresponde al prototipo desarrollado para la tesis:

**“Prototipo de sistema de visión artificial para la detección de un Sistema de Aeronaves Piloteadas a Distancia Micro, en apoyo a operaciones militares”.**

La correspondencia principal entre tesis y código es la siguiente:

| Elemento de tesis | Implementación en el proyecto |
|---|---|
| Captura de video RTSP | `RTSPLatestFrameReader` en `src/video_processor.py` |
| Inferencia YOLO | `load_yolo_model()` y `LiveVideoProcessor` |
| Validación por confianza y persistencia | `ModelParamsService` y `DetectionPersistence` |
| Seguimiento PTZ | `TrackingPTZWorker` y `PTZCommandWorker` |
| Control ONVIF | `PTZController` y servicios PTZ |
| Interfaz del operador | `templates/operador.html` y blueprints en `src/routes/` |
| Panel administrador | `templates/admin.html` y rutas de configuración |
| Registro de eventos | `DetectionEventWriter`, SQLite y endpoints de eventos |
| Evaluación experimental | Carpeta `evaluacion/scripts/` |
| Evidencias para Capítulo IV | `evaluacion/reporte_capitulo4.html`, resultados, curvas y tablas generadas |

---

## 3. Estado actual del proyecto

**Estado:** prototipo funcional de investigación.

El sistema ya cuenta con los módulos principales implementados y documentados. Sin embargo, no debe considerarse un sistema de producción sin aplicar mejoras adicionales de seguridad, pruebas automatizadas, endurecimiento de despliegue y limpieza final de deuda técnica.

### Funcionalidades implementadas

| Área | Estado |
|---|---|
| Login con roles | Implementado |
| Visualización en vivo | Implementado |
| Inferencia YOLO en stream RTSP | Implementado |
| Parámetros del modelo ajustables en caliente | Implementado |
| Persistencia temporal para reducir falsos positivos | Implementado |
| Control PTZ manual | Implementado |
| Seguimiento automático PTZ | Implementado |
| Readquisición PTZ | Implementado |
| Análisis offline de imágenes y videos | Implementado |
| Exportación y consulta de eventos | Implementado |
| Gestión básica de dataset recolectado | Implementado |
| Scripts de evaluación | Implementados |
| Preparación para producción | Pendiente |
| Pruebas unitarias completas | Pendiente |

---

## 4. Tecnologías principales

| Tecnología | Uso |
|---|---|
| Python 3.11+ | Lenguaje principal |
| Flask | Aplicación web |
| Flask-Login | Autenticación y sesiones |
| Flask-SQLAlchemy | Base de datos de usuarios y cámara |
| SQLite | Registro local de métricas, eventos y detecciones |
| OpenCV | Captura, procesamiento y codificación de video |
| Ultralytics YOLO | Inferencia del modelo de detección |
| PyTorch + CUDA | Aceleración por GPU |
| ONVIF / onvif-zeep | Control PTZ interoperable |
| FFmpeg / imageio-ffmpeg | Conversión de videos para navegador |
| NumPy / SciPy | Cálculos auxiliares |
| Pytest | Pruebas futuras |

---

## 5. Requisitos previos

- Python 3.11 o superior.
- Cámara IP con RTSP.
- Cámara PTZ compatible con ONVIF si se usará seguimiento automático.
- GPU NVIDIA con CUDA para inferencia acelerada.
- FFmpeg instalado o configurado mediante `FFMPEG_BIN` para reproducir videos procesados en navegador.

> El sistema puede caer a CPU si no hay CUDA disponible, pero el rendimiento esperado de tiempo real depende de GPU.

---

## 6. Instalación rápida

```bash
# 1. Clonar el repositorio
git clone https://github.com/AmauriPk/Tesis.git
cd Tesis

# 2. Crear entorno virtual
python -m venv venv_new

# 3. Activar entorno virtual en Windows
venv_new\Scripts\activate

# 4. Instalar dependencias
pip install -r requirements.txt

# 5. Copiar archivo de configuración
copy .env.example .env
```

En Linux/macOS:

```bash
python -m venv venv_new
source venv_new/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

---

## 7. Configuración mínima `.env`

Ejemplo base:

```env
# Cámara RTSP
RTSP_URL=rtsp://usuario:contraseña@IP_CAMARA:554/Streaming/Channels/101
RTSP_USERNAME=usuario
RTSP_PASSWORD=contraseña
RTSP_TIMEOUT=5
RTSP_BUFFER_SIZE=1

# ONVIF / PTZ
ONVIF_HOST=IP_CAMARA
ONVIF_PORT=80
ONVIF_USERNAME=usuario
ONVIF_PASSWORD=contraseña

# Modelo YOLO
YOLO_MODEL_PATH=runs/detect/weights/best.pt
YOLO_DEVICE=cuda:0
YOLO_VERBOSE=False

# Parámetros operativos del modelo
CONFIDENCE_THRESHOLD=0.60
PERSISTENCE_FRAMES=3
IOU_THRESHOLD=0.45
DETECTION_PERSISTENCE_FRAMES=3

# Video
VIDEO_WIDTH=1280
VIDEO_HEIGHT=720
VIDEO_FPS=30
JPEG_QUALITY=80
INFERENCE_INTERVAL=1

# Flask
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
FLASK_DEBUG=False
SESSION_IDLE_TIMEOUT_SECONDS=900

# Seguridad
SIRAN_ENCRYPT_KEY=
DEFAULT_ADMIN_PASSWORD=cambiar_admin
DEFAULT_OPERATOR_PASSWORD=cambiar_operador
```

Para generar una clave de cifrado Fernet:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## 8. Ejecución

```bash
venv_new\Scripts\activate
python app.py
```

El sistema quedará disponible en:

```text
http://localhost:5000
```

---

## 9. Usuarios y roles

| Rol | Uso principal |
|---|---|
| Administrador | Configurar cámara, parámetros del modelo, dataset y exportación de eventos |
| Operador | Visualizar video, activar seguimiento, usar PTZ manual y analizar archivos |

> Las contraseñas por defecto deben cambiarse antes de cualquier demostración en red.

---

## 10. Estructura principal del proyecto

```text
Tesis/
├── app.py                         # Punto de entrada Flask e inicialización de servicios
├── config.py                      # Configuración central por variables de entorno
├── requirements.txt               # Dependencias Python
├── train.py                       # Entrenamiento del modelo
├── src/
│   ├── system_core.py             # Modelos, utilidades, PTZ base, métricas
│   ├── video_processor.py         # RTSP, inferencia en vivo, MJPEG, persistencia
│   ├── routes/                    # Blueprints Flask
│   │   ├── analysis.py            # Análisis offline de imagen/video
│   │   ├── events.py              # Eventos, alertas y exportación CSV
│   │   ├── dataset.py             # Gestión del dataset recolectado
│   │   ├── admin_camera.py        # Configuración de cámara
│   │   ├── auth.py                # Login/logout
│   │   ├── dashboard.py           # Vista operador y métricas live
│   │   ├── model_params.py        # Ajuste de parámetros YOLO
│   │   ├── ptz_manual.py          # Joystick PTZ manual
│   │   └── automation.py          # Tracking e inspección automática
│   └── services/                  # Servicios desacoplados
│       ├── model_params_service.py
│       ├── yolo_model_service.py
│       ├── ptz_service.py
│       ├── ptz_worker_service.py
│       ├── tracking_worker_service.py
│       ├── inspection_patrol_service.py
│       ├── detection_event_service.py
│       ├── camera_config_service.py
│       └── video_export_service.py
├── templates/                     # Interfaz HTML/Jinja2
├── static/                        # Archivos estáticos de interfaz
├── docs/                          # Documentación técnica y de tesis
├── evaluacion/                    # Scripts y reporte del Capítulo IV
└── instance/                      # Base de datos local generada, no versionar
```

---

## 11. Flujo operativo

### Operador

1. Inicia sesión.
2. Abre el panel de video en vivo.
3. Verifica conexión RTSP.
4. Activa seguimiento automático si la cámara es PTZ.
5. Usa PTZ manual cuando sea necesario.
6. Revisa alertas recientes y eventos.
7. Ejecuta análisis offline de imágenes o videos cuando se requiera.

### Administrador

1. Configura RTSP y ONVIF.
2. Prueba conexión de cámara.
3. Ajusta confianza, IoU y persistencia.
4. Consulta eventos históricos.
5. Exporta registros CSV.
6. Clasifica imágenes recolectadas para mejora del dataset.

---

## 12. Evaluación para Capítulo IV

La carpeta `evaluacion/scripts/` contiene scripts para obtener evidencias, métricas y tablas de resultados.

| Script | Propósito |
|---|---|
| `eval_01_dataset.py` | Composición y validación del dataset |
| `eval_02_metricas_modelo.py` | Métricas del modelo entrenado |
| `eval_03_curvas.py` | Curvas de entrenamiento y gráficas |
| `eval_04_rendimiento_live.py` | FPS y latencia en vivo |
| `eval_05_sesion_prueba.py` | Registro de sesión experimental |
| `eval_06_por_distancia.py` | Resultados por distancia |
| `eval_07_falsos_positivos.py` | Objetos distractores y falsos positivos |
| `eval_08_iluminacion.py` | Condiciones de iluminación |
| `eval_09_ptz_tracking.py` | Seguimiento PTZ |
| `eval_10_cumplimiento_rf.py` | Cumplimiento de requerimientos |
| `eval_11_reporte_final.py` | Consolidación del reporte final |

---

## 13. Archivos que no deben subirse

El repositorio debe mantenerse ligero. No subir:

```text
.env
config_camara.json
instance/
uploads/
logs/
*.db
*.db-shm
*.db-wal
*.sqlite
*.pt
*.pth
*.onnx
*.tflite
*.mp4
*.avi
*.mov
runs/
dataset/
dataset_recoleccion/
dataset_entrenamiento/
detections_frames/
static/results/
static/evidence/
static/top_detections/
venv/
venv_new/
```

Antes de hacer `git push`, verificar:

```bash
git status --short
git ls-files | findstr /i "\.pt .mp4 .avi .mov .db runs dataset venv"
```

---

## 14. Limpieza técnica pendiente

Hay análisis previos en `docs/` sobre deuda técnica y código posiblemente muerto. La recomendación actual es no eliminar módulos críticos antes de una defensa o demostración sin ejecutar pruebas.

### Puede revisarse para eliminar después de validar con `grep` y `py_compile`

- Funciones PTZ antiguas duplicadas en `app.py`.
- Helpers no usados en `src/system_core.py`.
- Funciones PTZ/bbox antiguas en `src/video_processor.py`.
- Código comentado u obsoleto posterior al refactor.
- Documentación técnica duplicada o desactualizada en `docs/`.

### No eliminar

- `app.py` como punto de arranque.
- `config.py`.
- `src/video_processor.py`.
- `src/system_core.py`.
- `src/routes/`.
- `src/services/tracking_worker_service.py`.
- `src/services/ptz_worker_service.py`.
- `src/services/detection_event_service.py`.
- `src/services/inspection_patrol_service.py`.
- `evaluacion/scripts/` mientras se esté cerrando el Capítulo IV.

Validación mínima antes de cualquier limpieza:

```bash
py -m py_compile app.py src/routes/*.py src/services/*.py src/system_core.py src/video_processor.py
```

---

## 15. Seguridad

- Cambiar contraseñas por defecto.
- No exponer el servidor directamente a Internet.
- No activar `FLASK_DEBUG=True` fuera de localhost.
- Configurar `SIRAN_ENCRYPT_KEY` antes de guardar credenciales reales.
- No subir `.env`, bases de datos, modelos entrenados ni evidencias.
- Usar red local controlada durante pruebas.

---

## 16. Documentación útil

| Documento | Contenido |
|---|---|
| `docs/Manual_Tecnico_SIRAN.md` | Manual técnico del sistema |
| `docs/tesis/arquitectura_sistema.md` | Arquitectura para tesis |
| `docs/tesis/mapa_endpoints.md` | Endpoints del sistema |
| `docs/tesis/limitaciones_y_alcances.md` | Alcances y limitaciones |
| `docs/tesis/analisis_errores_y_mejoras.md` | Errores, mejoras y deuda técnica |
| `docs/analisis_codigo_muerto.md` | Código posiblemente muerto |
| `docs/plan_limpieza_y_mejora_codigo.md` | Plan de limpieza y mejora |

---

## 17. Nota final

SIRAN es un prototipo académico funcional. Para efectos de tesis, el sistema debe presentarse como una solución experimental viable, validada en condiciones controladas y con limitaciones identificadas. Para uso operativo real, requiere endurecimiento, pruebas de campo ampliadas, validación con más condiciones ambientales y revisión institucional de seguridad.
