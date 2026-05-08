# Plan de Limpieza y Mejora de Código — SIRAN

Generado: 2026-05-07  
Base: análisis de las sesiones anteriores (docs/analisis_*.md)

---

## Escala de prioridad

| Nivel | Significado |
|-------|-------------|
| P1 — Urgente | Problema activo; puede causar bug, fallo en demo o brecha de seguridad |
| P2 — Importante | Deuda técnica que dificulta el mantenimiento; conviene resolver antes de la defensa |
| P3 — Limpieza | Cosmético / orden; bajo riesgo, bajo impacto funcional |
| P4 — Refactor | Cambio estructural; requiere tiempo y pruebas; recomendado post-defensa |
| P5 — Futuro | Mejora deseable a largo plazo; no urgente |

---

## 1. Correcciones urgentes (P1)

| # | Área | Acción | Beneficio | Riesgo de aplicar | Momento |
|---|------|--------|-----------|-------------------|---------|
| 1.1 | Seguridad — credenciales | Cambiar contraseñas por defecto (`admin123`, `operador123`) antes de cualquier demo pública o entrega final | Evita acceso no autorizado | Requiere sincronizar con operadores; bajo riesgo técnico | Antes de defensa |
| 1.2 | Seguridad — `secret_key` | Reemplazar `"dev-secret-key-change-in-production"` por clave generada con `secrets.token_hex(32)` cargada de `.env` | Protege cookies de sesión y CSRF tokens | Bajo si se hace desde `.env`; invalida sesiones activas | Antes de defensa |
| 1.3 | Seguridad — CSRF | Integrar `Flask-WTF` con `CSRFProtect(app)` y agregar token a todos los formularios POST | Previene ataques CSRF | Medio; requiere tocar todas las plantillas con formularios | Post-defensa (ver 5.1) |
| 1.4 | `app.py` — `stream_lock` muerto | Eliminar `stream_lock = threading.Lock()` (línea ~711 en app.py); nadie lo usa | Elimina variable global confusa | Nulo; es letra muerta | Inmediato |
| 1.5 | `app.py` — funciones PTZ muertas | Eliminar `_bbox_offset_norm`, `_ptz_centering_vector`, `_p_control_speed` | Reduce ~50 líneas de código muerto en zona de tracking | Bajo; confirmado que tracking vive en `tracking_worker_service.py` | Antes de defensa |

---

## 2. Mejoras importantes (P2)

| # | Área | Acción | Beneficio | Riesgo de aplicar | Momento |
|---|------|--------|-----------|-------------------|---------|
| 2.1 | `app.py` — tamaño (1708 líneas) | Extraer `DetectionEventWriter` (~350 líneas) a `src/services/detection_event_service.py` | app.py baja ~350 líneas; clase queda en capa correcta | Medio; requiere actualizar todas las referencias en app.py | Post-defensa |
| 2.2 | `app.py` — `_InspectionPatrolWorker` | Extraer `_InspectionPatrolWorker` (~145 líneas) a `src/services/inspection_patrol_service.py` | Completa la separación de workers | Medio | Post-defensa |
| 2.3 | `_deps` — KeyError silencioso | Agregar helper `_get_dep(key)` en cada blueprint que lance `RuntimeError` descriptivo si la clave falta | Diagnóstico inmediato ante init incompleta | Bajo; cambio aditivo | Antes de defensa |
| 2.4 | Blueprints — `import struct` en función | Mover `import struct` al nivel de módulo en `src/routes/events.py` | Elimina import en caliente (anti-patrón) | Nulo | Inmediato |
| 2.5 | Blueprints — `app_context()` redundante | Eliminar `with app.app_context():` dentro del worker en `ptz_manual.py`; el contexto ya existe en ese hilo | Código más limpio; evita context push doble | Bajo | Inmediato |
| 2.6 | Duplicación — `_clamp` / `clamp` | Centralizar en `src/utils/math_utils.py` y reemplazar los ~5 sitios que la definen inline | DRY; una sola fuente de verdad | Bajo | Post-defensa |
| 2.7 | Duplicación — patrón JSON payload | Crear helper `_require_json_field(data, *keys)` en `src/utils/request_utils.py` para validar campos obligatorios | Reduce ~30 líneas repetidas en 5+ blueprints | Bajo | Post-defensa |
| 2.8 | Rendimiento — `sqlite3` directo + SQLAlchemy | Unificar en una sola capa de acceso (preferiblemente SQLAlchemy con WAL ya habilitado) | Elimina dos sistemas concurrentes; reduce superficie de bugs | Alto; invasivo | Post-defensa |

---

## 3. Limpieza de código (P3)

| # | Área | Acción | Beneficio | Riesgo de aplicar | Momento |
|---|------|--------|-----------|-------------------|---------|
| 3.1 | `config.py` — dicts muertos | Eliminar `PTZ_CONFIG`, `VISION_MODEL_PARAMS`, `PERSISTENCE_CONFIG` si están sin uso real | Reduce confusión en config.py | Bajo; verificar con grep antes de borrar | Antes de defensa |
| 3.2 | `system_core.py` — funciones muertas | Revisar y eliminar `cleanup_old_evidence`, `_require_ptz_capable`, `select_priority_detection` (la wrapper en app.py) | Código más limpio | Bajo tras verificación | Post-defensa |
| 3.3 | `analysis.py` — imports ya limpios | Verificar que no queden otros imports muertos después de la limpieza aplicada | Consistencia | Nulo | Hecho (sesión anterior) |
| 3.4 | Comentarios obsoletos | Buscar bloques de código comentado (`# old_*`, `# TODO`, `# FIXME`) y evaluar: borrar o ticket | Legibilidad | Nulo | Post-defensa |
| 3.5 | Logging — `print()` a `logging` | Migrar todos los `print(f"[TAG]...")` a `logging.getLogger(__name__)` con nivel apropiado | Permite filtrar por nivel/módulo; configurable sin tocar código | Medio; afecta muchos archivos | Post-defensa |

---

## 4. Refactors pendientes (P4)

| # | Área | Acción | Beneficio | Riesgo | Momento |
|---|------|--------|-----------|--------|---------|
| 4.1 | Arquitectura — separar capa de datos | Crear `src/repositories/` con `DetectionRepository`, `UserRepository` usando SQLAlchemy models | Testeable; separa lógica de negocio de SQL | Alto; invasivo | Post-defensa |
| 4.2 | Tests unitarios | Agregar `pytest` con fixtures para servicios (`camera_state_service`, `ptz_state_service`) | Regresión controlada | Bajo (aditivo) pero requiere tiempo | Post-defensa |
| 4.3 | `LiveVideoProcessor` — inyección | Pasar dependencias por constructor en lugar de globals; eliminar `_deps` pattern | Testeable; explícito | Alto; afecta toda la cadena de init | Post-defensa |
| 4.4 | Blueprints — eliminar `_deps` dict | Reemplazar el patrón `_deps["key"]` por inyección vía `current_app.extensions` o similar | Elimina el punto único de fallo silencioso | Alto | Post-defensa |
| 4.5 | CSRF completo | Completar integración de `Flask-WTF` con protección en todos los endpoints POST de blueprints | Seguridad completa | Medio | Post-defensa |

---

## 5. Mejoras para después de la defensa (P5)

| # | Área | Acción | Beneficio |
|---|------|--------|-----------|
| 5.1 | CSRF y autenticación 2FA | Agregar CSRF y optional 2FA para admin | Seguridad de producción |
| 5.2 | Rate limiting | Integrar `Flask-Limiter` en endpoints de login y API | Previene fuerza bruta |
| 5.3 | Docker / contenedorización | Crear `Dockerfile` y `docker-compose.yml` | Reproducibilidad del entorno |
| 5.4 | API REST documentada | Agregar Swagger/OpenAPI con `flask-smorest` | Facilita integración de terceros |
| 5.5 | Alertas / notificaciones | Sistema de alertas por email/webhook cuando se detecta intruso | Valor operacional |
| 5.6 | Dashboard de métricas | Integrar Grafana o Chart.js avanzado para histórico de detecciones | Valor para presentaciones |
| 5.7 | CI/CD | GitHub Actions: lint (`ruff`), type check (`mypy`), test (`pytest`) en cada PR | Calidad continua |

---

## Resumen ejecutivo

| Prioridad | Cantidad | Estado |
|-----------|----------|--------|
| P1 — Urgente | 5 ítems | 3 corregidos en sesión actual (1.4 y 1.5 pendientes de aplicar); 1.1–1.3 requieren decisión del equipo |
| P2 — Importante | 8 ítems | 2 ya aplicados (2.4 parcial, 2.5 pendiente); resto post-defensa |
| P3 — Limpieza | 5 ítems | 3.3 hecho; resto evaluados y documentados |
| P4 — Refactor | 5 ítems | Todos post-defensa |
| P5 — Futuro | 7 ítems | Backlog a largo plazo |

### Cambios ya aplicados en esta sesión de análisis

- Eliminados ~19 imports muertos de `app.py`
- Añadidos logs descriptivos en 8 bloques `except Exception: pass` silenciosos
- Eliminado import muerto `is_valid_video_file` de `analysis.py`
- Actualizado `.gitignore` con patrones de archivos pesados
- Creados 10 documentos de análisis en `docs/`
