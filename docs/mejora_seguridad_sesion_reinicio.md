# Mejora de seguridad: invalidación de sesión tras reinicio

## Problema

Si el usuario iniciaba sesión, se detenía el servidor con `CTRL+C` y luego se volvía a iniciar `app.py`, al recargar el navegador la sesión podía permanecer activa porque:

- Flask-Login conserva el `user_id` en la cookie de sesión.
- Por defecto, reiniciar el servidor no invalida automáticamente cookies existentes.

Esto es un riesgo si se deja una pestaña abierta o el navegador conserva la cookie.

## Solución aplicada

Se agregó un identificador volátil por arranque:

- En `app.py`: `SESSION_BOOT_ID = secrets.token_hex(16)` (cambia en cada reinicio).
- En login exitoso (`src/routes/auth.py`): se guarda `session["boot_id"] = SESSION_BOOT_ID`.
- En `@app.before_request` (`app.py`): si el usuario está autenticado y el `boot_id` de su sesión no coincide con el actual:
  - `logout_user()`
  - `session.clear()`
  - `flash("La sesión anterior fue cerrada porque el sistema se reinició.", "warning")`
  - `redirect(url_for("auth.login"))`

Se excluyen para evitar loops:

- `auth.login`
- `auth.logout`
- `static`

## Cómo probar manualmente

1. Arrancar: `py scripts/run_dev.py` (o el Python/venv correcto).
2. Iniciar sesión.
3. Entrar al dashboard.
4. Detener servidor (CTRL+C).
5. Arrancar de nuevo: `py scripts/run_dev.py`.
6. Recargar `127.0.0.1`: debe redirigir a `/login` y mostrar el aviso.

## Limitaciones

- La invalidación se basa en un “boot id” por proceso. No reemplaza controles adicionales como expiración por tiempo o CSRF (pendientes post-defensa).

