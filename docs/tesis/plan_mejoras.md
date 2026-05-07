# Plan de Mejoras — SIRAN

---

## 1. Mejoras críticas (antes de la defensa o inmediatamente después)

### Backend

| Mejora | Justificación | Impacto | Dificultad | Antes/después de defensa |
|---|---|---|---|---|
| Agregar `static/results/*.mp4`, `*.jpg`, `*.avi` al `.gitignore` | Archivos binarios pesados no deben estar en Git | Alto | Muy baja | **Antes** |
| Documentar prominentemente el cambio de contraseñas por defecto | Contraseñas `admin123`/`operador123` son inseguras | Alto | Muy baja | **Antes** |
| Verificar que ningún archivo sensible esté en el repositorio | `.env`, `config_camara.json`, `*.db`, `*.pt` | Crítico | Muy baja | **Antes** |

---

## 2. Mejoras importantes (corto plazo: 2-4 semanas tras defensa)

### Backend

| Mejora | Justificación | Impacto | Dificultad | Descripción |
|---|---|---|---|---|
| Política de retención de evidencias | `static/evidence/` crece indefinidamente | Alto | Baja | Purga automática de archivos con más de 30 días; o límite de N archivos |
| Política de retención de resultados | `static/results/` crece indefinidamente | Alto | Baja | Limpiar resultados con más de 7 días al inicio del servidor |
| Índices en `detections.db` | Consultas lentas con muchos registros | Medio | Baja | `CREATE INDEX IF NOT EXISTS idx_events_started_at ON detection_events(started_at)` |
| Histéresis en tracking PTZ | El tracking puede oscilar con detecciones ruidosas | Medio | Media | Solo mover PTZ si el error supera el umbral por N frames consecutivos |

### Seguridad

| Mejora | Justificación | Impacto | Dificultad | Descripción |
|---|---|---|---|---|
| HTTPS / TLS en el servidor | Credenciales e imágenes viajan en texto plano | Alto | Media | Configurar nginx como proxy reverso con certificado SSL, o usar `flask_talisman` |
| Expiración de sesión por inactividad | Sin expiración, la sesión puede persistir indefinidamente | Medio | Baja | `SESSION_COOKIE_PERMANENT=True` + `PERMANENT_SESSION_LIFETIME` en Flask config |

### Documentación

| Mejora | Justificación | Impacto | Dificultad | Descripción |
|---|---|---|---|---|
| README.md completo | El repositorio no tiene README | Alto | Muy baja | Ya incluido en este commit |
| Docstrings en funciones principales | Facilita comprensión y mantenimiento | Medio | Baja | Al menos las funciones públicas de cada módulo |

---

## 3. Mejoras deseables (mediano plazo: 1-3 meses)

### Backend

| Mejora | Justificación | Impacto | Dificultad | Descripción |
|---|---|---|---|---|
| Refactor modular de `app.py` | Archivo demasiado grande para mantener | Alto | Alta | Extraer rutas en Blueprints por módulo |
| Pruebas unitarias automatizadas | Sin pruebas, cada cambio es un riesgo | Alto | Media | Iniciar con pruebas para `video_export_service` y `event_service` |
| Timeout y manejo de errores en FFmpeg | La transcodificación puede bloquearse | Medio | Baja | Agregar timeout al `subprocess.run` de FFmpeg |
| Filtro Kalman para tracking predictivo | El tracking pierde el objetivo con oclusión breve | Medio | Alta | Implementar posición estimada cuando no hay detección |
| Limitar tamaño de cola PTZ | La cola puede acumular comandos obsoletos | Medio | Baja | `queue.Queue(maxsize=3)` + política drop-oldest |

### Frontend

| Mejora | Justificación | Impacto | Dificultad | Descripción |
|---|---|---|---|---|
| Diseño responsive básico | No usable en tableta/móvil | Medio | Media | Breakpoints CSS para pantallas < 768px |
| Indicador visual de confianza en vivo | El operador no ve la confianza de forma inmediata | Bajo | Baja | Badge con valor de confianza en el stream en vivo |
| Notificación de nueva detección | Sin notificación sonora/visual prominente | Medio | Baja | Notificación del navegador (`Notification API`) al confirmar detección |

### Dataset

| Mejora | Justificación | Impacto | Dificultad | Descripción |
|---|---|---|---|---|
| Script de reentrenamiento integrado | El proceso de reentrenamiento es manual y está fuera del sistema | Medio | Alta | Botón en panel admin que ejecuta `yolo train` con el dataset clasificado |
| Vista previa de imagen en clasificación | El admin clasifica sin ver la imagen claramente | Bajo | Baja | Modal de imagen grande al hacer clic antes de clasificar |

---

## 4. Mejoras futuras (largo plazo: >3 meses)

### Backend / Arquitectura

| Mejora | Justificación | Impacto | Dificultad | Descripción |
|---|---|---|---|---|
| Soporte para múltiples cámaras | El sistema actual solo soporta 1 cámara | Alto | Muy alta | Refactorizar a arquitectura de workers por cámara |
| Alertas externas (email/webhook/SMS) | El operador puede no estar frente a la pantalla | Alto | Media | Integrar Flask-Mail o webhooks (Slack, Telegram) |
| Autenticación 2FA | Seguridad adicional para el administrador | Medio | Media | TOTP (Google Authenticator) |
| Análisis de trayectoria | El sistema no analiza el patrón de vuelo | Bajo | Muy alta | Registrar posición del centroide por evento y generar mapa de trayectoria |
| Exportación de reportes en PDF | Formato estándar para informes formales | Bajo | Media | Usar WeasyPrint o ReportLab |

### Detección / IA

| Mejora | Justificación | Impacto | Dificultad | Descripción |
|---|---|---|---|---|
| Modelo multiclase (dron + tipo de dron) | El modelo actual solo detecta "dron" genérico | Medio | Muy alta | Ampliar dataset y reentrenar con clases (cuadricóptero, de ala fija, etc.) |
| Clasificación de comportamiento | Distinguir entre vuelo normal e intrusión | Bajo | Muy alta | Requiere análisis de secuencia temporal |
| Mejora de imagen previa a inferencia | Mejorar detección en condiciones adversas | Medio | Media | CLAHE, denoising previo a la inferencia |

### Despliegue

| Mejora | Justificación | Impacto | Dificultad | Descripción |
|---|---|---|---|---|
| Contenedorización con Docker | Facilita instalación y despliegue reproducible | Alto | Media | Dockerfile + docker-compose con GPU passthrough |
| Gunicorn + nginx en producción | Flask dev server no apto para producción | Alto | Baja | `gunicorn -w 4 --worker-class=gthread app:app` |
| Systemd service | Inicio automático del sistema | Medio | Baja | Unit file para iniciar SIRAN al arrancar el servidor |
