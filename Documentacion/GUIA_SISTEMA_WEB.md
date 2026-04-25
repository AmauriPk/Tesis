# guia_sistema_web.md â€“ Manual del sistema web (Operador)

## 1) Objetivo

Este manual describe la operaciÃ³n del dashboard web del prototipo **RPAS Micro**. El sistema integra detecciÃ³n de RPAS Micro por visiÃ³n artificial (YOLO26 en GPU), visualizaciÃ³n en vivo (RTSP â†’ multipart) y control PTZ condicionado por Auto-Discovery ONVIF.

La redacciÃ³n asume que el sistema ya estÃ¡ instalado y que la cÃ¡mara IP es accesible desde el servidor.

## 2) Acceso e inicio de sesiÃ³n

1. Abrir el navegador web.
2. Ingresar a la URL del sistema (por defecto): `http://localhost:5000`
3. Autenticarse con credenciales proporcionadas por el administrador.

**Roles relevantes:**

- **Operador (`operator`):** uso del dashboard.
- **Administrador (`admin`):** ademÃ¡s, acceso a configuraciÃ³n de cÃ¡mara.

## 3) Estructura del dashboard

El dashboard estÃ¡ organizado en dos pestaÃ±as:

- **Monitoreo en Vivo:** stream RTSP anotado con detecciones, panel de estado y (si procede) controles PTZ.
- **DetecciÃ³n Manual:** carga de archivo para inferencia asÃ­ncrona y visualizaciÃ³n de resultados.

## 4) Monitoreo en Vivo

### 4.1 Reproductor de video (stream multipart)

La vista en vivo muestra el stream procesado por el backend. Sobre el video se visualizan anotaciones (bounding boxes) cuando la inferencia detecta un objetivo.

### 4.2 Indicador de hardware (Auto-Discovery)

El sistema presenta un indicador de estado de hardware:

- **â€œCÃ¡mara Detectada: PTZâ€** (verde): el backend validÃ³ por ONVIF la disponibilidad de PTZ.
- **â€œCÃ¡mara Detectada: Fijaâ€** (gris): no se detectÃ³ PTZ o ONVIF fallÃ³. Se activa un mecanismo **fail-safe**.

**ImplicaciÃ³n operacional:**  
En modo â€œCÃ¡mara Fijaâ€, el sistema bloquea control mecÃ¡nico y oculta el panel PTZ automÃ¡ticamente.

### 4.3 Panel de alertas y estado

El panel lateral muestra:

- Estado actual (â€œZona despejadaâ€ o â€œAlerta: Dron detectadoâ€).
- Conteo de detecciones.
- Confianza promedio aproximada.
- Ãšltima actualizaciÃ³n.

## 5) Control PTZ (solo cuando aparece)

### 5.1 ApariciÃ³n del panel

El panel PTZ aparece Ãºnicamente cuando el indicador reporta **PTZ**. Esta lÃ³gica evita exponer controles no soportados y reduce el riesgo de uso incorrecto.

### 5.2 Uso del joystick/botones direccionales

- Mantener presionado un botÃ³n direccional para desplazar la cÃ¡mara.
- Usar **Stop** para detener el movimiento.

El backend ejecuta el control en hilos separados para evitar lag en la visualizaciÃ³n.

### 5.3 Tracking AutomÃ¡tico (solo PTZ)

Al activar el switch de **Tracking AutomÃ¡tico**:

- El sistema calcula la distancia del objetivo (centro del bounding box) respecto al centro del frame.
- Se envÃ­an correcciones PTZ asÃ­ncronas para recentrar el objetivo.

**Buenas prÃ¡cticas:**

- Activar tracking cuando exista un objetivo dominante y el movimiento sea estable.
- Desactivar tracking si se observa oscilaciÃ³n o si el objetivo no es consistente.

## 6) DetecciÃ³n Manual (carga de archivos)

### 6.1 Flujo bÃ¡sico

1. Seleccionar un archivo compatible:
   - Imagen: `.jpg`, `.jpeg`, `.png`
   - Video: `.mp4`, `.avi`, `.mov`
2. Iniciar el procesamiento.
3. Monitorear progreso hasta finalizar.
4. Revisar el resultado anotado y mÃ©tricas asociadas.

### 6.2 Observaciones

- La detecciÃ³n manual se ejecuta en background para mantener el servidor responsivo.
- Los resultados se almacenan en el Ã¡rea de resultados estÃ¡ticos para consulta posterior.

## 7) SoluciÃ³n rÃ¡pida de problemas (operador)

- **No hay video en vivo:** reportar al administrador para validar RTSP (URL, credenciales, red, puertos).
- **Se esperaba PTZ pero se muestra â€œFijaâ€:** reportar al administrador para validar ONVIF habilitado, credenciales y conectividad. El sistema adopta fail-safe ante cualquier falla ONVIF.
- **Rendimiento bajo:** reportar para validar GPU/CUDA y carga del sistema.


