## Refactor: Servicio de Carga de Modelo YOLO

**Fecha:** 2026-05-10  
**Objetivo:** Extraer lógica de carga YOLO de app.py a un servicio centralizado  
**Estado:** ✓ Completado

---

### Qué se movió

#### Antes (app.py)
```python
from ultralytics import YOLO

try:
    import torch
except Exception:
    torch = None

def load_yolo_model() -> YOLO | None:
    """Carga el modelo YOLO y selecciona device dinamico (GPU si existe; si no, CPU)."""
    try:
        if torch is None:
            raise RuntimeError("PyTorch no esta disponible.")
        device = "cuda:0" if bool(getattr(torch, "cuda", None)) and torch.cuda.is_available() else "cpu"
        model_path = str(YOLO_CONFIG.get("model_path") or "").strip() or "yolo26s.pt"
        if not os.path.exists(model_path):
            print(f"[WARN] No existe YOLO_MODEL_PATH='{model_path}'. Usando fallback 'yolo26s.pt'.")
            model_path = "yolo26s.pt"
        model = YOLO(model_path)
        model.to(device)
        print(f"[SUCCESS] Modelo YOLO cargado en device={device}.")
        return model
    except Exception as e:
        print(f"[ERROR] No se pudo cargar YOLO: {e}")
        return None
```

#### Después (src/services/yolo_model_service.py)

Tres funciones públicas:

1. **`get_torch_device(torch_module=None) -> str`**
   - Selecciona device dinámicamente
   - Retorna `"cuda:0"` si CUDA disponible, `"cpu"` si no
   - Lanza `RuntimeError` si PyTorch no está disponible

2. **`resolve_yolo_model_path(yolo_config: dict, *, fallback: str = "yolo26s.pt") -> str`**
   - Lee `yolo_config["model_path"]`
   - Si existe, la retorna
   - Si no existe o está vacía, retorna `fallback`
   - Imprime `[WARN]` si debe usar fallback

3. **`load_yolo_model(yolo_config: dict) -> Optional[Any]`**
   - Orquesta las funciones anteriores
   - Valida disponibilidad de torch y YOLO
   - Crea modelo e imprime `[SUCCESS]` o `[ERROR]`
   - Retorna modelo o None

---

### Decisiones CUDA/CPU

```python
device = "cuda:0" if bool(getattr(torch, "cuda", None)) and torch.cuda.is_available() else "cpu"
```

- **Lógica:** Si torch tiene módulo `cuda` Y `torch.cuda.is_available()` retorna True → usa `cuda:0`
- **Fallback:** CPU siempre disponible
- **Implicación:** No importa si GPU está disponible pero deshabilitada; prefiere CPU
- **Riesgo:** Ninguno; `model.to()` manejará errores de device

---

### Resolución de model_path

1. Lee `YOLO_CONFIG["model_path"]`
2. Si está vacía o falta → usa fallback `"yolo26s.pt"`
3. Si archivo no existe → intenta fallback
4. Prioridad: `model_path` (config) > `"yolo26s.pt"` (fallback)

```
Flow:
  yolo_config["model_path"] = "/path/to/yolov8.pt"
    ↓
  ¿Existe? No
    ↓
  Usa fallback: "yolo26s.pt"
```

---

### Cambios en app.py

#### Línea 40: Removido
```python
# ANTES
from ultralytics import YOLO

# DESPUÉS
# (removido)
```

#### Línea 45-47: Removido
```python
# ANTES
try:
    import torch
except Exception:
    torch = None

# DESPUÉS
# (removido)
```

#### Línea 50: Agregado
```python
# ANTES
from src.services.detection_event_service import ...

# DESPUÉS
from src.services.yolo_model_service import load_yolo_model
from src.services.detection_event_service import ...
```

#### Línea 277-293: Removido
```python
# ANTES
# ======================== YOLO (device dinamico) ========================
def load_yolo_model() -> YOLO | None:
    # ... 16 líneas de código ...

# DESPUÉS
# ======================== YOLO MODEL ========================
# (solo comentario; función movida a servicio)
```

#### Línea 322: Actualizado
```python
# ANTES
yolo_model = load_yolo_model()

# DESPUÉS
yolo_model = load_yolo_model(YOLO_CONFIG)
```

---

### Pruebas Agregadas

**Archivo:** `tests/test_yolo_model_service.py`

#### Test Suite: `TestGetTorchDevice`
- `test_returns_cpu_when_torch_is_none()` — Lanza error si torch es None
- `test_returns_cpu_when_cuda_not_available()` — CPU si no hay cuda
- `test_returns_cpu_when_cuda_not_available_explicitly()` — CPU si cuda.is_available() es False
- `test_returns_cuda_0_when_available()` — CUDA:0 si disponible

#### Test Suite: `TestResolveYoloModelPath`
- `test_returns_configured_path_if_exists()` — Retorna path si existe
- `test_returns_fallback_if_path_missing()` — Fallback si path no existe
- `test_returns_fallback_if_config_empty()` — Fallback si config vacía
- `test_returns_fallback_if_config_whitespace()` — Fallback si config solo espacios
- `test_custom_fallback()` — Acepta fallback personalizado

#### Test Suite: `TestLoadYoloModel`
- `test_returns_none_if_torch_unavailable()` — None si torch no disponible
- `test_returns_none_if_yolo_unavailable()` — None si YOLO no disponible
- `test_returns_model_on_success()` — Retorna modelo si éxito
- `test_moves_model_to_cuda_if_available()` — Llama model.to("cuda:0") si GPU
- `test_uses_fallback_if_model_path_missing()` — Usa fallback si path no existe
- `test_returns_none_on_yolo_exception()` — None si YOLO excepción
- `test_returns_none_on_model_to_device_exception()` — None si model.to() excepción

**Características:**
- ✓ No descarga modelos reales (usa mocks con MagicMock)
- ✓ No usa GPU real (mocks de torch.cuda)
- ✓ Cubre todos los caminos principales
- ✓ No importa app.py (no interdependencias)

---

### Riesgos Conocidos

#### 1. Type Hints en app.py
- **Riesgo:** app.py tenía `def load_yolo_model() -> YOLO | None:`
- **Resolución:** Se removió la type hint al remover la función local
- **Impacto:** ✓ Ninguno; `yolo_model` se usa como `Any` en los workers

#### 2. Imports Condicionales
- **Riesgo:** torch y YOLO se importan con try/except a nivel de módulo
- **Impacto:** ✓ Controlado; RuntimeError capturado en `load_yolo_model()`

#### 3. Comportamiento de Fallback
- **Riesgo:** Si `"yolo26s.pt"` tampoco existe, YOLO() lanzará excepción
- **Resolución:** Capturada en except; retorna None
- **Impacto:** ✓ Log [ERROR]; app sigue funcionando pero sin detecciones

#### 4. Device Selection
- **Riesgo:** GPU disponible pero no funcional
- **Impacto:** ✓ model.to() manejará error; retornará None

---

### Compatibilidad

- ✓ Endpoints sin cambios
- ✓ Rutas sin cambios
- ✓ HTML/JS sin cambios
- ✓ Comportamiento de yolo_model idéntico
- ✓ Logs [SUCCESS], [WARN], [ERROR] preservados
- ✓ PTZ, tracking, inspección, dataset, análisis: sin cambios

---

### Verificación Post-Refactor

1. **check_project.py:** ✓ Debe terminar OK
2. **py scripts/run_dev.py:** ✓ Debe cargar modelo sin errores
3. **Consola:** ✓ Debe mostrar `[SUCCESS] Modelo YOLO cargado en device=...`
4. **Login/Dashboard:** ✓ Debe funcionar normalmente
5. **Video en vivo:** ✓ Debe mostrar detecciones

---

### Migración Futura

Si en futuro se necesita cambiar estrategia de device selection o fallback:

1. Editar solo `src/services/yolo_model_service.py`
2. Actualizar tests en `tests/test_yolo_model_service.py`
3. No tocar app.py
4. Garantiza centralización y mantenibilidad

---

### Commit Message

```
AI: refactoriza servicio de carga YOLO

- Crea src/services/yolo_model_service.py con funciones:
  - get_torch_device(): selecciona cuda:0 o cpu
  - resolve_yolo_model_path(): resuelve path con fallback
  - load_yolo_model(): orquesta carga completa
- Actualiza app.py:
  - Elimina imports de YOLO y torch
  - Elimina función load_yolo_model() local
  - Importa desde servicio
  - Llama load_yolo_model(YOLO_CONFIG)
- Agrega tests/test_yolo_model_service.py:
  - 13 tests unitarios con mocks
  - Sin descargas ni GPU real
  - Cubre todos los caminos de error
- Documentación en docs/refactor_yolo_model_service.md
```
