# Mejora de seguridad: validación de username en login (whitespace)

## Problema

El login aceptaba usernames con espacios al inicio o al final (p. ej. `"   admin   "`), porque se aplicaba `.strip()` antes de validar/buscar al usuario.

Esto “corrige” silenciosamente input inválido, lo cual es indeseable desde seguridad y control de credenciales.

## Causa

En `src/routes/auth.py` se hacía:

- `username = (request.form.get("username") or "").strip()`

Lo que convertía inputs con whitespace externo en un username distinto, sin rechazar.

## Solución aplicada

Se conserva el valor original y se valida antes de buscar el usuario:

- `raw_username = request.form.get("username") or ""`
- `username = raw_username.strip()`
- Si `raw_username != username` o `not username` → rechazar con el **mismo mensaje genérico**:
  - `"Credenciales inválidas."`

No se revela la razón exacta (no se dice “tienes espacios”) para evitar dar pistas.

## Casos cubiertos por pruebas

Archivo: `tests/test_auth_validation.py`

- Acepta:
  - `"admin"`
  - `"operador"`
- Rechaza:
  - `" admin"`, `"admin "`, `"   admin   "`
  - `"\tadmin"`, `"admin\t"`
  - `""`, `"   "`, `"\t"`
- Password no se modifica:
  - No se hace `.strip()` al password; `"p "` debe fallar.

