# Refactor: rutas de autenticación a Blueprint

Fecha: 2026-05-07

## Qué se movió

Desde `app.py` se extrajeron a un Blueprint separado las rutas de autenticación:

- `GET|POST /login`
- `GET /logout`

Se mantuvieron las mismas **URLs HTTP**, métodos, lógica de validación, flashes y redirecciones.

## Dónde quedó

- Blueprint: `src/routes/auth.py`
  - `auth_bp = Blueprint("auth", __name__)`
  - `init_auth_routes(**deps)` para inyección de dependencias y evitar imports circulares con `app.py`.

## Dependencias inyectadas (desde app.py)

`src/routes/auth.py` no importa `app.py`. En su lugar, `app.py` llama:

- `init_auth_routes(...)` con:
  - `User` (modelo de usuario; usado para `User.query.filter_by(...)`)
  - `FLASK_CONFIG` (para `show_bootstrap_hint` en `login.html`)

Luego registra:
- `app.register_blueprint(auth_bp)`

## Nota importante (url_for y login_view)

Al mover rutas a Blueprint, los endpoints internos cambian a `auth.<endpoint>`.

Se aplicaron correcciones mínimas (solo `url_for(...)`) en templates para evitar `BuildError`:

- `url_for('login')` -> `url_for('auth.login')`
- `url_for('logout')` -> `url_for('auth.logout')`

También se actualizó:

- `login_manager.login_view = "auth.login"`

## Cómo probar

1. Arrancar la app:
   - `py app.py`
2. Probar login:
   - `GET /login` → renderiza `login.html`
   - `POST /login` con credenciales válidas → sesión inicia y redirige igual que antes.
3. Probar logout:
   - `GET /logout` → cierra sesión y redirige a `/login`.
4. Probar acceso sin sesión:
   - entrar a `/` debe redirigir a `/login`.

## Riesgos conocidos

- Si `login_manager.login_view` no apunta a `auth.login`, usuarios no autenticados pueden no ser redirigidos correctamente al formulario de login.
- Las correcciones en templates son necesarias porque los endpoints internos cambiaron al usar Blueprint.

## Pendiente

- Mantener `login_manager`, `load_user`, `role_required`, `bootstrap_users`, `User` y `db` en `app.py` por ahora (refactor posterior).

