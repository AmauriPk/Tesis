# Análisis de Seguridad — SIRAN

Fecha: 2026-05-07

---

## Tabla de hallazgos

| Prioridad | Problema | Archivo | Riesgo | Recomendación |
|---|---|---|---|---|
| Alta | Contraseñas por defecto hardcodeadas: `"admin123"` y `"operador123"` en `bootstrap_users()` | `app.py` línea ~262-263 | Si se despliega sin configurar `DEFAULT_ADMIN_PASSWORD` / `DEFAULT_OPERATOR_PASSWORD`, las cuentas quedan con credenciales triviales | Documentar en README que estas variables deben configurarse antes de producción. Agregar warning en consola si se usan los defaults. |
| Alta | `RTSP_CONFIG` default credentials: `"usuario"` y `"password"` | `config.py` líneas 14-16 | Si el `.env` no define `RTSP_USERNAME`/`RTSP_PASSWORD`, se usan valores genéricos. No expone el sistema directamente, pero podría revelar en logs qué credenciales se usaron. | Usar `""` como default y validar antes de conectar. |
| Media | No hay CSRF protection en endpoints POST | `app.py` y todos los blueprints | Susceptible a ataques CSRF desde otros dominios. En red local es bajo riesgo. | Implementar `Flask-WTF` o token CSRF en JS para producción. Post-defensa. |
| Media | `app.secret_key` tiene default inseguro: `"dev-secret-change-me"` | `app.py` línea 98 | Si no se configura `FLASK_SECRET_KEY`, las sesiones son predecibles | Documentar obligatoriedad. En producción es crítico cambiar. |
| Media | Los logs imprimen credenciales parciales: `"password_len": len(password)` | `ptz_worker_service.py` línea ~153, `admin_camera.py` línea ~196 | `password_len` no expone la contraseña directamente, pero confirma si hay contraseña configurada. Aceptable para debug. | Actual es correcto. No imprimir nunca el password real. ✅ |
| Media | `api_admin_cleanup_test_data` puede borrar todos los eventos y evidencias | `events.py` línea ~444 | Operación destructiva e irreversible. Solo accesible con `role_required("admin")`. | Considerar confirmación de 2 pasos o flag `dry_run` (ya existe). ✅ |
| Baja | Path traversal: `_safe_rel_path` bloquea solo `".."` en splits | `app.py` líneas ~1430-1433 | Si un path como `"foo/../../bar"` pasa sin split explícito, podría no bloquearse. `_safe_join` usa `os.path.abspath` + `startswith` — este sí bloquea completamente. | `_safe_rel_path` es defensa ligera; `_safe_join` es la defensa real. Correcto el patrón. ✅ |
| Baja | `config_camara.json` está en `.gitignore` pero contiene solo `{"is_ptz": bool}` | `config_camara.json` | No contiene credenciales. El riesgo real es mínimo. | OK. ✅ |
| Baja | `.env` está en `.gitignore` | `.gitignore` | OK. ✅ | — |
| Baja | `*.db` está en `.gitignore` | `.gitignore` | OK. ✅ | — |
| Baja | Subida de archivos: `allowed_file` valida extensión pero no tipo MIME | `app.py` línea ~188, `analysis.py` | Un archivo malicioso renombrado a `.jpg` pasaría la validación de extensión. OpenCV intentaría leerlo y fallaría silenciosamente. | Riesgo bajo dado el contexto (solo usuarios autenticados con `operator` role). Agregar validación MIME post-defensa. |
| Baja | `MAX_CONTENT_LENGTH` configurado (500MB por defecto) | `app.py` línea 123 | Limita tamaño de upload. Sin límite por tiempo de procesamiento. | Aceptable para el contexto académico. |
| Baja | `SESSION_COOKIE_SECURE` depende de variable de entorno | `app.py` línea 108 | Por defecto es `False` (HTTP). En producción HTTPS debe estar en `True`. | Documentar en README para despliegue productivo. |
| Baja | `SESSION_COOKIE_SAMESITE` = "Strict" por defecto | `app.py` línea 107 | Correcto para producción. ✅ | — |
| Baja | Rutas admin sin `role_required("admin")` | Verificado | NO existe ninguna ruta admin sin el decorator correcto. ✅ | — |
| Baja | Rutas operador sin `role_required` | Verificado | NO existe ninguna ruta de operador sin decorador. ✅ | — |
| Baja | Archivos sensibles en Git | Verificado | `.gitignore` protege: `.env`, `config_camara.json`, `*.db`, `*.pt`, `*.onnx`, `uploads/`, `static/results/`, `static/evidence/`, `venv_new/`, `dataset_*`. ✅ | Ver también análisis de gitignore. |
| Info | `__diag` endpoint solo disponible en debug + localhost | `app.py` línea ~1399-1413 | Correcto. Bloquea en producción. ✅ | — |

---

## Resumen de acciones

| Acción | Momento |
|---|---|
| Documentar en README que `DEFAULT_ADMIN_PASSWORD` y `FLASK_SECRET_KEY` son **obligatorias** en producción | Antes de la defensa |
| Agregar warning de consola si se usa default de admin | Antes de la defensa (baja intrusión) |
| CSRF protection | Post-defensa |
| Validación de tipo MIME en uploads | Post-defensa |
| Cambiar defaults de RTSP_CONFIG a strings vacíos | Post-defensa |

---

## Estado de .gitignore para archivos sensibles

| Archivo/Patrón | En .gitignore | Estado |
|---|---|---|
| `.env` | ✅ | OK |
| `config_camara.json` | ✅ | OK |
| `*.db`, `*.db-shm`, `*.db-wal` | ✅ | OK |
| `*.pt`, `*.pth` | ✅ | OK |
| `*.onnx`, `*.tflite` | ✅ | OK |
| `venv_new/` | ✅ | OK |
| `uploads/` | ✅ | OK |
| `static/results/` | ✅ | OK |
| `static/evidence/` | ✅ | OK |
| `static/top_detections/` | ✅ | OK |
| `dataset_entrenamiento/` | ✅ | OK |
| `dataset_recoleccion/` | ✅ | OK |
| `runs/` | ✅ | OK |
| `.claude/` | ✅ | OK |
