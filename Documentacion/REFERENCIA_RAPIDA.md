# referencia_rapida.md â€“ Cheat Sheet (1 pÃ¡gina)

## Inicio del servidor (comandos)

### Windows (PowerShell)

- Ejecutar desde la raÃ­z del proyecto:
  - `.\start_server.ps1`

### Inicio directo (cualquier sistema)

1. Activar entorno virtual.
2. Ejecutar:
   - `python app.py`

## Acceso desde el navegador

- URL por defecto: `http://localhost:5000`
- En red local: `http://<IP_DEL_SERVIDOR>:5000` (si el host estÃ¡ en `0.0.0.0`).

## Endpoints clave (operaciÃ³n)

- Stream en vivo: `GET /video_feed`
- Estado de hardware (PTZ/fija): `GET /api/camera_status`
- Control PTZ (condicional): `POST /ptz_move`, `POST /ptz_stop`
- DetecciÃ³n manual: `POST /upload_detect`

## Troubleshooting rÃ¡pido (3 pasos)

### 1) RTSP no muestra video

1. Validar la URL RTSP y credenciales reproduciendo en VLC.
2. Verificar conectividad y puertos (RTSP tÃ­pico: `554`) y firewall local.
3. Confirmar que la cÃ¡mara y el servidor estÃ¡n en la misma red o ruta vÃ¡lida.

### 2) ONVIF no detecta PTZ (aparece â€œCÃ¡mara Fijaâ€)

1. Confirmar ONVIF habilitado en la cÃ¡mara (segÃºn fabricante) y credenciales ONVIF correctas.
2. Verificar conectividad al host/puerto ONVIF (tÃ­pico `80`) desde el servidor.
3. Consultar `GET /api/camera_status`. El sistema aplica **fail-safe**: cualquier falla ONVIF provoca `is_ptz_capable = false`.

### 3) YOLO26 no carga en GPU / no hay inferencia

1. Verificar GPU/drivers: `nvidia-smi`.
2. Verificar CUDA en Python: `python -c "import torch; print(torch.cuda.is_available())"`.
3. Confirmar `YOLO_CONFIG["device"] == "cuda:0"` y que `YOLO_CONFIG["model_path"]` apunta a un `.pt` existente.


