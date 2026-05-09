# Mejora de seguridad: rate limit básico en login (in-memory)

## Problema

El endpoint `POST /login` permitía intentos ilimitados, lo cual facilita fuerza bruta local.

## Solución aplicada

Se agregó un rate limit simple **en memoria** dentro de `src/routes/auth.py`:

- Se registran intentos fallidos por combinación:
  - IP del cliente (X-Forwarded-For o `remote_addr`)
  - username normalizado (lower), o `__empty__` si vacío
- Si un cliente falla `N` veces dentro de una ventana `W`, se bloquea por `L` segundos.
- En login exitoso se limpian intentos de esa clave.
- Username inválido (con whitespace externo) también cuenta como intento fallido.

Mensaje durante lockout:

- `"Demasiados intentos. Intente nuevamente más tarde."`

No se revela si el usuario existe.

## Variables de entorno

- `LOGIN_MAX_ATTEMPTS` (default: `5`)
- `LOGIN_WINDOW_SECONDS` (default: `300`)
- `LOGIN_LOCKOUT_SECONDS` (default: `60`)

## Limitaciones

- Es **in-memory**: se reinicia al reiniciar `app.py`.
- No sustituye un rate limit real a nivel reverse proxy o una solución tipo Flask-Limiter (pendiente post-defensa).

## Pruebas

Archivo: `tests/test_auth_rate_limit.py`

- Bloquea después de `LOGIN_MAX_ATTEMPTS` fallos.
- Un intento correcto durante bloqueo no autentica.
- Después del lockout, permite login correcto.
- Login correcto limpia intentos.
- Username con espacios cuenta como intento fallido.
- `GET /login` no incrementa intentos.

