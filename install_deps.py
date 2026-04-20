# install_deps.py
# Script alternativo para instalar dependencias con mirrors más rápidos

import subprocess
import sys

def run_command(cmd):
    """Ejecuta un comando y muestra el output."""
    print(f"Ejecutando: {cmd}")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        print(e.stderr)
        return False

def main():
    print("Instalando dependencias del proyecto con mirrors alternativos...")

    # Activar venv
    venv_activate = r".\venv\Scripts\Activate.ps1"

    # Instalar PyTorch CPU desde mirror chino (más rápido)
    pytorch_cmd = f'{venv_activate}; pip install torch torchvision torchaudio -i https://pypi.tuna.tsinghua.edu.cn/simple'
    if run_command(pytorch_cmd):
        print("PyTorch instalado correctamente.")
    else:
        print("Fallo en PyTorch. Intentando con PyPI oficial...")
        pytorch_cmd = f'{venv_activate}; pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu'
        run_command(pytorch_cmd)

    # Instalar ultralytics
    ultralytics_cmd = f'{venv_activate}; pip install ultralytics -i https://pypi.tuna.tsinghua.edu.cn/simple'
    if run_command(ultralytics_cmd):
        print("Ultralytics instalado correctamente.")
    else:
        print("Fallo en ultralytics. Intentando con PyPI oficial...")
        ultralytics_cmd = f'{venv_activate}; pip install ultralytics'
        run_command(ultralytics_cmd)

    print("Instalación completada. Ejecuta 'python check_env.py' para verificar.")

if __name__ == "__main__":
    main()