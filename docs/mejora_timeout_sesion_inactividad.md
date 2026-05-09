# Mejora de seguridad: expiración de sesión por inactividad

## Problema

Un usuario autenticado podía permanecer con sesión activa indefinidamente mientras el navegador conservara la cookie, aun sin actividad.

## Solución aplicada

Se agregó expiración por inactividad (idle timeout):

- Variable de entorno: `SESSION_IDLE_TIMEOUT_SECONDS`
  - default: `900` (15 minutos)
  - clamp: mínimo `60`, máximo `86400`
- En `app.py` (`@app.before_request`):
  - si el usuario está autenticado y `now - last_seen_at > timeout`:
    - `logout_user()`
    - `session.clear()`
    - `flash("La sesión expiró por inactividad.", "warning")`
    - `redirect(url_for("auth.login"))`
  - si no expiró, actualiza `session["last_seen_at"] = time.time()`
- En login exitoso (`src/routes/auth.py`):
  - se setea `session["last_seen_at"] = time.time()`

Se excluye para evitar loops:

- `auth.login`
- `auth.logout`
- `static`

## Cómo probar manualmente

1. En una consola, setear temporalmente:
   - Windows (CMD): `set SESSION_IDLE_TIMEOUT_SECONDS=60`
2. Arrancar app.
3. Iniciar sesión.
4. Esperar más de 60s sin hacer requests.
5. Recargar una ruta protegida: debe redirigir a `/login` con mensaje de expiración.

## Limitaciones

- La expiración depende de actividad HTTP (requests).
- No reemplaza controles adicionales post-defensa (p.ej. CSRF, sesiones server-side).

