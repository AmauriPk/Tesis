# Refactor: `file_cleanup_service` (limpieza de evidencias)

## Qué se movió

- `cleanup_old_evidence(...)` desde `app.py` hacia `src/services/file_cleanup_service.py`.

## Compatibilidad

Se dejó un wrapper en `app.py` con la misma firma previa:

- `cleanup_old_evidence(*, dry_run: bool = True) -> dict`

Internamente delega al servicio inyectando:

- `root_path` (`app.root_path`)
- `evidence_dir_default` (`EVIDENCE_DIR`)
- `get_metrics_db_path_abs` (`_get_metrics_db_path_abs`)
- `env_int` (`_env_int`)
- `ensure_detection_events_schema` (`_ensure_detection_events_schema`)

## Por qué no se activa automáticamente

La limpieza puede borrar evidencias útiles para la demo/defensa. Por eso:

- No se ejecuta al arrancar.
- No se agregó endpoint.
- `dry_run=True` sigue siendo el valor por defecto (solo reporta).

## Cómo probar (solo dry-run)

En un REPL / consola (sin ejecutar borrado real):

- `cleanup_old_evidence(dry_run=True)`

Debe devolver un dict con `ok`, `files_total`, `files_marked`, etc.

## Riesgos conocidos

- Ejecutar con `dry_run=False` borrará archivos; usar solo si se decide explícitamente y con respaldo.

