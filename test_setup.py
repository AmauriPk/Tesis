#!/usr/bin/env python
# test_setup.py
# Script de prueba para verificar que todo está configurado correctamente
# Uso: python test_setup.py

import sys
import os

OK = "[OK]"
WARN = "[WARN]"
ERR = "[ERROR]"

def print_section(title):
    """Imprime un encabezado de sección."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def check_python_version():
    """Verifica versión de Python."""
    print_section("1. VERSIÓN DE PYTHON")
    version = sys.version_info
    print(f"Python {version.major}.{version.minor}.{version.micro}")
    if version.major >= 3 and version.minor >= 8:
        print(f"{OK} Version compatible")
        return True
    else:
        print(f"{ERR} Se requiere Python 3.8+")
        return False

def check_packages():
    """Verifica que todas las dependencias estén instaladas."""
    print_section("2. DEPENDENCIAS PYTHON")
    
    packages = [
        ('flask', 'Flask'),
        ('cv2', 'OpenCV'),
        ('ultralytics', 'Ultralytics YOLO'),
        ('torch', 'PyTorch'),
    ]
    
    all_ok = True
    for module_name, display_name in packages:
        try:
            __import__(module_name)
            print(f"{OK} {display_name} instalado")
        except ImportError:
            print(f"{ERR} {display_name} NO instalado")
            all_ok = False
    
    return all_ok

def check_gpu():
    """Verifica disponibilidad de GPU."""
    print_section("3. GPU CUDA")
    try:
        import torch
        if torch.cuda.is_available():
            print(f"{OK} CUDA disponible")
            print(f"  Dispositivos encontrados: {torch.cuda.device_count()}")
            print(f"  Dispositivo actual: {torch.cuda.get_device_name(0)}")
            return True
        else:
            print(f"{WARN} CUDA NO disponible (se usara CPU)")
            print("  Nota: Rendimiento sera significativamente menor")
            return False
    except Exception as e:
        print(f"{ERR} Error al verificar CUDA: {e}")
        return False

def check_yolo_model():
    """Verifica que el modelo YOLO existe."""
    print_section("4. MODELO YOLO")
    
    model_path = 'runs/detect/train-10/weights/best.pt'
    
    if os.path.exists(model_path):
        size_mb = os.path.getsize(model_path) / (1024 * 1024)
        print(f"{OK} Modelo encontrado: {model_path}")
        print(f"  Tamano: {size_mb:.1f} MB")
        return True
    else:
        print(f"{ERR} Modelo NO encontrado: {model_path}")
        print(f"  Verifica que existe en {os.path.abspath(model_path)}")
        return False

def check_model_loading():
    """Intenta cargar el modelo YOLO."""
    print_section("5. CARGA DE MODELO YOLO")
    try:
        from ultralytics import YOLO
        print("  Cargando modelo...")
        model = YOLO('runs/detect/train-10/weights/best.pt')
        print(f"{OK} Modelo cargado exitosamente")
        
        # Intentar mover a GPU
        try:
            model.to('cuda:0')
            print(f"{OK} Modelo movido a GPU (cuda:0)")
            return True
        except Exception as e:
            print(f"{WARN} No se pudo mover a GPU: {e}")
            print("  Se usara CPU (mas lento)")
            return False
            
    except Exception as e:
        print(f"{ERR} Error al cargar modelo: {e}")
        return False

def check_files():
    """Verifica que existan los archivos necesarios."""
    print_section("6. ARCHIVOS DEL PROYECTO")
    
    files = [
        ('app.py', 'Servidor Flask'),
        ('templates/index.html', 'Interfaz HTML'),
        ('requirements.txt', 'Dependencias'),
        ('config.py', 'Configuración'),
    ]
    
    all_ok = True
    for filepath, description in files:
        if os.path.exists(filepath):
            print(f"{OK} {description}: {filepath}")
        else:
            print(f"{ERR} {description} NO encontrado: {filepath}")
            all_ok = False
    
    return all_ok

def check_config():
    """Verifica que la configuración es válida."""
    print_section("7. CONFIGURACIÓN")
    
    try:
        from config import validate_config
        errors = validate_config()
        
        if errors:
            print(f"{ERR} Errores de configuracion encontrados:")
            for error in errors:
                print(f"  - {error}")
            return False
        else:
            print(f"{OK} Configuracion valida")
            return True
    except Exception as e:
        print(f"{WARN} No se pudo validar configuracion: {e}")
        return False

def main():
    """Ejecuta todas las pruebas."""
    print("\n" + "="*60)
    print("  VERIFICACION DE SETUP - SISTEMA RPAS")
    print("="*60)
    
    results = {
        'Python': check_python_version(),
        'Dependencias': check_packages(),
        'GPU': check_gpu(),
        'Modelo YOLO': check_yolo_model(),
        'Carga Modelo': check_model_loading(),
        'Archivos': check_files(),
        'Configuración': check_config(),
    }
    
    # Resumen
    print_section("RESUMEN")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test, result in results.items():
        status = OK if result else ERR
        print(f"{status} {test}")
    
    print(f"\nResultado: {passed}/{total} pruebas pasadas")
    
    if passed == total:
        print("\nSistema listo. Ejecuta: python app.py")
    elif passed >= total - 1:
        print(f"\n{WARN} Sistema parcialmente listo (algunas advertencias)")
        print("   Puedes ejecutar app.py, pero habra limitaciones")
    else:
        print(f"\n{ERR} Sistema NO listo. Revisa los errores arriba.")
        return 1
    
    print("="*60 + "\n")
    return 0

if __name__ == '__main__':
    sys.exit(main())
