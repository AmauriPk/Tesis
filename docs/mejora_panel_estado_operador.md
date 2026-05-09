# Mejora UI: panel/barra de estado del operador

## Qué se agregó

En el dashboard del operador (pestaña **Procesamiento de Flujo**) se agregó un panel visual **“Sistema”** que resume el estado del sistema sin cambiar lógica interna.

## Archivos tocados

- `templates/index.html` (nuevo bloque HTML del panel)
- `static/dashboard.js` (polling y render del panel)
- `static/style.css` (estilos discretos + clases de estado)

## Endpoints usados (existentes)

- `GET /api/camera_status`
- `GET /api/auto_tracking`
- `GET /api/inspection_mode`
- `GET /detection_status`

No se agregaron endpoints nuevos.

## Estados mostrados

- Cámara: conectada/sin señal/no disponible (según `rtsp.stale_over_5s` / `rtsp.error`)
- Tipo de cámara: PTZ/Fija (según `camera_type`)
- PTZ: listo/no listo (según `configured_is_ptz`)
- Tracking automático: activo/inactivo (`/api/auto_tracking`)
- Inspección automática: activa/inactiva (`/api/inspection_mode`)
- Última detección: `last_update` o “Sin detección” (`/detection_status`)
- Estado general: usa `status` y cambia color si hay detección o si no hay señal (`/detection_status` + `camera_status`)

## Cómo probar

1. `py scripts/run_dev.py` (con el Python/venv correcto).
2. Login como operador.
3. Ir a pestaña **Procesamiento de Flujo**.
4. Verificar que el panel “Sistema” se actualiza cada ~5s (y detección cada ~2s).
5. Activar/desactivar Tracking e Inspección y verificar que el panel refleja el cambio.

## Riesgos conocidos

- Si el RTSP no entrega `last_frame_age_s` (o si el reader retorna error), el panel mostrará “No disponible/Sin señal”. Esto no afecta la lógica interna; solo la UI.

