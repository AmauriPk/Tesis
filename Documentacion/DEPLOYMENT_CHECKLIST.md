# 📋 CHECKLIST DE DESPLIEGUE Y OPTIMIZACIONES

## ✅ PRE-DESPLIEGUE

### 1. Verificación de Dependencias
- [ ] Python 3.8+ instalado
- [ ] Entorno virtual activado (venv_new)
- [ ] `pip install -r requirements.txt` ejecutado
- [ ] CUDA Toolkit 11.8+ instalado (para GPU)
- [ ] cuDNN compatibles instalados

### 2. Verificación de Hardware
- [ ] GPU NVIDIA detectada (`nvidia-smi` en terminal)
- [ ] RTX 4060 disponible
- [ ] Al menos 4GB VRAM libre
- [ ] CPU con 4+ cores

### 3. Configuración del Proyecto
- [ ] URL RTSP actualizada en `config.py`
- [ ] Ruta modelo YOLO correcta: `runs/detect/train-10/weights/best.pt`
- [ ] Puerto 5000 disponible (o cambiar en config.py)
- [ ] Directorio `uploads/` creado
- [ ] Directorio `templates/` existe con `index.html`

### 4. Verificación de Archivos
- [ ] `app.py` existe
- [ ] `templates/index.html` existe
- [ ] `config.py` existe
- [ ] `requirements.txt` actualizado
- [ ] Modelo YOLO (`best.pt`) presente

### 5. Testing
- [ ] Ejecutado `python test_setup.py` (todos los checks ✓)
- [ ] Stream RTSP funciona (sin errores)
- [ ] Carga de modelo YOLO exitosa
- [ ] Base de datos SQLite se crea
- [ ] Upload de archivos funcionando

---

## 🚀 DESPLIEGUE

### Opción A: Ejecución Local (Desarrollo)

```bash
# 1. Activar entorno
venv_new\Scripts\activate.bat

# 2. Instalar deps
pip install -r requirements.txt

# 3. Ejecutar
python app.py
```

### Opción B: Ejecutar en Background (Windows)

```powershell
# PowerShell - ejecutar en background
Start-Job -ScriptBlock { 
    cd c:\Users\amaur\Desktop\Proyecto01
    python app.py
}

# Verificar que corre
Get-Job
```

### Opción C: Servicio Windows (Avanzado)

Para ejecutar como servicio Windows, usar `NSSM`:

```bash
# Descargar NSSM y luego:
nssm install RPAS_Server "C:\Users\amaur\Desktop\Proyecto01\venv_new\Scripts\python.exe" "app.py"
nssm start RPAS_Server
```

---

## ⚡ OPTIMIZACIONES DE RENDIMIENTO

### 1. GPU - Inferencia Rápida
```python
# En app.py ya implementado:
model.to('cuda:0')
results = yolo_model(frame, device='cuda:0', conf=0.5, verbose=False)
```

### 2. Compresión de Video Stream
```python
# Aumentar compresión JPEG (menos bandwidth)
# En app.py línea ~180
ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])  # 70 vs 80
```

### 3. Reducir Resolución
```python
# En config.py:
VIDEO_CONFIG = {
    'width': 960,      # Reducir de 1280
    'height': 540,     # Reducir de 720
    'fps': 20,         # Reducir de 30
}
```

### 4. Procesar Frames Alternos
```python
# En app.py, agregar:
if frame_count % 2 == 0:  # Procesar cada 2 frames
    results = yolo_model(frame, ...)
```

### 5. Aumentar Buffer Size
```python
# En app.py línea ~120
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Mantener bajo para latencia
```

### 6. Limpieza de Memoria
```python
# En app.py, agregar periódicamente:
import gc
gc.collect()
torch.cuda.empty_cache()
```

---

## 🔧 CONFIGURACIÓN AVANZADA

### Multi-GPU (si tienes varias NVIDIA)
```python
# En app.py línea 64
model.to('cuda:1')  # Usar GPU 2 en lugar de GPU 1
```

### CPU Fallback (si GPU falla)
```python
# En app.py línea 64
device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
model.to(device)
```

### Aumentar Límite de Upload
```python
# En app.py línea 13
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # 1GB
```

### Cambiar Puerto
```python
# En app.py línea ~530
app.run(host='0.0.0.0', port=8080)  # Usar puerto 8080
```

---

## 📊 MONITOREO

### Ver Uso de GPU en Tiempo Real
```bash
# En terminal (requiere NVIDIA drivers)
nvidia-smi -l 1
```

### Ver Proceso Python
```bash
tasklist | findstr python
```

### Ver Puerto en Uso
```bash
netstat -ano | findstr :5000
```

### Verificar BD
```bash
sqlite3 detections.db "SELECT COUNT(*) FROM detections;"
```

---

## 🛡️ SEGURIDAD

### 1. Cambiar Puerto Default
```python
# De: port=5000 a: port=8080
app.run(debug=False, host='0.0.0.0', port=8080)
```

### 2. Deshabilitar Debug
```python
# Verificar que esté:
app.run(debug=False, ...)  # No debug en producción
```

### 3. Validación de Archivos
```python
# Ya implementado en app.py - verificar extensiones:
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'mp4', 'avi', 'mov'}
```

### 4. Límite de Tamaño
```python
# Ya implementado: máx 500MB
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024
```

### 5. HTTPS (Opcional - Producción)
```bash
# Generar certificado autofirmado:
pip install pyopenssl
python -c "import ssl; ssl._create_default_https_context = ssl._create_unverified_context"

# En app.py:
app.run(ssl_context=('cert.pem', 'key.pem'))
```

---

## 🐛 DEBUGGING

### Habilitar Logs Detallados
```python
# En app.py línea 64 cambiar:
model = YOLO('best.pt')
model.verbose = True  # Agregado

# En inferencia:
results = yolo_model(frame, device='cuda:0', verbose=True)  # Cambiar a True
```

### Guardar Logs en Archivo
```bash
# Ejecutar con redirección:
python app.py > logs.txt 2>&1

# O en PowerShell:
python app.py | Tee-Object -FilePath logs.txt
```

### Debugger Python
```python
# En app.py donde quieras inspeccionar:
import pdb
pdb.set_trace()  # Pausa ejecución
```

---

## 📈 CASOS DE USO OPTIMIZADOS

### Caso 1: Máximo Rendimiento (Monitoreo 24/7)
```python
VIDEO_CONFIG = {
    'width': 960,
    'height': 540,
    'fps': 15,
    'jpeg_quality': 60,
}
YOLO_CONFIG = {
    'confidence': 0.4,  # Más sensible
}
```

### Caso 2: Máxima Calidad (Análisis Detallado)
```python
VIDEO_CONFIG = {
    'width': 1920,
    'height': 1080,
    'fps': 30,
    'jpeg_quality': 95,
}
YOLO_CONFIG = {
    'confidence': 0.7,  # Más conservador
}
```

### Caso 3: Balance (Recomendado)
```python
VIDEO_CONFIG = {
    'width': 1280,
    'height': 720,
    'fps': 25,
    'jpeg_quality': 80,
}
YOLO_CONFIG = {
    'confidence': 0.5,
}
```

---

## 🚨 TROUBLESHOOTING

| Error | Causa | Solución |
|-------|-------|----------|
| `CUDA out of memory` | Modelo muy grande | Reducir batch size o resolución |
| `Connection refused` | Puerto en uso | Cambiar puerto en config |
| `No RTSP stream` | URL incorrecta | Verificar URL RTSP en config |
| `Slow inference` | CPU usado | Verificar `nvidia-smi` |
| `File too large` | Upload >500MB | Aumentar límite en app.py |

---

## 📦 BACKUP Y MANTENIMIENTO

### Backup de Base de Datos
```bash
# Copiar diariamente
copy detections.db detections_backup_%date:~0,10%.db
```

### Limpiar Uploads Antiguos
```python
# Agregar a app.py:
import os
from datetime import datetime, timedelta

def cleanup_old_uploads(days=7):
    uploads_dir = 'uploads'
    cutoff_time = datetime.now() - timedelta(days=days)
    
    for filename in os.listdir(uploads_dir):
        filepath = os.path.join(uploads_dir, filename)
        if os.path.getmtime(filepath) < cutoff_time.timestamp():
            os.remove(filepath)
```

### Rotación de Logs
```bash
# Crear logs.txt y rotar cada semana
# Windows Task Scheduler: ejecutar cleanup script
```

---

## 🎯 LISTA DE VERIFICACIÓN FINAL

Pre-lanzamiento:
- [ ] test_setup.py pasa 100%
- [ ] RTSP stream funciona
- [ ] GPU detectada y funciona
- [ ] Upload de archivos OK
- [ ] Interfaz responsive
- [ ] Base de datos se crea
- [ ] Histórico se guarda
- [ ] Sin errores en consola

---

## 📞 CONTACTO Y SOPORTE

- **Logs:** Revisar consola durante ejecución
- **Testing:** Ejecutar `python test_setup.py`
- **Documentación:** Ver `GUIA_SISTEMA_WEB.md`
- **Configuración:** Editar `config.py`

---

**¡Sistema optimizado y listo para producción! 🚀**
