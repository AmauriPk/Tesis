# Flujo del Administrador — SIRAN

## Rol

El administrador tiene acceso exclusivo al dashboard de administración (`/admin_dashboard`) y puede:
- Configurar la cámara (RTSP URL, credenciales, tipo PTZ/fija)
- Configurar el host ONVIF y sus credenciales
- Probar la conexión a la cámara
- Ajustar parámetros del modelo de detección en caliente
- Gestionar el dataset (clasificar, revisar, revertir imágenes)
- Revisar eventos de detección y métricas globales
- Exportar datos de detección en CSV

Al iniciar sesión como administrador, es redirigido automáticamente a `/admin_dashboard` en lugar del dashboard del operador.

---

## Flujo 1: Acceso al panel de administración

1. Inicia sesión con usuario `admin` y contraseña configurada (default `admin123`)
2. El sistema redirige automáticamente a `/admin_dashboard`
3. El dashboard muestra: configuración de cámara actual, parámetros del modelo, sección de dataset

---

## Flujo 2: Configuración de cámara RTSP

1. En el panel de administración, sección "Cámara"
2. Completar campos:
   - **URL RTSP:** `rtsp://<ip>:<puerto>/<stream>`
   - **Usuario RTSP:** usuario de autenticación de la cámara
   - **Contraseña RTSP:** contraseña de autenticación
   - **Tipo de cámara:** PTZ o Fija (configura el comportamiento inicial, sobrescrito por ONVIF autodiscovery)
3. Guardar → `POST /admin/camera`
4. El sistema persiste en SQLite y actualiza `config_camara.json`
5. Se relanza el proceso de autodiscovery ONVIF

*Nota: Las credenciales RTSP se almacenan en la base de datos SQLite local. No se deben subir al repositorio.*

---

## Flujo 3: Configuración ONVIF (control PTZ)

1. En la sección "ONVIF" del panel de administración
2. Completar campos:
   - **Host ONVIF:** IP de la cámara (generalmente la misma IP del stream RTSP)
   - **Puerto ONVIF:** normalmente 80 (no confundir con el puerto RTSP 554)
   - **Usuario ONVIF:** usuario de administración de la cámara
   - **Contraseña ONVIF:** contraseña de administración
3. Guardar configuración
4. Usar el botón "Probar conexión" → `POST /api/test_connection`
5. El sistema detecta si la cámara responde y si expone servicios PTZ
6. Si la cámara es PTZ, se habilitan los controles en el panel del operador

*Si el puerto ONVIF es 554, el sistema lo detecta y usa 80 por defecto (advertencia de seguridad integrada).*

---

## Flujo 4: Prueba de conexión ONVIF

1. Presionar "Probar conexión" en la configuración de cámara
2. `POST /api/test_connection` con los datos ingresados
3. El sistema intenta conectar al host ONVIF con timeout de 6 segundos
4. Si conecta exitosamente:
   - Devuelve `{status: "success", is_ptz: true/false}`
   - Muestra snapshot RTSP si se proporcionó URL
   - Actualiza el tipo de cámara en base de datos
5. Si falla: devuelve mensaje de error descriptivo (timeout, credenciales inválidas, host inalcanzable)

---

## Flujo 5: Ajuste de parámetros del modelo YOLO

1. En la sección "Parámetros del modelo" del panel de administración
2. Ajustar:
   - **Umbral de confianza** (confidence threshold): 0.10 – 1.00 (default 0.60)
   - **Umbral IoU** (intersección sobre unión): 0.10 – 1.00 (default 0.45)
   - **Persistencia de frames** (N frames consecutivos para confirmar detección): 1 – 10 (default 3)
3. Guardar → `POST /api/update_model_params`
4. Los cambios aplican en el próximo frame procesado, **sin reiniciar el servidor**

*El ajuste de confianza es crítico: valores demasiado bajos generan falsos positivos (aves, ruido), valores demasiado altos pueden perder detecciones reales.*

---

## Flujo 6: Gestión del dataset

### 6a. Ver imágenes recolectadas

1. En el panel de administración, sección "Dataset"
2. `GET /api/get_dataset_images` devuelve imágenes en `dataset_recoleccion/`
3. El administrador puede ver las imágenes capturadas durante análisis

### 6b. Clasificar imagen

1. Seleccionar una imagen del dataset
2. Clasificar como "positivo" (contiene dron) o "negativo" (falso positivo / no dron)
3. `POST /api/classify_image` con `{filename, label}`:
   - **positivo:** mueve a `dataset_entrenamiento/pending/images/`
   - **negativo:** mueve a `dataset_entrenamiento/train/images/`
4. El sistema confirma la clasificación con timestamp

### 6c. Revisar clasificaciones

1. `GET /api/get_classified_images` devuelve imágenes ya clasificadas
2. El administrador puede revisar las decisiones previas

### 6d. Revertir clasificación

1. Si una clasificación fue incorrecta: `POST /api/revert_classification`
2. La imagen regresa al inbox `dataset_recoleccion/limpias/`
3. Puede reclasificarse nuevamente

---

## Flujo 7: Revisión de eventos y métricas

1. El dashboard de administración muestra métricas de detección
2. `GET /api/detection_summary` devuelve resumen estadístico
3. `GET /api/recent_detection_events` devuelve últimos eventos agrupados con confianza y duración
4. Exportar eventos: `GET /api/export_detection_events.csv` descarga archivo CSV

---

## Flujo 8: Limpieza de datos de prueba

1. Durante desarrollo o pruebas puede haber datos espurios
2. `POST /api/admin/cleanup_test_data` permite limpiar registros de test
3. Requiere rol `admin`

---

## Flujo 9: Mantenimiento básico

### Reinicio del stream RTSP
Si la cámara cambia de IP o se desconecta, es necesario:
1. Actualizar la URL RTSP en el panel de configuración
2. El `RTSPLatestFrameReader` intenta reconectar automáticamente si pierde la señal

### Gestión del espacio en disco
- `static/results/`: contiene imágenes y videos de análisis. Limpiar periódicamente.
- `static/evidence/`: contiene evidencias visuales. Respaldar antes de limpiar.
- `uploads/`: archivos temporales de análisis. Se eliminan automáticamente post-procesamiento.
- `dataset_recoleccion/`: imágenes capturadas. Respaldar antes de reentrenamiento.

### Base de datos
- `detections.db`: puede crecer significativamente. Monitorear tamaño.
- Los eventos cerrados (`status='closed'`) son histórico permanente.
