# Refactor: Video Export Service

## Qué se movió

Las siguientes funciones fueron extraídas de `app.py` hacia `src/services/video_export_service.py`:

| Función | Descripción |
|---|---|
| `resolve_ffmpeg_bin()` | Localiza el ejecutable FFmpeg (env, PATH o imageio_ffmpeg) |
| `create_video_writer(...)` | Abre `cv2.VideoWriter` con fallback de codecs mp4v → XVID → MJPG |
| `transcode_to_browser_mp4(...)` | Transcodifica con FFmpeg (libx264, luego mpeg4) |
| `make_browser_compatible_mp4(...)` | Wrapper semántico sobre `transcode_to_browser_mp4` |
| `is_valid_video_file(...)` | Valida que el archivo exista y tenga tamaño > 0 |

## Imports eliminados de app.py

- `import subprocess` — ya no se usa en app.py
- `import imageio_ffmpeg` (bloque try/except) — ya no se usa en app.py

## Prueba manual

1. Ejecutar el servidor:
   ```
   py app.py
   ```

2. Iniciar sesión y navegar a la sección de análisis de video.

3. Subir un video de prueba (.mp4 o .avi).

4. Verificar en la carpeta de resultados que se genere `result_<JOB>_raw.mp4`.

5. Si FFmpeg está disponible en el sistema, verificar que también se genere `result_<JOB>_browser.mp4`.

6. Consultar el endpoint de progreso y confirmar que devuelve:
   ```json
   {
     "result_video_url": "...",
     "result_video_raw_url": "...",
     "result_video_mime": "video/mp4",
     "result_video_playable": true,
     "video_output_warning": null
   }
   ```
   Si FFmpeg no está instalado, `result_video_playable` debe ser `false` y `video_output_warning` debe tener un mensaje descriptivo.

## Endpoints no modificados

No se cambió ninguna ruta Flask. Los endpoints `/video_progress`, `/analyze_video`, `/video_feed` y todos los demás permanecen idénticos.

## Logs que se conservan

- `[VIDEO_WRITER]` — inicialización del escritor de video
- `[VIDEO_OUTPUT]` — validación del archivo de salida y modo playable
- `[VIDEO_TRANSCODE]` — resolución de FFmpeg y transcodificación
