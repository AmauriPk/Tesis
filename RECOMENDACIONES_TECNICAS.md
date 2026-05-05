# 🔧 RECOMENDACIONES TÉCNICAS DETALLADAS

**Objetivo**: Guía de mejora continua para escalabilidad y robustez

---

## 1. REFACTORIZACIÓN DE STATE MANAGEMENT

### Problema Actual

El código usa variables globales con sincronización parcial:

```python
# ❌ Problemático
is_ptz_capable = False
auto_tracking_enabled = False
last_confirmed_detection_at: float | None = None

# Acceso inconsistente:
with state_lock:
    is_ptz_capable = True  # ✓ con lock
    
# Pero luego:
if not is_ptz_capable:  # ✗ sin lock (race condition potencial)
    auto_tracking_enabled = False
```

### Solución Propuesta

Implementar patrón Thread-Safe Singleton:

```python
# app.py - Nuevo módulo: state_manager.py
from __future__ import annotations
import threading
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class SystemState:
    """Thread-safe state container para sistema RPAS."""
    
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    
    # Estado de hardware
    _is_ptz_capable: bool = False
    _camera_source_mode: str = "fixed"
    
    # Estado de control automático
    _auto_tracking_enabled: bool = False
    _inspection_mode_enabled: bool = False
    
    # Timestamps
    _last_confirmed_detection_at: Optional[float] = None
    _onvif_last_probe_at: Optional[float] = None
    _onvif_last_probe_error: Optional[str] = None
    
    # Detection state
    _current_detection_state: dict = field(default_factory=dict, init=False)
    
    # Métodos seguros
    @property
    def is_ptz_capable(self) -> bool:
        with self._lock:
            return self._is_ptz_capable
    
    @is_ptz_capable.setter
    def is_ptz_capable(self, value: bool) -> None:
        with self._lock:
            self._is_ptz_capable = bool(value)
            # Fail-safe: si no es PTZ, deshabilitar tracking
            if not self._is_ptz_capable:
                self._auto_tracking_enabled = False
                self._inspection_mode_enabled = False
    
    @property
    def auto_tracking_enabled(self) -> bool:
        with self._lock:
            return self._auto_tracking_enabled and self._is_ptz_capable
    
    @auto_tracking_enabled.setter
    def auto_tracking_enabled(self, value: bool) -> None:
        with self._lock:
            self._auto_tracking_enabled = bool(value) and self._is_ptz_capable
    
    @property
    def last_confirmed_detection_at(self) -> Optional[float]:
        with self._lock:
            return self._last_confirmed_detection_at
    
    @last_confirmed_detection_at.setter
    def last_confirmed_detection_at(self, value: Optional[float]) -> None:
        with self._lock:
            self._last_confirmed_detection_at = value
    
    # ... similar para otros atributos
    
    def snapshot(self) -> dict:
        """Retorna snapshot atómico del estado para debugging."""
        with self._lock:
            return {
                "is_ptz_capable": self._is_ptz_capable,
                "auto_tracking_enabled": self._auto_tracking_enabled,
                "inspection_mode_enabled": self._inspection_mode_enabled,
                "last_confirmed_detection_at": self._last_confirmed_detection_at,
                "camera_source_mode": self._camera_source_mode,
            }

# Uso en app.py
system_state = SystemState()

# Antes: if not is_ptz_capable:
# Después:
if not system_state.is_ptz_capable:
    system_state.auto_tracking_enabled = False
    # ✓ Automáticamente sincronizado
```

### Beneficios

1. **Thread-safety garantizado**: Todos los accesos sincronizados
2. **Fail-safe automático**: Cambios relacionados se aplican juntos
3. **Debugging mejorado**: Método `snapshot()` para logging de estado
4. **Type-safe**: Properties aseguran tipos correctos

**Esfuerzo**: 4-6 horas  
**Impacto**: Alto (elimina clase entera de bugs)

---

## 2. LOGGING ESTRUCTURADO (Stdlib logging)

### Problema Actual

```python
# ❌ Prints dispersos sin contexto
print("[RTSP] Lectura fallida. Reintentando conexión...")
print("[WARN] DETECTION_PERSISTENCE_FRAMES='abc' invalid: ..., using default=3")
```

Ventajas del stdlib `logging`:
- Filtrado por nivel (DEBUG, INFO, WARNING, ERROR)
- Agregación con ELK stack, Datadog, etc.
- Contexto automático (timestamp, nivel, módulo)
- Configuración dinámica en runtime

### Solución Propuesta

```python
# app.py - Inicialización
import logging
import logging.handlers

# Configurar logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Handler para archivo (con rotación)
file_handler = logging.handlers.RotatingFileHandler(
    "logs/rpas_micro.log",
    maxBytes=10_000_000,  # 10MB
    backupCount=10,
)
file_handler.setLevel(logging.INFO)

# Handler para console (solo WARNING+)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.WARNING)

# Formatter
formatter = logging.Formatter(
    '%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Uso en código
# Antes:
print("[RTSP][WARN] Read failed on {self._current_url}, reconnecting...")

# Después:
logger.warning(
    "RTSP read failed, reconnecting",
    extra={
        "rtsp_url": self._current_url,
        "frame_count": self._frame_count,
    }
)
```

### Estructura de Logs Sugerida

```
logs/
├── rpas_micro.log           # General
├── rpas_micro_rtsp.log      # RTSP stream
├── rpas_micro_yolo.log      # YOLO inference
├── rpas_micro_ptz.log       # PTZ control
└── rpas_micro_metrics.log   # DB operations
```

**Esfuerzo**: 3-4 horas  
**Impacto**: Alto (debugging en producción)

---

## 3. MÉTRICAS Y MONITORING

### Prometheus Metrics

```python
# new file: metrics.py
from prometheus_client import Counter, Histogram, Gauge

# Counters
inference_total = Counter(
    'yolo_inference_total',
    'Total YOLO inferences',
    ['confidence_threshold']
)
detection_confirmed_total = Counter(
    'detection_confirmed_total',
    'Total confirmed detections'
)
ptz_moves_total = Counter(
    'ptz_moves_total',
    'Total PTZ movements',
    ['direction']  # pan, tilt, zoom
)

# Histograms
inference_duration_seconds = Histogram(
    'yolo_inference_duration_seconds',
    'YOLO inference latency',
    buckets=(0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1.0)
)
rtsp_read_duration_seconds = Histogram(
    'rtsp_read_duration_seconds',
    'RTSP frame read latency'
)

# Gauges
detection_state_gauge = Gauge(
    'detection_state',
    'Current detection status',
    ['camera_mode']  # fixed, ptz
)
ptz_capable_gauge = Gauge(
    'ptz_capable',
    'PTZ capability (0=fixed, 1=ptz)'
)

# En app.py:
@app.route('/metrics')
def metrics():
    from prometheus_client import generate_latest
    return generate_latest(), 200, {'Content-Type': 'text/plain'}
```

### Grafana Dashboard

```json
{
  "dashboard": {
    "title": "RPAS Micro Monitoring",
    "panels": [
      {
        "title": "YOLO Inference FPS",
        "targets": [
          {
            "expr": "rate(yolo_inference_total[1m])"
          }
        ]
      },
      {
        "title": "Detection Latency (p95)",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, yolo_inference_duration_seconds)"
          }
        ]
      },
      {
        "title": "PTZ Status",
        "targets": [
          {
            "expr": "ptz_capable_gauge"
          }
        ]
      }
    ]
  }
}
```

**Esfuerzo**: 6-8 horas  
**Impacto**: Alto (visibilidad operativa)

---

## 4. MULTI-CÁMARA SUPPORT

### Arquitectura Propuesta

```python
# models.py - Extender CameraConfig
class CameraConfig(db.Model):
    """Múltiples cámaras configurables."""
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    enabled = db.Column(db.Boolean, default=True)
    
    # RTSP
    rtsp_url = db.Column(db.String(500), nullable=True)
    rtsp_username = db.Column(db.String(120), nullable=True)
    rtsp_password = db.Column(db.String(120), nullable=True)
    
    # ONVIF
    onvif_host = db.Column(db.String(120), nullable=True)
    onvif_port = db.Column(db.Integer, default=80)
    onvif_username = db.Column(db.String(120), nullable=True)
    onvif_password = db.Column(db.String(120), nullable=True)
    
    # Status
    is_ptz_capable = db.Column(db.Boolean, default=False)
    last_connection_at = db.Column(db.DateTime)
    
    # Relaciones
    detections = db.relationship('Detection', backref='camera', lazy=True)

# app.py - Refactorizar para multi-cámara
class CameraStreamManager:
    """Gestor de múltiples streams RTSP."""
    
    def __init__(self):
        self.readers: dict[int, _RTSPLatestFrameReader] = {}
        self.processors: dict[int, _LiveVideoProcessor] = {}
    
    def add_camera(self, camera_id: int, camera_config: CameraConfig) -> None:
        """Agrega una nueva cámara al sistema."""
        reader = _RTSPLatestFrameReader(url=camera_config.effective_rtsp_url())
        processor = _LiveVideoProcessor(reader)
        
        self.readers[camera_id] = reader
        self.processors[camera_id] = processor
        
        reader.start()
        processor.start()
    
    def remove_camera(self, camera_id: int) -> None:
        """Detiene y remueve una cámara."""
        reader = self.readers.pop(camera_id, None)
        processor = self.processors.pop(camera_id, None)
        
        if reader:
            reader.stop()
        if processor:
            processor.stop()

# Uso
camera_manager = CameraStreamManager()

# Inicialización
for camera in CameraConfig.query.filter_by(enabled=True):
    camera_manager.add_camera(camera.id, camera)

# Routes
@app.route('/camera/<int:camera_id>/video_feed')
def video_feed(camera_id: int):
    processor = camera_manager.processors.get(camera_id)
    if not processor:
        abort(404)
    return Response(processor.mjpeg_generator(), ...)
```

**Esfuerzo**: 16-20 horas  
**Impacto**: Alto (escalabilidad)

---

## 5. CONTAINERIZACIÓN (Docker)

```dockerfile
# Dockerfile
FROM nvidia/cuda:11.8.0-runtime-ubuntu22.04

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3.10-venv \
    python3-pip \
    ffmpeg \
    libopencv-dev \
    && rm -rf /var/lib/apt/lists/*

# Crear venv
RUN python3.10 -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

# Instalar Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel
RUN pip install -r requirements.txt

# Copiar código
COPY . .

# Ports
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Entrypoint
CMD ["python", "-m", "flask", "run", "--host=0.0.0.0"]
```

```yaml
# docker-compose.yml
version: '3.9'

services:
  rpas-micro:
    build: .
    ports:
      - "5000:5000"
    environment:
      FLASK_ENV: production
      YOLO_MODEL_PATH: /models/best.pt
      RTSP_URL: rtsp://camera.local:554/stream
      DATABASE_URL: sqlite:////data/app.db
      METRICS_LOGGING: "1"
    volumes:
      - ./models:/models:ro
      - rpas-data:/data
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

volumes:
  rpas-data:
```

**Esfuerzo**: 4-6 horas  
**Impacto**: Alto (deployment consistency)

---

## 6. TESTING (Pytest + CI/CD)

### Test Structure

```python
# tests/conftest.py
import pytest
from app import app, db
from models import User, CameraConfig

@pytest.fixture
def client():
    """Flask test client."""
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove()
        db.drop_all()

@pytest.fixture
def sample_user(client):
    """Crea usuario de prueba."""
    user = User(username='testuser', role='operator')
    user.set_password('testpass123')
    db.session.add(user)
    db.session.commit()
    return user

# tests/test_routes.py
def test_video_feed_requires_auth(client):
    """Valida que /video_feed requiere autenticación."""
    response = client.get('/video_feed')
    assert response.status_code == 302  # Redirect a login

def test_detection_status_endpoint(client, sample_user):
    """Valida endpoint de estado de detecciones."""
    client.post('/login', data={
        'username': 'testuser',
        'password': 'testpass123'
    }, follow_redirects=True)
    
    response = client.get('/detection_status')
    assert response.status_code == 200
    data = response.get_json()
    assert 'status' in data
    assert 'detected' in data

# tests/test_backend_rules.py
from backend_rules import select_priority_detection, bbox_area

def test_bbox_area():
    """Valida cálculo de área."""
    assert bbox_area((0, 0, 10, 10)) == 100
    assert bbox_area((0, 0, 0, 10)) == 0  # Ancho cero
    assert bbox_area((10, 10, 0, 0)) == 0  # Coordenadas inválidas

def test_select_priority_detection():
    """Valida selección de bbox más grande."""
    detections = [
        {'bbox': (0, 0, 10, 10), 'confidence': 0.9},  # Area = 100
        {'bbox': (0, 0, 20, 20), 'confidence': 0.8},  # Area = 400 (mayor)
    ]
    selected = select_priority_detection(detections)
    assert selected['bbox'] == (0, 0, 20, 20)
```

### GitHub Actions CI/CD

```yaml
# .github/workflows/tests.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: test_rpas
          POSTGRES_PASSWORD: test
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
          cache: 'pip'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov
      
      - name: Run tests
        env:
          TESTING: 1
        run: |
          pytest tests/ -v --cov=app --cov=models --cov=backend_rules --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

**Esfuerzo**: 8-12 horas  
**Impacto**: Alto (calidad de código)

---

## 7. PERFORMANCE OPTIMIZATION

### Benchmarking

```python
# benchmarks/yolo_inference.py
import time
import numpy as np
from ultralytics import YOLO

model = YOLO('best.pt')

# Genera frame sintético
frames = [np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8) for _ in range(100)]

# Benchmark
times = []
for frame in frames:
    start = time.perf_counter()
    results = model(frame, device='cuda:0', verbose=False)
    elapsed = time.perf_counter() - start
    times.append(elapsed * 1000)  # ms

print(f"Mean: {np.mean(times):.2f}ms")
print(f"P50:  {np.percentile(times, 50):.2f}ms")
print(f"P95:  {np.percentile(times, 95):.2f}ms")
print(f"P99:  {np.percentile(times, 99):.2f}ms")
print(f"FPS:  {1000 / np.mean(times):.1f}")
```

### Cuellos de Botella Comunes

1. **YOLO Inference**: Paralelizar con batch_size > 1
2. **RTSP Descodificación**: HW acceleration (NVIDIA NVDEC)
3. **Database Writes**: Async writes con queue
4. **ONVIF Discovery**: Caché + scheduled re-probe

---

## 8. SECURITY HARDENING

```python
# config.py - Security additions
import os
from datetime import timedelta

# CORS
CORS_CONFIG = {
    'origins': os.environ.get('CORS_ORIGINS', 'localhost:5000').split(','),
    'methods': ['GET', 'POST'],
    'allow_headers': ['Content-Type', 'Authorization'],
}

# Session security
SESSION_CONFIG = {
    'PERMANENT': False,
    'COOKIE_SECURE': os.environ.get('FLASK_ENV') == 'production',
    'COOKIE_HTTPONLY': True,
    'COOKIE_SAMESITE': 'Strict',
    'COOKIE_NAME': 'RPAS_SESSION_ID',
}

# Rate limiting
RATELIMIT_CONFIG = {
    'API_ENDPOINTS': '100 per hour',
    'LOGIN': '5 per minute',
    'ADMIN_ROUTES': '20 per minute',
}

# Password policy
PASSWORD_MIN_LENGTH = 12
PASSWORD_REQUIRE_SPECIAL_CHARS = True
PASSWORD_REQUIRE_NUMBERS = True
```

**Esfuerzo**: 4-6 horas  
**Impacto**: Medium (security posture)

---

## Matriz de Priorización

| Feature | Impacto | Esfuerzo | Prioridad |
|---------|---------|----------|-----------|
| Thread-safe State | Alto | Medio | 🔴 CRÍTICO |
| Logging Estructurado | Alto | Bajo | 🔴 CRÍTICO |
| Prometheus Metrics | Alto | Medio | 🟠 HIGH |
| Multi-Cámara | Alto | Alto | 🟠 HIGH |
| Docker | Alto | Bajo | 🟠 HIGH |
| Testing/CI-CD | Alto | Alto | 🟡 MEDIUM |
| Security | Medium | Medio | 🟡 MEDIUM |

---

## Conclusión

Estos cambios transformarían el prototipo a un **sistema production-ready**:

- ✅ Escalable (multi-cámara, containerizado)
- ✅ Observable (logging, metrics, monitoring)
- ✅ Robusto (tests, error handling)
- ✅ Seguro (auth, security hardening)
- ✅ Mantenible (code quality, documentation)

**Estimación total**: 60-80 horas de trabajo (~3-4 sprints)

