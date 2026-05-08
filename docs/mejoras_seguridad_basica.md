# Mejoras de seguridad básica (bajo riesgo) — SIRAN

Fecha: 2026-05-08

## Objetivo

Aplicar mejoras de seguridad **de bajo riesgo** antes de una demostración, sin cambiar comportamiento funcional ni endpoints.

## Cambios aplicados

### 1) `FLASK_SECRET_KEY` desde entorno + warning

- `app.py` ahora lee `FLASK_SECRET_KEY` desde variable de entorno.
- Si no está configurada (vacía o ausente), se mantiene un fallback de desarrollo y se imprime:
  - `[SECURITY][WARN] FLASK_SECRET_KEY no configurada; usando clave de desarrollo. No usar así en demo/producción.`

Esto evita depender silenciosamente de una clave fija en demos/producción.

### 2) Passwords por defecto solo como fallback + warning

En `bootstrap_users()` (solo cuando la tabla de usuarios está vacía):
- Admin:
  - Usa `DEFAULT_ADMIN_PASSWORD` si existe; si no, fallback `admin123`.
  - Si se usa el fallback (o el env es literalmente `admin123`), se imprime warning **sin** revelar el valor:
    - `password_configurada=True/False`, `password_len=n`
- Operador:
  - Usa `DEFAULT_OPERATOR_PASSWORD` si existe; si no, fallback `operador123`.
  - Warning equivalente si se usa default.

## Verificaciones rápidas (sin ejecutar Flask)

- Compilar:
  - `py -m py_compile app.py src/routes/*.py src/services/*.py src/system_core.py src/video_processor.py`

## Notas de seguridad

- No se imprime ninguna contraseña completa en logs.
- No se tocaron rutas, endpoints, HTML o JavaScript.
- `.gitignore` fue revisado y cubre archivos sensibles / pesados (env, config local, DBs, modelos, uploads y resultados).

## Variables de entorno recomendadas (ejemplo, sin valores reales)

- `FLASK_SECRET_KEY=<clave_larga_generada>`
- `DEFAULT_ADMIN_PASSWORD=<contraseña_segura>`
- `DEFAULT_OPERATOR_PASSWORD=<contraseña_segura>`

## Logs sensibles (revisión)

- Se evitó imprimir contraseñas completas (solo `password_configurada` y `password_len`).
- Se revisó que no se esté imprimiendo `FLASK_SECRET_KEY` ni volcados completos de `.env`.
- RTSP/ONVIF: no se agregaron logs nuevos con credenciales; si en el futuro se imprime una URL RTSP, debe enmascararse (p. ej. `rtsp://user:***@host/...`).

## Permisos de rutas (revisión)

Revisión básica: las rutas administrativas permanecen con `role_required("admin")` y las del operador con `role_required("operator")` / `login_required` según correspondía. No se hicieron cambios de permisos en esta mejora para evitar riesgo.

## Pendientes post-defensa

- CSRF (no implementado en este cambio por riesgo de romper formularios/POST).
