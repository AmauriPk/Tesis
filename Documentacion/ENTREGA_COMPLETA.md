# entrega_completa.md â€“ Manifiesto de entrega / Release Notes

## 1) Resumen ejecutivo de la entrega

El presente manifiesto describe los artefactos entregables del proyecto **â€œPrototipo de sistema de visiÃ³n artificial para la detecciÃ³n de RPAS Microâ€**, incluyendo su estructura de archivos y el rol tÃ©cnico de cada componente en el despliegue final.

## 2) Funcionalidades incluidas

- Dashboard web responsivo con pestaÃ±as:
  - Monitoreo en vivo (RTSP â†’ web).
  - DetecciÃ³n manual por carga de archivo (imagen/video).
- Inferencia en tiempo real con **YOLO26 end-to-end sin NMS** (objetos pequeÃ±os), ejecutada estrictamente en **GPU** mediante `ultralytics`.
- Procesamiento de video y render de anotaciones con `opencv-python`.
- Auto-Discovery ONVIF (onvif-zeep) para determinar **PTZ vs cÃ¡mara fija**.
- Control PTZ asÃ­ncrono (worker en background) y **Tracking AutomÃ¡tico** condicionado por el estado detectado.
- Mecanismo **fail-safe**: ante falla ONVIF o ausencia de PTZ, el sistema opera como cÃ¡mara fija y bloquea control mecÃ¡nico.

## 3) Estructura del proyecto (artefactos principales)

### 3.1 Archivos raÃ­z

- `app.py`  
  Backend Flask. Integra streaming RTSP, inferencia YOLO26 en GPU, autodescubrimiento ONVIF, control PTZ asÃ­ncrono y endpoints REST.

- `config.py`  
  ParÃ¡metros de ejecuciÃ³n: RTSP, YOLO, video, Flask, almacenamiento y lectura de variables de entorno.

- `requirements.txt`  
  Dependencias Python del proyecto (Flask, OpenCV, Ultralytics, onvif-zeep, etc.).

- `models.py`  
  Modelos SQLAlchemy: usuarios y configuraciÃ³n de cÃ¡mara (RTSP/ONVIF).

- `ptz_controller.py`  
  Encapsula control ONVIF PTZ (conexiÃ³n, perfiles, `ContinuousMove` y `Stop`).

- `detections.db`  
  Base de datos SQLite (usuarios/configuraciÃ³n). Se genera/actualiza en ejecuciÃ³n.

- `start_server.ps1` / `start_server.bat`  
  Scripts de arranque en Windows (activaciÃ³n de venv y ejecuciÃ³n del servidor).

- `README.md`  
  GuÃ­a de instalaciÃ³n, ejecuciÃ³n y contexto del proyecto.

### 3.2 Directorios

- `templates/`  
  Plantillas HTML:
  - `templates/index.html`: dashboard (tabs, stream en vivo, indicador de hardware y panel PTZ condicional).
  - `templates/admin_camera.html`: interfaz de configuraciÃ³n de cÃ¡mara (rol admin).
  - `templates/login.html`: login.

- `static/`  
  Recursos estÃ¡ticos:
  - `static/style.css`: estilos.
  - `static/results/`: artefactos de resultados (imÃ¡genes/videos procesados).

- `uploads/`  
  Directorio temporal para archivos subidos para detecciÃ³n manual.

- `runs/`  
  Artefactos generados por Ultralytics (entrenamiento/detecciÃ³n), incluyendo pesos `best.pt` segÃºn configuraciÃ³n.

- `venv_new/`  
  Entorno virtual local (se regenera por instalaciÃ³n; no constituye artefacto de entrega â€œbinariaâ€).

- `dataset/`  
  Dataset asociado al entrenamiento/validaciÃ³n (si aplica a la entrega).

- `Documentacion/`  
  DocumentaciÃ³n tÃ©cnica y manuales:
  - `indice.md`
  - `api_rest.md`
  - `arquitectura_modulos.md`
  - `deployment_checklist.md`
  - `guia_sistema_web.md`
  - `referencia_rapida.md`

## 4) Artefactos de IA

- Pesos del modelo configurados en `config.py` (`YOLO_CONFIG["model_path"]`), tÃ­picamente `runs/detect/.../best.pt`.
- Pesos adicionales (p.ej. `yolo26s.pt`) pueden existir en el repositorio como referencia/alternativa experimental.

## 5) Limitaciones y observaciones (prototipo)

- El prototipo estÃ¡ orientado a demostraciÃ³n y validaciÃ³n. Para operaciÃ³n en producciÃ³n se recomienda hardening (TLS, reverse proxy, gestiÃ³n de secretos, auditorÃ­a, mÃ©tricas).
- El rendimiento depende de la disponibilidad real de CUDA y de la estabilidad RTSP.
- La capacidad PTZ depende del soporte ONVIF del fabricante y su correcta habilitaciÃ³n/configuraciÃ³n.


