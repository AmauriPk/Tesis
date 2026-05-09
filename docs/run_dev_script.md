# Script: `scripts/run_dev.py`

## Para qué sirve

Arranque controlado para desarrollo que:

- verifica estructura mínima del proyecto,
- emite warnings útiles (sin modificar nada),
- y finalmente ejecuta `app.py` usando el mismo Python del proceso actual.

## Cómo ejecutarlo

Desde la raíz del repo:

- `py scripts/run_dev.py`

Si usas otro Python/venv para el proyecto, ejecuta el script con ese intérprete (para que `app.py` use las mismas dependencias).

## Qué valida

Antes de ejecutar `app.py`:

- Estructura base: `app.py`, `config.py`, `src/`, `scripts/`
- Presencia (solo warning si falta):
  - `config_camara.json`
  - `uploads/`
  - `static/results/`
  - `static/evidence/`
  - `static/top_detections/`
  - `dataset_entrenamiento/`
  - `dataset_recoleccion/`
- Variables recomendadas (solo warning si faltan):
  - `FLASK_SECRET_KEY`
  - `DEFAULT_ADMIN_PASSWORD`
  - `DEFAULT_OPERATOR_PASSWORD`
- Modelo YOLO configurado (heurística ligera leyendo `config.py` como texto):
  - muestra `YOLO model_path=...` y si el archivo existe.

## Qué NO valida

- No prueba RTSP/ONVIF ni hardware real.
- No ejecuta smoke-tests ni pytest.
- No crea archivos, no modifica `.env` ni `config_camara.json`.

## Diferencias con `scripts/check_project.py`

- `scripts/check_project.py` valida compilación + pytest + warnings de archivos sensibles + git status.
- `scripts/run_dev.py` está enfocado en **arrancar** el servidor de forma controlada y con warnings previos.

