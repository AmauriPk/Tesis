# Refactor: rutas de dataset (admin) a Blueprint

Fecha: 2026-05-07

## Qué se movió

Desde `app.py` se extrajeron a un Blueprint separado las rutas del **gestor de dataset del administrador** (pendientes, clasificadas, clasificar y revertir).

Se mantuvieron exactamente las mismas URLs, métodos, JSON y protecciones (`login_required` + `role_required("admin")`).

## Endpoints conservados (sin cambios)

El Blueprint se registra **sin prefijo**, por lo que se conservan:

- `GET /api/get_dataset_images`
- `GET /api/dataset_image`
- `POST /api/classify_image`
- `GET /api/get_classified_images`
- `GET /api/classified_image`
- `POST /api/revert_classification`

## Dónde quedó

- Blueprint: `src/routes/dataset.py`
  - `dataset_bp = Blueprint("dataset", __name__)`
  - `init_dataset_routes(**deps)` para inyección de dependencias y evitar imports circulares con `app.py`.

Nota: al mover endpoints a un Blueprint, los nombres internos para `url_for(...)` cambian a `dataset.<endpoint>`, aunque las **URLs HTTP** se conservaron iguales. Por ejemplo:
- `url_for("api_get_dataset_images")` -> `url_for("dataset.api_get_dataset_images")`

## Dependencias inyectadas (desde app.py)

`src/routes/dataset.py` no importa `app.py`. En su lugar, `app.py` llama:

- `init_dataset_routes(...)` con:
  - `role_required` (decorador RBAC)
  - `safe_join` (callable `_safe_join` de `app.py`, para bloquear path traversal igual que antes)
  - `dataset_recoleccion_folder` (equivalente a `app.config["DATASET_RECOLECCION_FOLDER"]`)
  - `dataset_training_root` (equivalente a `DATASET_TRAINING_ROOT`)
  - `dataset_negative_dir` (equivalente a `DATASET_NEGATIVE_DIR`)
  - `dataset_positive_pending_dir` (equivalente a `DATASET_POSITIVE_PENDING_DIR`)
  - `dataset_limpias_inbox_dir` (equivalente a `DATASET_LIMPIAS_INBOX_DIR`)

Luego registra:

- `app.register_blueprint(dataset_bp)`

## Helpers movidos vs pendientes

Movidos a `src/routes/dataset.py` (por ser exclusivos del gestor de dataset):

- `_iter_clean_dataset_images(...)`
- `_unique_dest_path(...)` (evita sobrescritura; renombra con sufijos)
- `_iter_classified_images(...)`

Pendientes (se mantuvieron en `app.py` por uso compartido):

- `_safe_rel_path(...)` y `_safe_join(...)` siguen en `app.py` porque también los usa `GET /media/<path:rel_path>`.

## Cómo probar (pendientes)

1. Arrancar la app:
   - `py app.py`
2. Login con rol `admin`.
3. Probar:
   - `GET /api/get_dataset_images?limit=30` → `200` y JSON `{ status, images }`.
4. Ver una imagen:
   - abrir la `url` que viene en cada item (usa `GET /api/dataset_image?path=...`).

## Cómo probar ("Sí es dron" / "No es dron")

1. Login con rol `admin`.
2. Clasificar:
   - `POST /api/classify_image` con body (JSON o form-data) igual que el frontend:
     - `id` (o `path`) y `label` (o `classification`)
3. Confirmar:
   - La imagen se mueve a `DATASET_POSITIVE_PENDING_DIR` (positiva) o `DATASET_NEGATIVE_DIR` (negativa).
   - El item ya no aparece en pendientes.

## Cómo probar ("Ya clasificadas")

1. Login con rol `admin`.
2. Probar:
   - `GET /api/get_classified_images?limit=50` → `200` y JSON `{ status, images }`.
3. Ver una imagen clasificada:
   - abrir la `url` que viene en cada item (usa `GET /api/classified_image?path=...`).

## Cómo probar ("Revertir")

1. Login con rol `admin`.
2. Probar:
   - `POST /api/revert_classification` con el mismo payload que usa el frontend:
     - `id` (`scope:name`) o `path`, y/o `scope` + `name`.
3. Confirmar:
   - La imagen vuelve al inbox `DATASET_LIMPIAS_INBOX_DIR`.

## Riesgos conocidos

- Si `init_dataset_routes(...)` no se llama antes de registrar el Blueprint, las rutas no quedan registradas.
- Los nombres de endpoint se conservaron explícitamente en el Blueprint para no romper `url_for(...)`; cambiar esos `endpoint="..."` rompería el panel admin.
