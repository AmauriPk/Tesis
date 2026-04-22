# 🚀 REFERENCIA RÁPIDA - Sistema RPAS Web

## ⚡ INICIO EN 3 PASOS

### 1️⃣ Verificar Sistema
```bash
python test_setup.py
```
✓ Verifica Python, GPU, YOLO, dependencias

### 2️⃣ Configurar URL RTSP
Editar `config.py` línea 7:
```python
'url': 'rtsp://tu-usuario:tu-password@tu-ip:554/stream1',
```

### 3️⃣ Iniciar Servidor
```bash
python app.py
```
O usar: `start_server.bat` (Windows CMD)

---

## 🌐 ACCESO

**URL:** http://localhost:5000

---

## 📑 ARCHIVOS PRINCIPALES

| Archivo | Tipo | Propósito |
|---------|------|----------|
| `app.py` | Python | Servidor Flask + YOLO |
| `templates/index.html` | HTML/CSS/JS | Interfaz web |
| `config.py` | Python | Configuración |
| `test_setup.py` | Python | Verificar setup |
| `requirements.txt` | Pip | Dependencias |
| `GUIA_SISTEMA_WEB.md` | Markdown | Documentación completa |
| `README_ES.md` | Markdown | Este archivo |

---

## 🎯 FUNCIONES PRINCIPALES

### Pestaña 1: Monitoreo en Vivo
- 📹 Stream RTSP en tiempo real
- 🔍 Detección YOLO automática
- ⚠️ Panel de alertas
- 📊 Estadísticas en vivo
- 📥 Descargar historial

### Pestaña 2: Detección Manual
- 📤 Subir imagen o video
- ⚙️ Procesar con YOLO
- 📊 Ver resultados
- 💾 Descargar procesado

---

## 🛠️ CONFIGURACIÓN CLAVE

**config.py:**
```python
# Línea 7: URL RTSP
'url': 'rtsp://...'

# Línea 16: Modelo YOLO
'model_path': 'runs/detect/train-10/weights/best.pt'

# Línea 22: Dispositivo GPU
'device': 'cuda:0'

# Línea 28: Resolución video
'width': 1280, 'height': 720
```

---

## 📊 API ENDPOINTS

```javascript
// Obtener estado detecciones
GET /detection_status
→ { status, detected, avg_confidence, last_update, detection_count }

// Subir y procesar
POST /upload_detect
→ { success, image/video_url, detections_count, avg_confidence }

// Historial
GET /history
→ [{ fecha, hora, confianza, fuente, x1, y1, x2, y2 }, ...]
```

---

## ⚙️ REQUISITOS PREVIOS

✅ Python 3.8+  
✅ NVIDIA GPU (RTX 4060)  
✅ CUDA Toolkit  
✅ pip (gestor de paquetes)  

---

## 🐛 COMANDOS ÚTILES

```bash
# Verificar CUDA
python -c "import torch; print(torch.cuda.is_available())"

# Instalar dependencias
pip install -r requirements.txt

# Verificar modelo YOLO existe
dir runs\detect\train-10\weights\best.pt

# Ver procesos Python
tasklist | findstr python

# Matar servidor
taskkill /IM python.exe

# Ver los últimos logs
tail -f app.log
```

---

## 🎨 COLORES Y TEMAS

| Color | Código | Uso |
|-------|--------|-----|
| Verde | #00d4aa | Acento, OK, Zona despejada |
| Rojo | #ff4444 | Alerta, Peligro, Dron detectado |
| Negro | #1a1a1a | Fondo principal |
| Gris | #2d2d2d | Secundario, Tarjetas |
| Amarillo | #ffaa00 | Warnings |

---

## 🔐 SEGURIDAD

- ✓ Validación de extensiones
- ✓ Límite tamaño: 500MB
- ✓ Sanitización nombres archivo
- ✓ BD local (sin exposición)
- ⚠️ TODO: Agregar autenticación

---

## 📈 RENDIMIENTO

| Métrica | Valor |
|---------|-------|
| Resolución | 1280x720 |
| FPS objetivo | 30 |
| Inferencia | GPU RTX 4060 |
| Actualización alertas | Cada 1s (AJAX) |
| Max upload | 500MB |

---

## 📂 ESTRUCTURA DIRECTORIOS

```
proyecto01/
├── app.py                      ← Backend
├── templates/index.html        ← Frontend
├── config.py                   ← Config
├── test_setup.py              ← Testing
├── requirements.txt            ← Deps
├── detections.db              ← BD (auto)
├── uploads/                   ← Files (auto)
├── runs/detect/train-10/
│   └── weights/best.pt        ← Modelo
└── venv_new/                  ← Virtual env
```

---

## 💡 TIPS

1. **Lento:** Reduce resolución en config.py
2. **No stream RTSP:** Verifica URL, usará webcam fallback
3. **GPU no detectada:** Instala CUDA + torch GPU
4. **Port 5000 en uso:** Cambia en config.py línea 38
5. **Muchos logs:** Desactiva debug en config.py línea 33

---

## 🆘 SOPORTE RÁPIDO

**Problema** | **Solución**
---|---
GPU no funciona | `pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118`
RTSP no conecta | Verifica URL en config.py
Puerto en uso | Cambia port en config.py
Archivo no sube | Máx 500MB, verifica extensión
Interfaz lenta | Reduce resolución video

---

## 📞 LOGS Y DEBUG

```bash
# Ver logs en tiempo real
python app.py

# Guardar logs en archivo
python app.py > server.log 2>&1

# Ver solo errores
grep -i error server.log
```

---

## ✅ CHECKLIST PRE-PRODUCCIÓN

- [ ] python test_setup.py (pasar todas pruebas)
- [ ] Cambiar URL RTSP en config.py
- [ ] Verificar modelo YOLO existe (best.pt)
- [ ] Instalar dependencias: pip install -r requirements.txt
- [ ] Verificar carpeta uploads existe (creada automáticamente)
- [ ] Probar stream en tiempo real
- [ ] Probar upload de archivo
- [ ] Revisar BD detections.db
- [ ] Configurar backups
- [ ] Documentar cambios

---

## 🎓 RECURSOS

- 📖 `GUIA_SISTEMA_WEB.md` - Guía completa
- 📝 `README_ES.md` - Este archivo
- 💻 `app.py` - Código documentado
- 🎨 `templates/index.html` - Frontend comentado

---

**¡Sistema listo para usar! 🚀**

Para preguntas: Revisa GUIA_SISTEMA_WEB.md o ejecuta `python test_setup.py`
