# Script: `scripts/check_project.py`

## Para qué sirve

Ejecuta una validación rápida y repetible del proyecto SIRAN después de cambios (Claude/Codex), para detectar:

- errores de sintaxis/import/compilación,
- fallos en tests,
- presencia de archivos sensibles (advertencia),
- y estado del working tree de git.

## Cómo ejecutarlo

Desde la raíz del repo:

- `py scripts/check_project.py`

## Qué valida

1) **Compilación Python (`py_compile`)** de:

- `app.py`
- `config.py`
- `src/system_core.py`
- `src/video_processor.py`
- `src/routes/**/*.py`
- `src/services/**/*.py`
- `tests/**/*.py`

2) **Pytest**:

- Ejecuta `sys.executable -m pytest tests` (usa el mismo Python del entorno).
- Si pytest no está instalado, falla con mensaje:
  - `[ERROR] pytest no está instalado. Instala con: pip install pytest`

3) **Archivos sensibles (solo advertencia)**:

- Advierte si existen localmente:
  - `.env`
  - `config_camara.json`
  - `uploads/`
  - `static/results/`
  - `static/evidence/`
  - `static/top_detections/`
  - `dataset_entrenamiento/`
  - `dataset_recoleccion/`
  - `runs/`
- Busca y advierte por patrones:
  - `*.db`, `*.sqlite`, `*.sqlite3`, `*.pt`, `*.onnx`

4) **Git status (solo informativo)**:

- Ejecuta `git status --porcelain`.
- Si hay cambios, los lista.
- No hace commit ni push.

## Qué NO valida

- No verifica conectividad RTSP/ONVIF.
- No ejecuta YOLO ni video_feed.
- No prueba hardware real.
- No borra archivos ni modifica configuración.

## Interpretación de resultados

- `RESULTADO FINAL: OK` → compilación + pytest OK, sin warnings.
- `RESULTADO FINAL: OK CON WARNINGS` → compilación + pytest OK, pero hay advertencias (p. ej. archivos sensibles presentes o cambios en git).
- `RESULTADO FINAL: ERROR` → falló compilación o pytest (exit code 1).

