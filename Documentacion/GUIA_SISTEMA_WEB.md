# 🚁 Sistema Web de Detección de Drones RPAS Micro

## 📋 Descripción General

Interfaz web profesional y responsiva para **detección en tiempo real de micro drones** utilizando:
- **Backend**: Flask (Python)
- **IA/Visión**: YOLO (modelo entrenado) en GPU RTX 4060
- **Frontend**: HTML5 + CSS + JavaScript + Bootstrap 5
- **Streaming**: RTSP desde cámara Hikvision PTZ

---

## ⚙️ Instalación y Configuración

### 1. Requisitos Previos
- Python 3.8+
- GPU NVIDIA con CUDA (recomendado para máximo rendimiento)
- Pip instalado

### 2. Instalar Dependencias

```bash
# Activar entorno virtual (si existe)
cd c:\Users\amaur\Desktop\Proyecto01
venv_new\Scripts\activate

# Instalar/actualizar dependencias
pip install -r requirements.txt

# Verificar instalación
python -c "from ultralytics import YOLO; import torch; print(f'CUDA disponible: {torch.cuda.is_available()}')"
```

### 3. Configuración del Sistema

**En `app.py`, línea 29:**
```python
rtsp_url = "rtsp://admin:12345@192.168.1.108:554/stream1"  # ← CAMBIAR A TU RTSP
```

Reemplaza con la URL RTSP real de tu cámara Hikvision.

**Ruta del Modelo YOLO (línea 64 en `app.py`):**
```python
model = YOLO('runs/detect/train-10/weights/best.pt')  # Tu modelo entrenado
```

---

## 🚀 Ejecución del Servidor

### Opción 1: Ejecución Directa

```bash
# En el entorno virtual activado
python app.py
```

**Salida esperada:**
```
============================================================
🚁 SERVIDOR DE DETECCIÓN DE DRONES RPAS MICRO
============================================================
[INFO] Modelo YOLO: CARGADO EN GPU
[INFO] URL RTSP: rtsp://admin:12345@192.168.1.108:554/stream1
[INFO] Servidor Flask iniciado en: http://localhost:5000
[INFO] Interfaz disponible en: http://localhost:5000/
============================================================
```

### Opción 2: En segundo plano (PowerShell)

```powershell
# Iniciar en segundo plano
Start-Job -ScriptBlock { python app.py }

# Verificar que está corriendo
Get-Process | Where-Object { $_.Name -like "*python*" }
```

---

## 📱 Interfaz Web

Accede a: **http://localhost:5000/**

### 🎥 Pestaña 1: "Monitoreo en Vivo"

**Características:**
- ✅ Stream RTSP en tiempo real con frames procesados
- ✅ Detección automática de drones (YOLO GPU)
- ✅ Bounding boxes con etiqueta "RPAS Micro" y confianza
- ✅ Panel de alertas con:
  - Estado: "🚨 ALERTA: Dron detectado" / "✓ Zona despejada"
  - Confianza promedio en tiempo real
  - Número de objetos detectados
  - Estadísticas de sesión
- ✅ Botones para actualizar manualmente o descargar historial

**Diseño:**
- Layout responsivo: Video a la izquierda, panel de alertas a la derecha
- Colores militar/seguridad: Verde oscuro, rojo para alertas, fondo negro
- FPS mostrado en la esquina superior del video

### 📁 Pestaña 2: "Detección Manual"

**Características:**
- 📸 Subir **imágenes** (JPG, PNG)
- 🎬 Subir **videos cortos** (MP4, AVI, MOV)
- 📤 Drag & drop o selección de archivo
- ⚙️ Procesamiento con YOLO en GPU
- 📊 Resultados con detecciones dibujadas
- 💾 Descargar video procesado

**Flujo:**
1. Selecciona/arrastra archivo
2. Sistema procesa con YOLO en GPU
3. Resultado se muestra en tiempo real
4. Para videos: descarga el archivo procesado

---

## 🔌 Endpoints de la API

| Ruta | Método | Descripción |
|------|--------|-------------|
| `/` | GET | Página principal (HTML) |
| `/video_feed` | GET | Stream RTSP (multipart/x-mixed-replace) |
| `/detection_status` | GET | JSON con estado actual de detecciones |
| `/upload_detect` | POST | Procesa archivo subido |
| `/history` | GET | Historial JSON de detecciones |

### Ejemplo: Obtener estado de detecciones (AJAX)

```javascript
fetch('/detection_status')
    .then(r => r.json())
    .then(data => {
        console.log('Estado:', data.status);
        console.log('Confianza:', data.avg_confidence);
        console.log('Detectados:', data.detected);
    });
```

---

## 💾 Base de Datos

Se crea automáticamente un archivo `detections.db` (SQLite) con historial:

**Tabla: `detections`**
| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | INTEGER | ID único |
| `fecha` | TEXT | Fecha de detección |
| `hora` | TEXT | Hora de detección |
| `confianza` | REAL | Score de confianza YOLO (0-1) |
| `fuente` | TEXT | 'rtsp' o 'upload_image' o 'upload_video' |
| `x1, y1, x2, y2` | INTEGER | Coordenadas del bbox |

---

## 🎯 Características Técnicas Clave

### ✅ Optimizaciones de Rendimiento

1. **GPU Acceleration**
   - Modelo YOLO cargado en `cuda:0` (RTX 4060)
   - Inferencia en GPU para máxima velocidad

2. **Streaming Eficiente**
   - Multipart/x-mixed-replace para video en vivo
   - Compresión JPEG con calidad 80% (balance velocidad/calidad)
   - Buffer limitado para evitar acumulación

3. **Procesamiento de Archivos**
   - Redimensionamiento automático (max 1280x720)
   - Procesamiento asíncrono
   - Soporte para archivos grandes (hasta 500MB)

4. **Actualización de UI**
   - Alertas actualizadas cada 1 segundo vía AJAX
   - Sin recargas de página
   - Interfaz responsiva

### 🛡️ Seguridad

- Validación de extensiones de archivo
- Límite de tamaño de carga (500MB)
- Sanitización de nombres de archivo
- Base de datos local (sin exposición de datos)

---

## 🐛 Resolución de Problemas

### ❌ Error: "No se pudo conectar a RTSP"

**Solución:**
- Verifica que la URL RTSP es correcta
- Sistema fallará gracefully y usará webcam por defecto
- Revisa conectividad con la cámara Hikvision

### ❌ Error: "CUDA no disponible"

**Solución:**
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

Luego reinicia `app.py`.

### ❌ Interfaz carga lentamente

**Solución:**
- Verifica que la GPU está siendo usada: `nvidia-smi`
- Reduce resolución en `app.py` (línea ~150): `(640, 480)` en lugar de `(1280, 720)`

### ❌ Archivo de video no se procesa

**Solución:**
- Verifica que es MP4, AVI o MOV
- Máximo 500MB
- Usa codec H264 si es posible

---

## 📊 Estructura de Archivos

```
c:\Users\amaur\Desktop\Proyecto01\
├── app.py                    # ← Servidor Flask principal
├── templates/
│   └── index.html            # ← Interfaz web
├── requirements.txt          # ← Dependencias Python
├── detections.db             # ← Base de datos (generada automáticamente)
├── uploads/                  # ← Directorio de archivos subidos (generado automáticamente)
├── dataset/                  # ← Datos de entrenamiento
├── runs/
│   └── detect/train-10/
│       └── weights/
│           └── best.pt       # ← Modelo YOLO entrenado
└── venv_new/                 # ← Entorno virtual Python
```

---

## 🔍 Logs y Debugging

Todos los eventos se registran en consola:

```
[INFO] Cargando modelo YOLO en GPU...
[SUCCESS] Modelo YOLO cargado en GPU correctamente.
[INFO] Conectando a RTSP: rtsp://...
[INFO] Frame procesado - 23 FPS
[ERROR] En inferencia YOLO: ... (si hay errores)
```

---

## 📈 Casos de Uso

1. **Vigilancia en Tiempo Real**
   - Monitoreo continuo de zona con cámara PTZ Hikvision
   - Alertas inmediatas de detección

2. **Análisis de Incidentes**
   - Subir videos de incidentes sospechosos
   - Procesar y ver dónde se detectaron drones

3. **Entrenamiento y Pruebas**
   - Validar modelo YOLO con nuevos datos
   - Ajustar umbrales de confianza

---

## 🚀 Mejoras Futuras

- [ ] Integración con notificaciones Telegram/Email
- [ ] Grabación automática de eventos
- [ ] Panel de control de cámara PTZ (pan/tilt/zoom)
- [ ] Multi-cámara soportadas
- [ ] WebSockets para tiempo real (en lugar de AJAX)
- [ ] Exportar reportes en PDF
- [ ] Almacenamiento en nube

---

## 📧 Soporte

Revisa los logs en consola para más detalles. Sistema completo y listo para producción.

---

**¡Sistema de detección de drones RPAS Micro en vivo! 🎯**
