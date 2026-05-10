"""
Servicio para carga y gestión del modelo YOLO.

Responsabilidades:
  - Importación segura de PyTorch y YOLO
  - Selección dinámica de device (GPU si disponible, CPU si no)
  - Resolución de ruta del modelo con fallback
  - Carga del modelo con manejo de errores
"""
import os
from typing import Any, Optional

try:
    import torch
except ImportError:  # pragma: no cover
    torch = None

try:
    from ultralytics import YOLO
except ImportError:  # pragma: no cover
    YOLO = None


def get_torch_device(torch_module: Optional[Any] = None) -> str:
    """
    Selecciona device dinámicamente para inferencia.
    
    Args:
        torch_module: módulo torch. Si es None, se usa el torch global.
                      Útil para testing con mocks.
    
    Returns:
        "cuda:0" si CUDA está disponible, "cpu" si no.
        
    Raises:
        RuntimeError: Si torch_module es None y torch global no está disponible.
    """
    if torch_module is None:
        torch_module = torch
    
    if torch_module is None:
        raise RuntimeError("PyTorch no está disponible.")
    
    has_cuda = bool(getattr(torch_module, "cuda", None))
    if has_cuda and torch_module.cuda.is_available():
        return "cuda:0"
    return "cpu"


def resolve_yolo_model_path(
    yolo_config: dict,
    *,
    fallback: str = "yolo26s.pt"
) -> str:
    """
    Resuelve la ruta del modelo YOLO desde configuración, con fallback.
    
    Args:
        yolo_config: dict con clave "model_path" (puede estar vacía o ausente)
        fallback: ruta por defecto si model_path no existe o no está configurada.
                  Por defecto: "yolo26s.pt"
    
    Returns:
        Ruta del modelo: yolo_config["model_path"] si existe, sino fallback.
    """
    model_path = str(yolo_config.get("model_path") or "").strip() or fallback
    
    if not os.path.exists(model_path):
        if model_path != fallback:
            print(f"[WARN] No existe YOLO_MODEL_PATH='{model_path}'. Usando fallback '{fallback}'.")
        model_path = fallback
    
    return model_path


def load_yolo_model(yolo_config: dict) -> Optional[Any]:
    """
    Carga el modelo YOLO con device dinámico (GPU si existe; CPU si no).
    
    Comportamiento:
      1. Verifica disponibilidad de PyTorch.
      2. Determina device: cuda:0 (GPU) o cpu.
      3. Resuelve ruta del modelo desde config, con fallback a yolo26s.pt.
      4. Crea instancia YOLO(model_path).
      5. Mueve modelo a device con model.to(device).
      6. Retorna modelo si éxito, None si falla (con [ERROR]).
    
    Args:
        yolo_config: dict con "model_path" (puede estar vacía)
    
    Returns:
        Instancia YOLO o None si falla.
    """
    try:
        # 1. Verificar PyTorch
        if torch is None:
            raise RuntimeError("PyTorch no está disponible.")
        
        # 2. Seleccionar device
        device = get_torch_device(torch)
        
        # 3. Resolver ruta del modelo
        model_path = resolve_yolo_model_path(yolo_config, fallback="yolo26s.pt")
        
        # 4. Crear y mover modelo a device
        if YOLO is None:
            raise RuntimeError("YOLO (ultralytics) no está disponible.")
        
        model = YOLO(model_path)
        model.to(device)
        
        # 5. Log de éxito
        print(f"[SUCCESS] Modelo YOLO cargado en device={device}.")
        return model
        
    except Exception as e:
        print(f"[ERROR] No se pudo cargar YOLO: {e}")
        return None
