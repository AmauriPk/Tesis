# Refactor: `media_service` (rutas/paths de evidencias)

## Qué se movió

- Helpers de paths seguros desde `app.py` hacia `src/services/media_service.py`:
  - `safe_rel_path(rel_path: str) -> str`
  - `safe_join(base_dir: str, rel_path: str) -> str`
- Endpoint de media desde `app.py` hacia un Blueprint nuevo `src/routes/media.py`:
  - `GET /media/<path:rel_path>`

## Endpoints (sin cambios)

- `GET /media/<path:rel_path>` (mismo método y misma URL HTTP).

## Seguridad (path traversal)

El servicio aplica:

- Normalización a separador `/` y remoción de prefijo `/`.
- Bloqueo de segmentos `..`.
- Verificación de que la ruta final permanezca dentro del `base_dir` permitido.

La ruta `/media/<path:rel_path>` mantiene la política anterior:

- Solo sirve archivos que estén dentro de `app.root_path`.
- Requiere autenticación y rol (`operator` o `admin`), igual que antes.

## Dependencias inyectadas

`src/routes/media.py` recibe por `init_media_routes(...)`:

- `role_required`

## Cómo probar

1. Iniciar la app:
   - `py app.py`
2. Autenticarse (operador o admin).
3. Abrir una evidencia desde la UI (alertas recientes).
4. Verificar que una URL tipo:
   - `/media/static/evidence/<archivo>.jpg`
   responda `200` y muestre la imagen.
5. Verificar que un traversal devuelva error:
   - `/media/../.env` -> `400`

## Riesgos conocidos / pendientes

- La ruta permite servir cualquier archivo dentro de `app.root_path` (comportamiento previo). Si post-defensa se quiere restringir a carpetas permitidas (por ejemplo solo `static/evidence`, `static/results`, `static/top_detections`), hacerlo como cambio separado para no romper URLs existentes.

