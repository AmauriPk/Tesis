# Refactor: `session_security_service`

## Qué se movió

Desde `app.py` hacia `src/services/session_security_service.py`:

- Generación de `boot_id` (token aleatorio por arranque).
- Lectura de `SESSION_IDLE_TIMEOUT_SECONDS` desde entorno + normalización (clamp 60..86400; default 900).
- Helpers para:
  - detectar sesión de arranque anterior (`is_session_from_old_boot`)
  - detectar expiración por inactividad (`is_idle_expired`)
  - actualizar `last_seen_at` (`mark_seen`)

## Qué quedó en `app.py`

- El `@app.before_request` (`_volatile_sessions`) con:
  - `session.permanent = False`
  - exclusiones: `auth.login`, `auth.logout`, `static`
  - acciones side-effect de Flask: `logout_user()`, `session.clear()`, `flash()`, `redirect()`
- La variable pública `SESSION_BOOT_ID` se mantiene (ahora proviene del servicio) para inyección en `init_auth_routes(...)`.

## Comportamiento conservado

- Si expira por inactividad:
  - cierra sesión y redirige a login con mensaje: `"La sesión expiró por inactividad."`
- Si es de un arranque anterior:
  - cierra sesión y redirige a login con mensaje: `"La sesión anterior fue cerrada porque el sistema se reinició."`

## Pruebas agregadas

- `tests/test_session_security_service.py`

## Riesgos conocidos

- El servicio es in-memory y depende de variables de entorno; comportamiento es el mismo que antes, solo reorganizado.

