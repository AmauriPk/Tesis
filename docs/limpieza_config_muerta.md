# Limpieza controlada: configuración muerta en `config.py`

Fecha: 2026-05-08

## Variables candidatas revisadas

- `PTZ_CONFIG`
- `VISION_MODEL_PARAMS`
- `PERSISTENCE_CONFIG`

## Evidencia de no uso funcional

Se buscó en todo el proyecto (excluyendo `docs/`) referencias a:

- `PTZ_CONFIG`
- `VISION_MODEL_PARAMS`
- `PERSISTENCE_CONFIG`

Resultado: solo aparecían en `config.py` (definición y `__all__`), sin imports ni usos en:

- `app.py`
- `src/routes/`
- `src/services/`
- `src/video_processor.py`
- `src/system_core.py`
- `templates/`
- `static/`

## Variables eliminadas

Se eliminaron de `config.py` por no uso real:

- `PTZ_CONFIG`
- `VISION_MODEL_PARAMS`
- `PERSISTENCE_CONFIG`

También se removieron de `__all__` para no exportarlas.

## Variables conservadas

No se tocaron (por ser config activa del sistema):

- `FLASK_CONFIG`
- `YOLO_CONFIG`
- `VIDEO_CONFIG`
- `STORAGE_CONFIG`
- `RTSP_CONFIG`
- `ONVIF_CONFIG`
- `_env_bool`, `_env_float`, `_env_int`

## Riesgos / pendientes

- Si algún script externo fuera del repo importa `PTZ_CONFIG`/`VISION_MODEL_PARAMS`/`PERSISTENCE_CONFIG`, necesitaría actualizarse. No se detectaron usos dentro del proyecto.

## Validación

- `py_compile` sobre: `app.py`, `config.py`, `src/routes/*.py`, `src/services/*.py`, `src/system_core.py`, `src/video_processor.py`.

