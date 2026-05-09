from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _print_header() -> None:
    print("=== SIRAN RUN DEV ===")


def _warn(msg: str) -> None:
    print(f"[WARN] {msg}")


def _error(msg: str) -> None:
    print(f"[ERROR] {msg}")


def _check_structure() -> bool:
    required = [
        ROOT / "app.py",
        ROOT / "config.py",
        ROOT / "src",
        ROOT / "scripts",
    ]
    missing = [p for p in required if not p.exists()]
    if missing:
        for p in missing:
            _error(f"No existe: {p}")
        return False
    return True


def _check_local_paths() -> None:
    paths = [
        ROOT / "config_camara.json",
        ROOT / "uploads",
        ROOT / "static" / "results",
        ROOT / "static" / "evidence",
        ROOT / "static" / "top_detections",
        ROOT / "dataset_entrenamiento",
        ROOT / "dataset_recoleccion",
    ]
    for p in paths:
        if not p.exists():
            _warn(f"Falta: {p.relative_to(ROOT)}")


def _check_recommended_env() -> None:
    keys = ["FLASK_SECRET_KEY", "DEFAULT_ADMIN_PASSWORD", "DEFAULT_OPERATOR_PASSWORD"]
    for k in keys:
        if not (os.environ.get(k) or "").strip():
            _warn(f"{k} no configurada")


def _try_read_yolo_model_path() -> None:
    """
    Intenta leer el modelo YOLO configurado de forma ligera.

    No importa `config.py` para evitar dependencias pesadas; hace parsing simple de texto.
    """
    cfg_path = ROOT / "config.py"
    try:
        text = cfg_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return

    # Parse ligero (sin regex): buscar la línea de model_path y extraer el default.
    model_path = ""
    for line in text.splitlines():
        if '"model_path"' in line and "YOLO_MODEL_PATH" in line and "os.environ.get" in line:
            # Ej: "model_path": os.environ.get("YOLO_MODEL_PATH", "runs/detect/weights/best.pt"),
            # Tomar el 2do string literal del get(..., "<default>")
            parts = line.split('"')
            # parts suele contener: ['    ', 'model_path', ': os.environ.get(', 'YOLO_MODEL_PATH', ', ', 'runs/...', '),']
            if len(parts) >= 6:
                model_path = (parts[5] or "").strip()
            break
    if not model_path:
        return

    model_fs = Path(model_path)
    if not model_fs.is_absolute():
        model_fs = (ROOT / model_fs).resolve()

    exists = model_fs.exists()
    status = "EXISTE" if exists else "NO EXISTE"
    print(f"[INFO] YOLO model_path={model_path} ({status})")


def _check_python_deps() -> bool:
    """
    Checks mínimos antes de intentar ejecutar `app.py`.
    No instala nada ni imprime secretos.
    """
    required = ["flask", "flask_login"]
    missing = []
    for mod in required:
        try:
            __import__(mod)
        except Exception:
            missing.append(mod)
    if missing:
        _warn(f"Faltan módulos en este Python ({sys.executable}): {', '.join(missing)}")
        _warn("Si usas otro Python/venv, ejecuta este script con ese intérprete (ej: `py -3.11 scripts/run_dev.py`).")
        # No abortamos: intentamos ejecutar app.py igual; así el error real se ve en consola.
    return True


def main() -> int:
    _print_header()

    print("\n[1/4] Verificando estructura...")
    if not _check_structure():
        print("ERROR")
        return 1
    print("OK")

    print("\n[2/4] Revisando archivos locales...")
    _check_local_paths()
    _try_read_yolo_model_path()
    print("OK")

    print("\n[3/4] Revisando variables recomendadas...")
    _check_recommended_env()
    print("OK")

    print("\n[4/4] Iniciando app.py...")
    _check_python_deps()
    cmd = [sys.executable, str(ROOT / "app.py")]
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT))
        return int(proc.returncode or 0)
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        _error(f"No se pudo ejecutar app.py: {e!r}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
