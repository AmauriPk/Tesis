# check_env.py
# Script para verificar que el entorno esté configurado correctamente

import sys

OK = "[OK]"
ERR = "[ERROR]"

def check_module(module_name):
    try:
        __import__(module_name)
        print(f"{OK} {module_name} instalado correctamente")
        return True
    except ImportError:     
        print(f"{ERR} {module_name} no esta instalado")
        return False

def main():
    print("Verificando dependencias del proyecto...")
    print()

    modules = ['cv2', 'ultralytics', 'torch', 'sqlite3']
    all_ok = True

    for module in modules:
        if not check_module(module):
            all_ok = False

    print()

    if all_ok:
        print(f"{OK} Todas las dependencias estan instaladas.")
        # Verificar CUDA si torch está disponible
        try:
            import torch
            print(f"CUDA disponible: {torch.cuda.is_available()}")
            if torch.cuda.is_available():
                print(f"Dispositivos CUDA: {torch.cuda.device_count()}")
                print(f"GPU: {torch.cuda.get_device_name(0)}")
                # Probar YOLO con GPU
                try:
                    from ultralytics import YOLO
                    print("Probando YOLO con GPU...")
                    model = YOLO('yolo26n.pt')  # modelo pequeño para prueba
                    device = 'cuda' if torch.cuda.is_available() else 'cpu'
                    model.to(device)
                    print(f"{OK} YOLO funciona en {device}")
                except Exception as e:
                    print(f"{ERR} Error con YOLO: {e}")
            else:
                print("Advertencia: CUDA no disponible. El entrenamiento sera en CPU (mas lento).")
        except:
            pass
    else:
        print(f"{ERR} Faltan dependencias. Ejecuta: pip install -r requirements.txt")
        print("Para PyTorch con CUDA: pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121")

if __name__ == "__main__":
    main()
