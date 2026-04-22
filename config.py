# config.py
# Archivo de configuración para el sistema de detección de drones
# Personaliza estos valores según tu entorno

import os


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip().lower()
    if value in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "f", "no", "n", "off"}:
        return False
    return default


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value.strip())
    except Exception:
        return default

# ======================== CONFIGURACIÓN RTSP ========================
RTSP_CONFIG = {
    'enabled': True,           # Habilitar streaming RTSP
    'url': 'rtsp://admin:Hitmank98@192.168.1.64:554/Streaming/Channels/101',  # URL de cámara Hikvision
    'username': 'admin',       # Usuario de cámara
    'password': 'Hitmank98',   # Contraseña
    'timeout': 30,             # Timeout de conexión en segundos
    'buffer_size': 1,          # Tamaño de buffer (evitar latencia)
}

# ======================== CONFIGURACIÓN YOLO ========================
YOLO_CONFIG = {
    'model_path': 'runs/detect/train-10/weights/best.pt',  # Ruta al modelo entrenado
    'device': 'cuda:0',        # GPU a usar (cuda:0 para RTX 4060)
    'confidence': 0.5,         # Threshold de confianza mínimo
    'verbose': False,          # Mostrar logs YOLO detallados
    'save_detections': True,   # Guardar detecciones en BD
    'min_confidence_db': 0.60,  # Confianza mínima para guardar en BD
}

# ======================== CONFIGURACIÓN DE VIDEO ========================
VIDEO_CONFIG = {
    'width': 1280,             # Ancho de frame
    'height': 720,             # Alto de frame
    'fps': 30,                 # FPS objetivo
    'jpeg_quality': 80,        # Calidad JPEG (1-100)
    'inference_interval': 1,   # Procesar cada N frames (1 = todos)
}

# ======================== CONFIGURACIÓN DE FLASK ========================
FLASK_CONFIG = {
    'debug': _env_bool('FLASK_DEBUG', False),  # Modo debug (no recomendado en producción)
    'host': os.environ.get('FLASK_HOST', '0.0.0.0'),  # Host (0.0.0.0 para acceso remoto)
    'port': _env_int('FLASK_PORT', 5000),  # Puerto
    'threaded': _env_bool('FLASK_THREADED', True),  # Soporte multi-thread
    'max_content_length': _env_int('FLASK_MAX_CONTENT_LENGTH', 500 * 1024 * 1024),  # Máximo upload 500MB
}

# ======================== CONFIGURACIÓN DE ALMACENAMIENTO ========================
STORAGE_CONFIG = {
    'db_path': 'detections.db',           # Ruta base de datos SQLite
    'upload_folder': 'uploads',            # Directorio de archivos subidos
    'detections_frames_folder': 'detections_frames',  # Directorio para frames de detecciones
    'allowed_extensions': {'png', 'jpg', 'jpeg', 'mp4', 'avi', 'mov'},  # Extensiones permitidas
    'cleanup_old_uploads': True,           # Limpiar uploads antiguos
    'cleanup_days': 7,                     # Días para considerar "antiguo"
}

# ======================== CONFIGURACIÓN DE ALERTAS ========================
ALERT_CONFIG = {
    'update_interval': 1000,   # Actualizar UI cada N milisegundos
    'enable_notifications': False,  # Habilitar notificaciones del sistema
    'notification_confidence': 0.7,  # Confianza mínima para notificar
    'sound_alert': False,      # Reproducir sonido en alerta
}

# ======================== CONFIGURACIÓN DE SEGURIDAD ========================
SECURITY_CONFIG = {
    'require_auth': False,     # Requerir autenticación (TODO: implementar)
    'api_key': 'your-api-key',  # API key para endpoints
    'enable_cors': False,      # Habilitar CORS
}

# ======================== FUNCIONES DE UTILIDAD ========================
def get_config():
    """Retorna configuración completa."""
    return {
        'rtsp': RTSP_CONFIG,
        'yolo': YOLO_CONFIG,
        'video': VIDEO_CONFIG,
        'flask': FLASK_CONFIG,
        'storage': STORAGE_CONFIG,
        'alert': ALERT_CONFIG,
        'security': SECURITY_CONFIG,
    }

def validate_config():
    """Valida que la configuración es válida."""
    import os
    from pathlib import Path
    
    errors = []
    
    # Validar modelo YOLO
    if not os.path.exists(YOLO_CONFIG['model_path']):
        errors.append(f"Modelo YOLO no encontrado: {YOLO_CONFIG['model_path']}")
    
    # Validar directorio de uploads
    Path(STORAGE_CONFIG['upload_folder']).mkdir(parents=True, exist_ok=True)
    
    return errors

if __name__ == '__main__':
    # Prueba de configuración
    print("Validando configuración...")
    errors = validate_config()
    
    if errors:
        print("ERRORES ENCONTRADOS:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("[OK] Configuracion valida")
        print("\nConfiguraciones cargadas:")
        config = get_config()
        for section, values in config.items():
            print(f"  [{section.upper()}]")
            for key, value in values.items():
                if isinstance(value, str) and len(value) > 50:
                    print(f"    {key}: {value[:50]}...")
                else:
                    print(f"    {key}: {value}")
