# Limpieza controlada: funciones muertas en `app.py`

Fecha: 2026-05-08

## Objetivo

Eliminar funciones marcadas como probablemente muertas **solo si** no existen referencias en el proyecto.

## Funciones revisadas

- `_bbox_offset_norm`
- `_ptz_centering_vector`
- `_p_control_speed`
- `_select_priority_detection`
- `_require_ptz_capable`

## Evidencia de no uso

Se buscó en todo el repo (`app.py`, `src/`, `templates/`, `static/`) referencias a:

- `*_name*` (búsqueda por token)
- `*_name*(` (búsqueda de llamadas)

Resultado: solo existían en sus definiciones (y en llamadas internas entre ellas), sin usos externos.

## Funciones eliminadas

Se eliminaron de `app.py`:

- `_bbox_offset_norm`
- `_ptz_centering_vector`
- `_p_control_speed`
- `_select_priority_detection`
- `_require_ptz_capable`

## Funciones conservadas

- `_clamp`: **no** se eliminó porque sigue siendo usada por tracking/inspección/inyección de dependencias.

## Imports eliminados

- `select_priority_detection` (import en `app.py`), porque quedó sin uso al eliminar `_select_priority_detection`.

## Riesgos / pendientes

- Si algún flujo externo (no indexado por búsqueda, p.ej. ejecución dinámica) dependiera de alguno de estos nombres, habría que restaurarlo. No se detectaron usos de ese tipo en el repositorio.

## Validación

- `py_compile` sobre `app.py`, `src/routes/*.py`, `src/services/*.py`, `src/system_core.py`, `src/video_processor.py`.

