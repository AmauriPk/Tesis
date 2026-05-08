# Limpieza técnica mínima (bajo riesgo) — SIRAN

Fecha: 2026-05-08

## Qué se cambió

### 1) `src/routes/events.py`: mover `import struct` a nivel de módulo

- Antes: `import struct` estaba dentro de una función/ruta (scope local).
- Ahora: `import struct` está al inicio del archivo, junto con el resto de imports.

Motivo: mejora legibilidad y evita imports en caliente, sin cambiar comportamiento.

### 2) `src/routes/ptz_manual.py`: eliminar `with app.app_context()` redundante

- Se removió `with app.app_context():` dentro de la ruta `POST /ptz_move`.
- Se mantuvo exactamente la misma lógica: solo se des-indentó el bloque que lee `cfg` y deriva `host/username/password/port`.

Motivo: en una función de ruta Flask ya existe application/request context activo; el contexto extra es redundante y no aporta.

## Qué NO se tocó (por seguridad)

- No se eliminaron funciones “muertas” de PTZ en `app.py` (solo documentadas como pendientes).
- No se modificó lógica de tracking, inspección, PTZ workers, YOLO, `video_feed`, análisis manual, dataset o eventos (más allá del import).
- No se cambiaron endpoints, rutas, JSON ni permisos.
- No se tocó `config_camara.json` ni `.env`.

## Cómo se validó

- Compilación estática (sin ejecutar Flask):
  - `py_compile` de `app.py`, `src/routes/*.py`, `src/services/*.py`, `src/system_core.py`, `src/video_processor.py`

## Pruebas funcionales recomendadas

1. `py app.py`
2. Login operador → dashboard → video en vivo.
3. PTZ manual: mover y STOP.
4. Activar/desactivar tracking.
5. Activar/desactivar inspección.
6. Login admin → `admin_dashboard`.

