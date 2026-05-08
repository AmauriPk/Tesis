# Limpieza segura aplicada (bajo riesgo) — SIRAN

Fecha: 2026-05-08

## Alcance

Limpieza **mínima** y **de muy bajo riesgo** posterior al análisis de código muerto en `docs/`.

Reglas respetadas:
- No se cambiaron endpoints HTTP, rutas, HTML ni JavaScript.
- No se tocó YOLO, PTZController, PTZCommandWorker, TrackingPTZWorker, InspectionPatrolWorker.
- No se movieron workers ni rutas; solo se eliminó código claramente no referenciado.

## Qué se eliminó (y por qué es seguro)

- `app.py`: variable global `stream_lock = threading.Lock()`
  - Motivo: no tiene referencias en el proyecto (era letra muerta). Ya estaba marcada como “Muy bajo” en `docs/analisis_codigo_muerto.md`.

## Qué NO se eliminó (pendiente por seguridad)

Se dejaron explícitamente para evitar riesgos antes de la defensa (aunque algunos estén marcados como probables “muertos”):
- `app.py`: `_bbox_offset_norm`, `_ptz_centering_vector`, `_p_control_speed`, `_select_priority_detection`, `_require_ptz_capable`
- `app.py`: `cleanup_old_evidence`
- `src/system_core.py`: helpers/funciones “de respaldo” (no se eliminan aún)
- `src/video_processor.py`: funciones relacionadas con PTZ/bbox
- `config.py`: `PTZ_CONFIG`, `VISION_MODEL_PARAMS`, `PERSISTENCE_CONFIG` (solo documentado como posible limpieza futura)

Nota sobre duplicación:
- `_clamp` en `app.py` podría reemplazarse por `clamp` de `src.system_core`, pero **no se cambió** en esta limpieza.

## Cómo validar

Compilación (sin ejecutar Flask):
- `py -m py_compile app.py src/routes/*.py src/services/*.py src/system_core.py src/video_processor.py`

## Riesgos restantes

- Persisten secciones de código “probablemente muerto” en `app.py` y `src/video_processor.py`, mantenidas como respaldo hasta después de la defensa.

