# GitHub Actions: validación automática

## Qué se agregó

- Workflow: `.github/workflows/siran-check.yml`

## Cuándo se ejecuta

- En cada `push` a `main`.
- En cada `pull_request` hacia `main`.

## Qué valida

- Instala dependencias **mínimas** (sin YOLO/RTSP/ONVIF) para poder correr tests:
  - `pytest`, `Flask`, `Flask-Login`, `Werkzeug`
- Ejecuta:
  - `python -m pytest tests`
  - Un `py_compile` básico de `app.py`, `config.py`, `src/routes/*.py`, `src/services/*.py`, `tests/*.py`.

## Qué NO valida (por seguridad/tiempo)

- No ejecuta `app.py` ni `scripts/run_dev.py`.
- No conecta a RTSP.
- No conecta a ONVIF ni mueve PTZ.
- No ejecuta YOLO ni descarga modelos.
- No prueba `/video_feed` ni streaming.

## Cómo interpretar fallas

- Si falla `pytest`: revisar el test que falla en el log del job.
- Si falla `py_compile`: hay un error de sintaxis/import/bytecode en alguno de los módulos compilados.

## Diferencia vs `scripts/check_project.py`

- `scripts/check_project.py` es el check local completo (incluye warnings de archivos sensibles locales + git status).
- El workflow en GitHub Actions busca ser liviano y no depende de hardware ni de dependencias pesadas (ultralytics/opencv/torch).

