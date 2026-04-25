# deployment_checklist.md â€“ Lista de verificaciÃ³n para puesta en marcha

Esta lista de verificaciÃ³n consolida requisitos y acciones para desplegar el prototipo **RPAS Micro** en un entorno de laboratorio/demostraciÃ³n, alineado con inferencia estricta en GPU y operaciÃ³n RTSP/ONVIF.

## 1) Hardware (NVIDIA GPU)

- [ ] GPU NVIDIA disponible (objetivo: **RTX 4060** o equivalente).
- [ ] Drivers NVIDIA instalados y funcionales (`nvidia-smi`).
- [ ] RefrigeraciÃ³n adecuada (evitar throttling por temperatura).

## 2) CUDA / PyTorch (validaciÃ³n previa)

- [ ] Verificar CUDA desde Python:
  - [ ] `python -c "import torch; print(torch.cuda.is_available())"` retorna `True`.
- [ ] Confirmar dispositivo requerido por el prototipo:
  - [ ] `YOLO_CONFIG["device"]` estÃ¡ configurado como `cuda:0`.

## 3) Dependencias de software

- [ ] Python 3.10+ instalado.
- [ ] `pip` actualizado.
- [ ] (Opcional recomendado) FFmpeg instalado si se requiere soporte adicional de codecs/transcodificaciÃ³n.

## 4) InstalaciÃ³n del proyecto (Python)

- [ ] Crear entorno virtual:
  - [ ] Windows: `python -m venv venv_new`
  - [ ] Activar: `.\venv_new\Scripts\Activate.ps1`
- [ ] Instalar dependencias:
  - [ ] `python -m pip install -r requirements.txt`
- [ ] Validar librerÃ­as crÃ­ticas:
  - [ ] `python -c "import flask, cv2; import ultralytics; from onvif import ONVIFCamera; print('OK')"`

## 5) CÃ¡mara IP y red (RTSP)

- [ ] Confirmar conectividad IP entre servidor y cÃ¡mara (misma subred o ruta vÃ¡lida).
- [ ] Validar RTSP fuera del sistema (VLC recomendado):
  - [ ] La URL RTSP reproduce correctamente.
- [ ] Verificar puertos:
  - [ ] RTSP (tÃ­picamente `554`) accesible desde el servidor.
- [ ] Validar credenciales RTSP (si aplica).

## 6) ONVIF (Auto-Discovery PTZ)

- [ ] ONVIF habilitado en la cÃ¡mara (segÃºn fabricante).
- [ ] Usuario/contraseÃ±a ONVIF vÃ¡lidos.
- [ ] Puerto ONVIF accesible (tÃ­picamente `80`).
- [ ] Validar autodescubrimiento:
  - [ ] `GET /api/camera_status` retorna `{"is_ptz_capable": true}` para cÃ¡maras PTZ con ONVIF funcional.
- [ ] Confirmar comportamiento fail-safe:
  - [ ] Si ONVIF falla, el sistema reporta `is_ptz_capable = false` y bloquea `/ptz_move` y `/ptz_stop`.

## 7) Variables de entorno recomendadas

- [ ] Seguridad / sesiÃ³n:
  - [ ] `FLASK_SECRET_KEY` definido (no utilizar valores por defecto en operaciÃ³n real).
- [ ] Host/puerto:
  - [ ] `FLASK_HOST` (por defecto `0.0.0.0`)
  - [ ] `FLASK_PORT` (por defecto `5000`)
- [ ] Modo debug:
  - [ ] `FLASK_DEBUG=0` en entornos no interactivos.
- [ ] Cookies de sesiÃ³n (segÃºn operaciÃ³n):
  - [ ] `SESSION_COOKIE_SECURE=true` bajo HTTPS.
  - [ ] `SESSION_COOKIE_SAMESITE=Strict|Lax` segÃºn polÃ­tica.
- [ ] Credenciales iniciales (si se desea parametrizar):
  - [ ] `DEFAULT_ADMIN_PASSWORD`
  - [ ] `DEFAULT_OPERATOR_PASSWORD`

## 8) VerificaciÃ³n funcional post-arranque

- [ ] Iniciar servidor:
  - [ ] Windows: `.\start_server.ps1`
  - [ ] Alternativa: `python app.py`
- [ ] Acceder desde navegador:
  - [ ] `http://localhost:5000`
- [ ] Confirmar monitoreo en vivo:
  - [ ] Video se visualiza y el estado se actualiza periÃ³dicamente.
- [ ] Confirmar inferencia:
  - [ ] La UI muestra alertas cuando el objetivo es detectado.
- [ ] Confirmar UI condicional:
  - [ ] PTZ detectado â†’ aparece el panel PTZ.
  - [ ] No PTZ / falla ONVIF â†’ no aparece el panel PTZ.


