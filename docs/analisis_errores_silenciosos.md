# Análisis de Errores Silenciosos — SIRAN

Fecha: 2026-05-07

---

## Tabla de hallazgos

| Archivo | Línea aprox. | Bloque | Qué podría ocultar | Recomendación | Cambiar ahora |
|---|---|---|---|---|---|
| `app.py` | 389 | `except Exception: pass` en `DetectionEventWriter._connect` (bloque PRAGMA) | Falla al aplicar WAL/synchronous — el sistema corre con journaling lento sin saberlo | Agregar `print(f"[EVENT_DB][WARN] pragma err={e}")` — log de bajo ruido | Sí (bajo riesgo) |
| `app.py` | 677 | `except Exception: pass` en `_update_active_event` (best bbox parsing) | Falla al parsear bbox — la evidencia se guarda sin coordenadas sin aviso | Agregar `print(f"[EVENT][WARN] bbox_parse err={e}")` | Sí (bajo riesgo) |
| `app.py` | 495 | `except Exception: pass` en `_update_active_event` (evidence path) | Falla al registrar el path de la evidencia sin aviso | Agregar log similar | Sí (bajo riesgo) |
| `app.py` | 1676-1678 | `except Exception: pass` en bootstrap `guardar_config_camara` | Si falla la escritura de config_camara.json al arranque, el sistema continúa sin configuración persistida | Agregar `print(f"[INIT][WARN] guardar_config_camara failed: {e}")` | Sí (bajo riesgo) |
| `video_processor.py` | 659 | `except cv2.error: pass` en inferencia YOLO | Error de OpenCV durante inferencia — frame descartado silenciosamente | Conservar: silenciar cv2.error en el loop de video es correcto (frames corruptos son normales en RTSP) | No — correcto |
| `video_processor.py` | 661 | `except RuntimeError: pass` en inferencia YOLO | Error de PyTorch/CUDA — frame descartado sin log cuando hay error de GPU | Agregar `print(f"[INFERENCE][WARN] RuntimeError: {e}")` throttleado (no más de 1 log/5s) | Condicional (ver nota) |
| `video_processor.py` | 678-679 | `except Exception: pass` en `_save_evidence` (llamada) | Si falla el guardado de evidencia, no hay ningún log | Agregar `print(f"[EVIDENCE][ERROR] save failed: {e}")` | Sí (bajo riesgo) |
| `video_processor.py` | 703-704 | `except Exception: pass` en enqueue de métricas | Si falla el enqueue, no hay log | Agregar `print(f"[METRICS][WARN] enqueue failed: {e}")` throttleado | Sí (bajo riesgo) |
| `video_processor.py` | 726-727 | `except Exception: pass` en `update_tracking_target` | Si falla la actualización del target PTZ, el tracking se rompe silenciosamente | Agregar `print(f"[TRACKING][WARN] update_target failed: {e}")` | Sí (bajo riesgo) |
| `src/services/ptz_state_service.py` | 80 | `except Exception: pass` en `update_tracking_target` | Si falla el parseo del payload de tracking, no hay rastro | Agregar `print(f"[PTZ_STATE][WARN] update_tracking_target err={e}")` | Sí (bajo riesgo) |
| `src/services/camera_state_service.py` | 99-101 | `except Exception: pass` en `set_configured_camera_type` (guardar) | Si falla la escritura de config_camara.json, el sistema continúa sin persistir | El comentario ya lo documenta como "fail-safe". Agregar log. | Sí (bajo riesgo) |
| `src/routes/events.py` | ~483-488 | `except Exception: pass` en cleanup_test_data DB counts | Si falla la consulta de COUNT, los totales mostrados al admin son 0 sin aviso | Agregar `print(f"[CLEANUP][WARN] count query err={e}")` | Sí (bajo riesgo) |
| `src/routes/admin_camera.py` | ~267-268 | `except Exception: pass` en guardar_config_camara post-test | Si falla persistir el resultado del test de conexión, el estado no se guarda | Agregar `print(f"[ADMIN_CAM][WARN] guardar_config err={e}")` | Sí (bajo riesgo) |
| `src/routes/admin_camera.py` | ~272-273 | `except Exception: pass` en DB sync post-test | Si falla la sincronización con DB después del test, la discrepancia no se reporta | Agregar log | Sí (bajo riesgo) |
| `src/routes/analysis.py` | 143-148 | `except Exception: pass` en limpieza del archivo temp | Si falla borrar el temp, queda basura en uploads/ | `print(f"[ANALYSIS][WARN] temp cleanup failed: {e}")` | Sí (bajo riesgo) |

---

## Nota sobre `RuntimeError` en inferencia (video_processor.py)

El bloque `except RuntimeError: pass` en el loop de inferencia YOLO puede silenciar errores graves de CUDA/GPU. Sin embargo, agregar un log sin throttle generaría ruido excesivo (potencialmente cientos de líneas por segundo si hay un problema de GPU). 

**Recomendación**: Agregar un log throttleado: si pasan más de 5 segundos desde el último log de ese error, imprimir una vez.

Ejemplo:
```python
except RuntimeError as e:
    now = time.time()
    if (now - self._last_runtime_err_log) > 5.0:
        print(f"[INFERENCE][WARN] RuntimeError (throttled): {e}")
        self._last_runtime_err_log = now
```

Este cambio requiere agregar `self._last_runtime_err_log = 0.0` en `__init__` — cambio de bajo riesgo pero que modifica `__init__`. **No aplicar ahora** — documentar como mejora para después de la defensa.

---

## Cambios aplicados en esta sesión

- `app.py`: Logs agregados en bloques silenciosos de bajo riesgo en `DetectionEventWriter` y bootstrap.
- `video_processor.py`: Log en `_save_evidence`, `metrics enqueue`, `update_tracking_target`.
- `ptz_state_service.py`: Log en `update_tracking_target`.
- `camera_state_service.py`: Log en `set_configured_camera_type`.
