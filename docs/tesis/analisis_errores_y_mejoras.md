# Análisis de Errores y Mejoras — SIRAN

## 1. Resumen del estado actual

El sistema SIRAN es un prototipo funcional con capacidades completas de detección, tracking, análisis manual y gestión de dataset. El código central se concentra en un único archivo `app.py` de aproximadamente 3800 líneas, lo que representa el principal riesgo de mantenimiento a futuro. La primera refactorización ya fue ejecutada (extracción del servicio de exportación de video a `src/services/video_export_service.py`). El sistema carece de pruebas automatizadas, y algunos patrones de manejo de errores pueden ocultar problemas silenciosamente.

---

## 2. Tabla de errores, riesgos y mejoras

| Prioridad | Área | Problema | Impacto | Recomendación |
|---|---|---|---|---|
| **ALTA** | Arquitectura | `app.py` demasiado grande (~3800 líneas) | Dificulta mantenimiento, extensión y revisión de código | Extraer módulos: auth, events, dataset, jobs, metrics, admin |
| **ALTA** | Seguridad | Sin HTTPS/TLS en la versión actual | Credenciales e imágenes viajan en texto plano en red local | Configurar certificado SSL o usar proxy reverso nginx con TLS |
| **ALTA** | Seguridad | Contraseñas por defecto en código (`admin123`, `operador123`) | Riesgo si el sistema se expone en red sin cambiar contraseñas | Documentar prominentemente; bloquear acceso si contraseña es default |
| **ALTA** | Seguridad | `config_camara.json` no siempre ignorado por Git en todos los entornos | Riesgo de subir credenciales de cámara | Ya en `.gitignore`; verificar que no esté staged nunca |
| **ALTA** | Estabilidad | `static/results/` contiene MP4/JPG de prueba que no deberían estar en Git | Archivos binarios pesados en el repositorio | Agregar `static/results/*.mp4` y `static/results/*.jpg` a `.gitignore` |
| **ALTA** | Estabilidad | Sin pruebas automatizadas | Cualquier refactor puede romper funcionalidad sin saberlo | Agregar pruebas unitarias para las funciones críticas (video_export, events) |
| **ALTA** | PTZ | Saturación de cola PTZ si se envían comandos muy rápidamente | La cola puede acumular movimientos obsoletos, causando comportamiento errático | Implementar política "drop oldest" o limitar comandos por segundo desde el frontend |
| **MEDIA** | Mantenimiento | Lógica mezclada: rutas Flask, servicios, workers y helpers en un mismo archivo | Dificulta razonar sobre el sistema y hacer cambios aislados | Refactor modular incremental (ver plan de refactorización) |
| **MEDIA** | Estabilidad | Evidencias en `static/evidence/` sin política de retención | Crecimiento indefinido del disco | Implementar purga automática de evidencias con más de N días |
| **MEDIA** | Estabilidad | Videos en `static/results/` sin política de retención | Crecimiento indefinido del disco | Implementar limpieza automática de resultados viejos |
| **MEDIA** | Tracking | El tracking PTZ puede oscilar (hunting) con detecciones ruidosas | La cámara se mueve innecesariamente, consume energía y puede alarmar | Agregar histéresis: solo mover si el error supera el umbral por N frames consecutivos |
| **MEDIA** | Tracking | Sin predicción de posición (tracking reactivo puro) | Al perder la detección brevemente, el tracking se interrumpe | Implementar filtro de Kalman o suavizado exponencial de posición objetivo |
| **MEDIA** | Video | Transcodificación FFmpeg bloquea el hilo del job | Para videos largos, puede demorar significativamente | Ejecutar FFmpeg en subproceso con timeout; registrar advertencia si tarda >60s |
| **MEDIA** | Base de datos | `detections.db` puede crecer indefinidamente | Sin límite de filas, las consultas se vuelven lentas con el tiempo | Agregar índices en `timestamp` y `started_at`; implementar archivado o purga |
| **MEDIA** | Frontend | Sin diseño responsive | El sistema es difícil de usar en tabletas o teléfonos | Agregar breakpoints CSS mínimos para pantallas < 768px |
| **MEDIA** | Dataset | El reentrenamiento del modelo no está automatizado | El administrador debe ejecutar el entrenamiento YOLO manualmente fuera del sistema | Documentar el proceso de reentrenamiento; a futuro, integrar script de entrenamiento |
| **BAJA** | Código | `import ffmpeg` en app.py ya no se usa (la librería python-ffmpeg no se llama en el código) | Import innecesario, puede generar confusión | Verificar y eliminar el import si no se usa |
| **BAJA** | Código | Varios `except Exception: pass` sin log | Errores silenciosos que dificultan el diagnóstico | Agregar al menos `print(f"[WARN] {e}")` en los catch silenciosos críticos |
| **BAJA** | Seguridad | El endpoint `/__diag` está protegido solo por `FLASK_DEBUG` y IP | Si se olvida desactivar debug en producción, expone información del sistema | Documentar que `FLASK_DEBUG=False` siempre en producción |
| **BAJA** | Mantenimiento | Sin documentación de API formal (no hay Swagger/OpenAPI) | Dificulta entender la API sin leer el código | A futuro: generar documentación OpenAPI o mínimamente mantener `mapa_endpoints.md` |
| **BAJA** | Estabilidad | El bootstrap de usuarios crea `admin123`/`operador123` si la tabla está vacía | Si se borra la DB por error, las credenciales vuelven a los valores default | Documentar y agregar advertencia al log si se usa contraseña default |
| **BAJA** | Dataset | `api/revert_classification` mueve archivos sin validar si el destino ya existe | Podría sobreescribir un archivo | Agregar verificación y renombramiento si el destino existe |

---

## 3. Riesgos técnicos adicionales

### RT-01: Bloqueo por video largo en CPU

Si se sube un video de varios minutos para análisis y el servidor corre en CPU, el hilo del job puede estar ocupado durante decenas de minutos. Durante ese tiempo, si el servidor es single-threaded (modo desarrollo), otros requests pueden quedar bloqueados.

**Mitigación:** Flask en modo threaded (`FLASK_THREADED=True`) maneja múltiples requests; verificar que está configurado. Para producción, usar gunicorn con workers.

### RT-02: Desincronización entre `config_camara.json` y SQLite

El tipo de cámara se persiste en dos lugares: `config_camara.json` (fuente de verdad para PTZ) y SQLite (`camera_config`). Si uno se corrompe o se borra, el sistema puede comportarse de forma inconsistente.

**Mitigación:** el código ya prioriza `config_camara.json` sobre SQLite para el tipo PTZ. Documentar este comportamiento.

### RT-03: Queue PTZ sin límite efectivo de tamaño bajo carga

Si el operador mueve el joystick muy rápidamente y la latencia ONVIF es alta, la cola del PTZWorker puede acumular comandos. El efecto observado es que la cámara continúa moviéndose después de soltar el joystick.

**Mitigación:** implementar `queue.Queue(maxsize=3)` con política de drop; el frontend limita frecuencia de envío.

---

## 4. Orden sugerido para corregir

1. **Inmediato (antes de la defensa):**
   - Agregar `static/results/*.mp4`, `static/results/*.jpg`, `static/results/*.avi` al `.gitignore`
   - Verificar que `config_camara.json`, `.env`, `*.db`, `*.pt` no están en el repositorio
   - Documentar prominentemente el cambio de contraseñas por defecto en el README

2. **Corto plazo (mejoras de estabilidad):**
   - Implementar política de retención para evidencias y resultados
   - Agregar índices en las tablas de detecciones
   - Agregar histéresis al tracking

3. **Mediano plazo (calidad de código):**
   - Continuar el refactor modular de `app.py` (auth, events, dataset, jobs)
   - Agregar pruebas unitarias para los módulos extraídos
   - Reducir los `except Exception: pass` silenciosos

4. **Largo plazo (funcionalidades):**
   - Implementar HTTPS
   - Agregar filtro de Kalman para tracking predictivo
   - Soporte para múltiples cámaras
   - Automatización del reentrenamiento del modelo
