# Lista de Capturas Necesarias — SIRAN

## CAP-01: Pantalla de Login

| Campo | Detalle |
|---|---|
| **Nombre sugerido** | `cap_01_login.png` |
| **Dónde tomarla** | Navegar a `http://localhost:5000/login` sin autenticación |
| **Capítulo** | Cap. 3 (interfaz), Cap. 4 (resultados - validación de autenticación) |
| **Qué debe mostrar** | Formulario de login con logo o nombre del sistema visible |
| **Qué ocultar** | No dejar credenciales reales escritas; formulario vacío o con usuario de prueba |

---

## CAP-02: Dashboard del operador (vacío / sin stream)

| Campo | Detalle |
|---|---|
| **Nombre sugerido** | `cap_02_dashboard_operador.png` |
| **Dónde tomarla** | Iniciar sesión como operador, pestaña "En Vivo" |
| **Capítulo** | Cap. 3 (módulo de interfaz), Cap. 4 (resultados) |
| **Qué debe mostrar** | Layout completo: menú, pestañas, área de stream, panel de alertas |

---

## CAP-03: Cámara en vivo con stream activo

| Campo | Detalle |
|---|---|
| **Nombre sugerido** | `cap_03_stream_en_vivo.png` |
| **Dónde tomarla** | Con cámara conectada y stream RTSP activo |
| **Capítulo** | Cap. 3 (descripción del stream), Cap. 4 (resultados del stream en tiempo real) |
| **Qué debe mostrar** | Frame de video en vivo visible en el dashboard |

---

## CAP-04: Detección activa del dron en vivo

| Campo | Detalle |
|---|---|
| **Nombre sugerido** | `cap_04_deteccion_dron_vivo.png` |
| **Dónde tomarla** | Con dron en campo de visión de la cámara |
| **Capítulo** | Cap. 4 (resultado principal de detección) |
| **Qué debe mostrar** | Frame del stream con bounding box sobre el dron, etiqueta de clase y confianza |
| **Qué ocultar** | No mostrar IP de la cámara si aparece en pantalla |

---

## CAP-05: Tracking automático activo

| Campo | Detalle |
|---|---|
| **Nombre sugerido** | `cap_05_tracking_automatico.png` |
| **Dónde tomarla** | Con tracking activo y dron detectado |
| **Capítulo** | Cap. 4 (resultados de tracking) |
| **Qué debe mostrar** | Badge "Tracking activo", bounding box centrado en el frame |

---

## CAP-06: Inspección automática

| Campo | Detalle |
|---|---|
| **Nombre sugerido** | `cap_06_inspeccion_activa.png` |
| **Dónde tomarla** | Con modo inspección habilitado |
| **Capítulo** | Cap. 4 (resultados de inspección) |
| **Qué debe mostrar** | Badge "Inspección activa", indicador visual de modo de operación |

---

## CAP-07: Panel de alertas recientes con evidencias

| Campo | Detalle |
|---|---|
| **Nombre sugerido** | `cap_07_alertas_recientes.png` |
| **Dónde tomarla** | Dashboard del operador, panel de alertas después de varias detecciones |
| **Capítulo** | Cap. 4 (resultados de evidencias y eventos) |
| **Qué debe mostrar** | Lista de alertas con thumbnails de evidencia, timestamps y nivel de confianza |

---

## CAP-08: Evidencia visual generada

| Campo | Detalle |
|---|---|
| **Nombre sugerido** | `cap_08_evidencia_visual.png` |
| **Dónde tomarla** | Carpeta `static/evidence/` o panel de alertas |
| **Capítulo** | Cap. 4 (evidencias) |
| **Qué debe mostrar** | Imagen JPG con el dron claramente visible, bounding box si aplica, timestamp legible |

---

## CAP-09: Análisis manual de imagen — resultado

| Campo | Detalle |
|---|---|
| **Nombre sugerido** | `cap_09_analisis_imagen.png` |
| **Dónde tomarla** | Pestaña "Análisis Manual", después de analizar una imagen con dron |
| **Capítulo** | Cap. 4 (resultados de análisis de imagen) |
| **Qué debe mostrar** | Imagen analizada con bounding box visible, conteo de detecciones y confianza |

---

## CAP-10: Análisis manual de video — reproductor

| Campo | Detalle |
|---|---|
| **Nombre sugerido** | `cap_10_analisis_video.png` |
| **Dónde tomarla** | Pestaña "Análisis Manual", video procesado reproducido en el navegador |
| **Capítulo** | Cap. 4 (resultados de análisis de video) |
| **Qué debe mostrar** | Video con bounding boxes visibles, controles de reproducción del navegador |

---

## CAP-11: Métricas / eventos de detección

| Campo | Detalle |
|---|---|
| **Nombre sugerido** | `cap_11_eventos_deteccion.png` |
| **Dónde tomarla** | Sección de eventos del dashboard o respuesta JSON de `/api/recent_detection_events` |
| **Capítulo** | Cap. 4 (resultados de registro de eventos) |
| **Qué debe mostrar** | Lista de eventos con started_at, ended_at, max_confidence, detection_count |

---

## CAP-12: Gestor de dataset (administrador)

| Campo | Detalle |
|---|---|
| **Nombre sugerido** | `cap_12_gestor_dataset.png` |
| **Dónde tomarla** | Dashboard de administrador, sección "Dataset" |
| **Capítulo** | Cap. 3 (módulo de dataset), Cap. 4 (resultados del dataset) |
| **Qué debe mostrar** | Galería de imágenes disponibles para clasificar |

---

## CAP-13: Panel de configuración de cámara (sin credenciales)

| Campo | Detalle |
|---|---|
| **Nombre sugerido** | `cap_13_config_camara.png` |
| **Dónde tomarla** | `/admin_dashboard`, sección de configuración de cámara |
| **Capítulo** | Cap. 3 (configuración del sistema) |
| **Qué debe mostrar** | Formulario de configuración RTSP/ONVIF con campos visibles |
| **Qué ocultar** | Contraseñas (mostrar asteriscos o campo vacío), IP real de la cámara |

---

## CAP-14: Consola mostrando YOLO en CUDA

| Campo | Detalle |
|---|---|
| **Nombre sugerido** | `cap_14_yolo_cuda.png` |
| **Dónde tomarla** | Terminal donde se ejecuta `py app.py` |
| **Capítulo** | Cap. 3 (herramientas) / Cap. 4 (rendimiento) |
| **Qué debe mostrar** | Línea `[SUCCESS] Modelo YOLO cargado en device=cuda:0` |

---

## CAP-15: Consola mostrando procesamiento de video

| Campo | Detalle |
|---|---|
| **Nombre sugerido** | `cap_15_procesamiento_video_consola.png` |
| **Dónde tomarla** | Terminal durante análisis de video |
| **Capítulo** | Cap. 4 (resultados de análisis de video) |
| **Qué debe mostrar** | Logs `[VIDEO_WRITER]`, `[VIDEO_TRANSCODE]`, `[VIDEO_OUTPUT]` con valores reales |

---

## CAP-16: Exportación de CSV de eventos

| Campo | Detalle |
|---|---|
| **Nombre sugerido** | `cap_16_export_csv.png` |
| **Dónde tomarla** | Abrir `GET /api/export_detection_events.csv` en el navegador o mostrar el archivo descargado |
| **Capítulo** | Cap. 4 (resultados de exportación) |
| **Qué debe mostrar** | Contenido del CSV con columnas correctas y al menos 3 eventos reales |

---

## CAP-17: Estructura de carpetas del proyecto

| Campo | Detalle |
|---|---|
| **Nombre sugerido** | `cap_17_estructura_proyecto.png` |
| **Dónde tomarla** | Explorador de archivos o terminal con `tree` |
| **Capítulo** | Cap. 3 (arquitectura) |
| **Qué debe mostrar** | Árbol de directorios del proyecto (sin mostrar venv_new ni uploads) |
| **Qué ocultar** | Carpetas con credenciales, `venv_new`, contenido de `uploads` |

---

## CAP-18: GitHub actualizado

| Campo | Detalle |
|---|---|
| **Nombre sugerido** | `cap_18_github_repo.png` |
| **Dónde tomarla** | Página principal del repositorio en GitHub |
| **Capítulo** | Cap. 3 (herramientas / control de versiones) |
| **Qué debe mostrar** | README, lista de archivos del repositorio, historial de commits reciente |
| **Qué ocultar** | No mostrar email personal, tokens o información sensible del perfil |

---

## CAP-19: Requisitos (requirements.txt)

| Campo | Detalle |
|---|---|
| **Nombre sugerido** | `cap_19_requirements.png` |
| **Dónde tomarla** | Editor de código mostrando `requirements.txt` |
| **Capítulo** | Cap. 3 (tecnologías y dependencias) |
| **Qué debe mostrar** | Lista completa de dependencias con versiones |

---

## CAP-20: Configuración RTSP/ONVIF sin credenciales visibles

| Campo | Detalle |
|---|---|
| **Nombre sugerido** | `cap_20_config_rtsp_onvif.png` |
| **Dónde tomarla** | Panel de administración, formulario de configuración |
| **Capítulo** | Cap. 3 (configuración de hardware) |
| **Qué debe mostrar** | Campos de URL RTSP, host ONVIF y puerto visibles; contraseñas ocultas |
| **Qué ocultar** | IPs reales, contraseñas, cualquier credencial visible |
