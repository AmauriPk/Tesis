# Video procesado en navegador (FFmpeg)

El video procesado/anotado que se genera con OpenCV puede quedar codificado con formatos que **Windows reproduce**, pero que **Chrome/Edge no siempre reproducen correctamente** en un elemento HTML5 `<video>`.

Para asegurar compatibilidad en el navegador, el sistema intenta convertir el video “raw” a un MP4 estándar:

- H.264 (`libx264`) + `yuv420p` + `+faststart` (recomendado)
- Fallback: `mpeg4` si `libx264` no está disponible

## Instalación en Windows (winget)

```bat
winget install Gyan.FFmpeg
```

## Alternativa automática (imageio-ffmpeg)

Si no quieres instalar FFmpeg globalmente (PATH), el proyecto incluye `imageio-ffmpeg` como fallback.
Esta librería puede descargar/proveer un `ffmpeg` embebido y el backend lo intentará usar automáticamente.

Instalar en tu entorno virtual:

```bat
pip install imageio-ffmpeg
```

Probar qué ruta resolvió:

```bat
py -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"
```

Usar esa ruta explícitamente con `FFMPEG_BIN` (PowerShell):

```powershell
$env:FFMPEG_BIN = (py -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())")
py app.py
```

## Verificar instalación

```bat
ffmpeg -version
```

Si el comando no existe, FFmpeg no está en `PATH`.

## Configurar ruta manual (`FFMPEG_BIN`)

Si FFmpeg está instalado pero no está en `PATH`, puedes configurar la ruta completa al ejecutable:

1. Edita tu `.env` (o variables de entorno) y agrega:

```env
FFMPEG_BIN=C:\ffmpeg\bin\ffmpeg.exe
```

2. Reinicia la aplicación Flask.

## Qué hace el sistema

- Genera un video intermedio: `static/results/result_<JOB>_raw.mp4`
- Intenta generar el final para navegador: `static/results/result_<JOB>_browser.mp4`
- Si no hay FFmpeg o la conversión falla:
  - El sistema mantiene el video “raw” como descarga
  - La interfaz muestra una advertencia y deja disponible el botón **Descargar**
