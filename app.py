# app.py
# Servidor Flask para interfaz web de detección de drones RPAS Micro
# Backend: YOLO modelo en GPU (RTX 4060), streaming RTSP, procesamiento de archivos
# Frontend: HTML5 + Bootstrap, dos pestañas (Monitoreo en Vivo y Detección Manual)

import os
import cv2
import numpy as np
from flask import Flask, render_template, request, jsonify, Response, send_from_directory
from ultralytics import YOLO
from werkzeug.utils import secure_filename
import sqlite3
from datetime import datetime
import threading
import time
from collections import deque
from config import FLASK_CONFIG, RTSP_CONFIG, STORAGE_CONFIG, VIDEO_CONFIG, YOLO_CONFIG

try:
    import torch
except Exception:  # pragma: no cover
    torch = None

# ======================== CONFIGURACIÓN ========================
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = FLASK_CONFIG['max_content_length']  # Max upload 500MB
app.config['UPLOAD_FOLDER'] = STORAGE_CONFIG['upload_folder']
app.config['ALLOWED_EXTENSIONS'] = STORAGE_CONFIG['allowed_extensions']

# Crear directorio de uploads si no existe
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Variables globales para streaming
rtsp_url = RTSP_CONFIG['url']
detection_buffer = deque(maxlen=10)  # Últimas 10 detecciones para panel de alertas
camera_source_mode = "fixed"  # "fixed" | "ptz"
state_lock = threading.Lock()
stream_lock = threading.Lock()

latest_annotated_jpeg = None  # type: bytes | None
latest_annotated_ts = None  # type: float | None

_rtsp_reader = None
_live_processor = None
_live_threads_started = False
current_detection_state = {
    'status': 'Zona despejada',
    'avg_confidence': 0.0,
    'detected': False,
    'last_update': None,
    'detection_count': 0,
    'camera_source_mode': camera_source_mode,
}

# ======================== INICIALIZACIÓN YOLO ========================
def load_yolo_model():
    """Carga modelo YOLO en GPU (cuda:0) para RTX 4060."""
    try:
        if YOLO_CONFIG.get("device") != "cuda:0":
            raise RuntimeError("YOLO_CONFIG['device'] debe ser 'cuda:0' para ejecutar estrictamente en GPU.")
        if torch is None:
            raise RuntimeError("PyTorch no está disponible. Instala torch con soporte CUDA para ejecutar en GPU.")
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA no está disponible. Este prototipo requiere ejecución estricta en GPU (cuda:0).")

        print("[INFO] Cargando modelo YOLO en GPU...")
        model = YOLO(YOLO_CONFIG['model_path'])
        model.to(YOLO_CONFIG['device'])
        print("[SUCCESS] Modelo YOLO cargado en GPU correctamente.")
        return model
    except Exception as e:
        print(f"[ERROR] No se pudo cargar el modelo YOLO: {e}")
        return None

# Cargar modelo globalmente
yolo_model = load_yolo_model()

# ======================== BASE DE DATOS ========================
def init_db():
    """Inicializa tabla SQLite para historial de detecciones."""
    db_path = 'detections.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            hora TEXT,
            confianza REAL,
            fuente TEXT,
            x1 INTEGER,
            y1 INTEGER,
            x2 INTEGER,
            y2 INTEGER,
            image_path TEXT
        )
    ''')
    cursor.execute('PRAGMA table_info(detections)')
    columns = [row[1] for row in cursor.fetchall()]
    if 'fuente' not in columns:
        cursor.execute("ALTER TABLE detections ADD COLUMN fuente TEXT DEFAULT 'rtsp'")
    if 'image_path' not in columns:
        cursor.execute("ALTER TABLE detections ADD COLUMN image_path TEXT")
    conn.commit()
    conn.close()

def save_detection(confianza, x1, y1, x2, y2, fuente='rtsp', image_path=None):
    """Guarda detección en BD si confianza > 0.60."""
    if confianza > YOLO_CONFIG['min_confidence_db']:
        db_path = 'detections.db'
        now = datetime.now()
        fecha = now.strftime('%Y-%m-%d')
        hora = now.strftime('%H:%M:%S')
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO detections (fecha, hora, confianza, fuente, x1, y1, x2, y2, image_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (fecha, hora, float(confianza), fuente, int(x1), int(y1), int(x2), int(y2), image_path))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[ERROR] No se pudo guardar detección: {e}")

# ======================== PROCESAMIENTO DE FRAMES ========================
def draw_detections(frame, results):
    """Dibuja bounding boxes, etiquetas y confianza en el frame."""
    detection_list = []
    
    for result in results:
        if result.boxes is not None:
            boxes = result.boxes
            for box in boxes:
                try:
                    # Obtener coordenadas y confianza
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                    conf = float(box.conf[0].cpu().numpy())
                    cls = int(box.cls[0].cpu().numpy())
                    
                    # Dibujar rectángulo (color verde para RPAS Micro)
                    color = (0, 255, 0)  # Verde en BGR
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    
                    # Preparar etiqueta
                    label = f"RPAS Micro: {conf:.2%}"
                    
                    # Fondo para el texto
                    label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                    cv2.rectangle(frame, (x1, y1 - 25), (x1 + label_size[0], y1), color, -1)
                    
                    # Dibujar etiqueta
                    cv2.putText(frame, label, (x1, y1 - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
                    
                    # Guardar en lista de detecciones
                    detection_list.append({
                        'confidence': conf,
                        'bbox': (x1, y1, x2, y2)
                    })
                    
                    # Guardar frame si confianza > 0.60
                    image_path = None
                    if conf > YOLO_CONFIG['min_confidence_db']:
                        os.makedirs(STORAGE_CONFIG['detections_frames_folder'], exist_ok=True)
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                        image_filename = f"detection_{timestamp}_{conf:.2f}.jpg"
                        image_path = os.path.join(STORAGE_CONFIG['detections_frames_folder'], image_filename)
                        cv2.imwrite(image_path, frame)
                    
                    # Guardar en BD
                    save_detection(conf, x1, y1, x2, y2, 'rtsp', image_path)
                    
                except Exception as e:
                    print(f"[ERROR] Al procesar detección: {e}")
    
    return frame, detection_list

def enviar_comando_ptz(direction: str, speed: float = 0.5):
    """
    Simulación de envío de comando PTZ.
    En integración real, aquí iría ONVIF / SDK del fabricante / HTTP API.
    """
    print(f"[PTZ] Comando simulado: direction={direction} speed={speed}")


def _bbox_off_center(frame_w: int, frame_h: int, bbox_xyxy):
    x1, y1, x2, y2 = bbox_xyxy
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0

    # Zona central tolerada (rectángulo). Fuera de ella => pedir movimiento PTZ.
    tol_w = 0.20 * frame_w
    tol_h = 0.20 * frame_h
    center_x = frame_w / 2.0
    center_y = frame_h / 2.0

    dx = cx - center_x
    dy = cy - center_y

    if abs(dx) <= tol_w and abs(dy) <= tol_h:
        return None

    if abs(dx) >= abs(dy):
        return "left" if dx < 0 else "right"
    return "up" if dy < 0 else "down"


class _RTSPLatestFrameReader:
    """
    Lee RTSP en un hilo dedicado y conserva sólo el último frame.
    Esto "dropea" frames automáticamente si hay lag para mantener tiempo real.
    """

    def __init__(self, url: str):
        self.url = url
        self._lock = threading.Lock()
        self._frame = None
        self._ts = None
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def get_latest(self):
        with self._lock:
            return self._frame, self._ts

    def _run(self):
        cap = None
        try:
            while not self._stop.is_set():
                if cap is None or not cap.isOpened():
                    print(f"[INFO] Conectando a RTSP: {self.url}")
                    cap = cv2.VideoCapture(self.url)
                    if cap.isOpened():
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH, VIDEO_CONFIG['width'])
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, VIDEO_CONFIG['height'])
                        cap.set(cv2.CAP_PROP_FPS, VIDEO_CONFIG['fps'])
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, RTSP_CONFIG.get("buffer_size", 1))
                    else:
                        print("[WARNING] No se pudo abrir RTSP. Reintentando...")
                        time.sleep(1.0)
                        continue

                ret, frame = cap.read()
                if not ret or frame is None:
                    print("[WARNING] Lectura RTSP fallida. Reintentando conexión...")
                    try:
                        cap.release()
                    except Exception:
                        pass
                    cap = None
                    time.sleep(0.5)
                    continue

                ts = time.time()
                with self._lock:
                    self._frame = frame
                    self._ts = ts
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass


class _LiveVideoProcessor:
    """Procesa el último frame RTSP, ejecuta YOLO en GPU y conserva el último JPEG anotado."""

    def __init__(self, reader: _RTSPLatestFrameReader):
        self.reader = reader
        self._stop = threading.Event()
        self._thread = None
        self._last_ts = None
        self._frame_count = 0
        self._detection_times = deque(maxlen=30)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self):
        global latest_annotated_jpeg, latest_annotated_ts

        while not self._stop.is_set():
            frame, ts = self.reader.get_latest()
            if frame is None or ts is None:
                time.sleep(0.02)
                continue
            if ts == self._last_ts:
                time.sleep(0.005)
                continue
            self._last_ts = ts

            try:
                frame = cv2.resize(frame, (VIDEO_CONFIG['width'], VIDEO_CONFIG['height']))
            except Exception:
                pass

            self._frame_count += 1

            detection_list = []
            if yolo_model is not None and (self._frame_count % max(1, VIDEO_CONFIG.get("inference_interval", 1)) == 0):
                try:
                    t0 = time.time()
                    results = yolo_model(
                        frame,
                        device=YOLO_CONFIG['device'],
                        conf=YOLO_CONFIG['confidence'],
                        verbose=YOLO_CONFIG['verbose'],
                    )
                    self._detection_times.append(time.time() - t0)
                    frame, detection_list = draw_detections(frame, results)
                except Exception as e:
                    print(f"[ERROR] En inferencia YOLO: {e}")
                    cv2.putText(frame, "Error en inferencia", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            # Regla de adaptabilidad: PTZ si el bbox no está centrado.
            with state_lock:
                mode = camera_source_mode
            if mode == "ptz" and detection_list:
                best = max(detection_list, key=lambda d: d["confidence"])
                h, w = frame.shape[:2]
                direction = _bbox_off_center(w, h, best["bbox"])
                if direction:
                    enviar_comando_ptz(direction=direction, speed=0.6)

            with state_lock:
                current_detection_state["camera_source_mode"] = camera_source_mode
                current_detection_state["last_update"] = datetime.now().isoformat()
                if detection_list:
                    avg_conf = float(np.mean([d["confidence"] for d in detection_list]))
                    current_detection_state["status"] = "Alerta: Dron detectado"
                    current_detection_state["avg_confidence"] = avg_conf
                    current_detection_state["detected"] = True
                    current_detection_state["detection_count"] = len(detection_list)
                else:
                    current_detection_state["status"] = "Zona despejada"
                    current_detection_state["avg_confidence"] = 0.0
                    current_detection_state["detected"] = False
                    current_detection_state["detection_count"] = 0

            if self._detection_times:
                avg_inf_time = float(np.mean(list(self._detection_times)))
                fps = 1.0 / avg_inf_time if avg_inf_time > 0 else 0.0
                cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, VIDEO_CONFIG['jpeg_quality']])
            if not ok:
                time.sleep(0.01)
                continue

            with stream_lock:
                latest_annotated_jpeg = buffer.tobytes()
                latest_annotated_ts = ts


def _ensure_live_threads_started():
    global _rtsp_reader, _live_processor, _live_threads_started
    if _live_threads_started:
        return
    _rtsp_reader = _RTSPLatestFrameReader(rtsp_url)
    _live_processor = _LiveVideoProcessor(_rtsp_reader)
    _rtsp_reader.start()
    _live_processor.start()
    _live_threads_started = True


def process_rtsp_stream():
    """Generador multipart/x-mixed-replace: entrega el último frame anotado (tiempo real con drop de frames)."""
    _ensure_live_threads_started()

    placeholder = np.zeros((VIDEO_CONFIG['height'], VIDEO_CONFIG['width'], 3), dtype=np.uint8)
    cv2.putText(placeholder, "Conectando a RTSP...", (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
    _, ph_buf = cv2.imencode(".jpg", placeholder, [cv2.IMWRITE_JPEG_QUALITY, 80])
    ph_bytes = ph_buf.tobytes()

    last_sent_ts = None
    while True:
        with stream_lock:
            jpeg = latest_annotated_jpeg
            ts = latest_annotated_ts

        if jpeg is None or ts is None:
            frame_bytes = ph_bytes
            time.sleep(0.05)
        else:
            if ts == last_sent_ts:
                time.sleep(0.01)
                continue
            last_sent_ts = ts
            frame_bytes = jpeg

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Content-Length: "
            + str(len(frame_bytes)).encode()
            + b"\r\n\r\n"
            + frame_bytes
            + b"\r\n"
        )

def allowed_file(filename):
    """Verifica que el archivo tenga extensión permitida."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# ======================== RUTAS FLASK ========================

@app.route('/')
def index():
    """Ruta principal - carga la interfaz HTML."""
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    """Ruta para streaming de video RTSP con detecciones en tiempo real."""
    source = (request.args.get("source") or "").strip().lower()
    if source in {"fixed", "ptz"}:
        global camera_source_mode
        with state_lock:
            camera_source_mode = source
            current_detection_state["camera_source_mode"] = camera_source_mode
    return Response(
        process_rtsp_stream(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

@app.route('/set_camera_source', methods=['POST'])
def set_camera_source():
    """Endpoint para cambiar el origen/mode de cámara (Fija vs PTZ) desde la UI."""
    payload = request.get_json(silent=True) or request.form or {}
    source = str(payload.get("source", "")).strip().lower()
    if source not in {"fixed", "ptz"}:
        return jsonify({"success": False, "error": "Modo inválido. Usa 'fixed' o 'ptz'."}), 400

    global camera_source_mode
    with state_lock:
        camera_source_mode = source
        current_detection_state["camera_source_mode"] = camera_source_mode

    return jsonify({"success": True, "camera_source_mode": camera_source_mode})

@app.route('/detection_status')
def detection_status():
    """Endpoint AJAX para obtener estado actual de detecciones."""
    with state_lock:
        return jsonify(dict(current_detection_state))

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """Sirve archivos procesados guardados en la carpeta uploads."""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/upload_detect', methods=['POST'])
def upload_detect():
    """
    Ruta para procesar archivos subidos (imagen o video).
    - Recibe archivo, aplica YOLO, devuelve resultado procesado.
    """
    try:
        # Validar que se subió un archivo
        if 'file' not in request.files:
            return jsonify({'error': 'No se subió archivo'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'Archivo sin nombre'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Extensión no permitida'}), 400
        
        # Guardar archivo temporalmente
        filename = secure_filename(file.filename)
        timestamp = str(int(time.time()))
        filename = f"{timestamp}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Determinar si es imagen o video
        file_ext = filename.rsplit('.', 1)[1].lower()
        
        if file_ext in {'jpg', 'jpeg', 'png'}:
            # Procesar imagen
            return process_image_detection(filepath)
        elif file_ext in {'mp4', 'avi', 'mov'}:
            # Procesar video
            return process_video_detection(filepath)
        else:
            os.remove(filepath)
            return jsonify({'error': 'Tipo de archivo no soportado'}), 400
    
    except Exception as e:
        print(f"[ERROR] En upload_detect: {e}")
        return jsonify({'error': str(e)}), 500

def process_image_detection(filepath):
    """Procesa una imagen: YOLO → dibuja detecciones → devuelve imagen procesada."""
    try:
        # Leer imagen
        image = cv2.imread(filepath)
        if image is None:
            return jsonify({'error': 'No se pudo leer la imagen'}), 400
        
        original_height, original_width = image.shape[:2]
        
        # Redimensionar para inferencia (max 1280x720)
        if original_width > 1280 or original_height > 720:
            scale = min(1280 / original_width, 720 / original_height)
            new_width = int(original_width * scale)
            new_height = int(original_height * scale)
            image = cv2.resize(image, (new_width, new_height))
        
        # Inferencia YOLO
        if yolo_model is None:
            return jsonify({'error': 'Modelo YOLO no disponible'}), 500
        
        results = yolo_model(
            image,
            device=YOLO_CONFIG['device'],
            conf=YOLO_CONFIG['confidence'],
            verbose=YOLO_CONFIG['verbose'],
        )
        
        # Procesar detecciones
        image, detection_list = draw_detections(image, results)
        
        # Codificar imagen procesada a base64
        ret, buffer = cv2.imencode('.jpg', image)
        img_base64 = buffer.tobytes()
        import base64
        img_b64_str = base64.b64encode(img_base64).decode()
        
        # Limpiar archivo temporal
        os.remove(filepath)
        
        return jsonify({
            'success': True,
            'image': f'data:image/jpeg;base64,{img_b64_str}',
            'detections_count': len(detection_list),
            'avg_confidence': np.mean([d['confidence'] for d in detection_list]) if detection_list else 0.0
        })
    
    except Exception as e:
        print(f"[ERROR] En process_image_detection: {e}")
        if os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({'error': str(e)}), 500

def process_video_detection(filepath):
    """Procesa un video: YOLO en cada frame → crea video procesado → devuelve URL de descarga."""
    try:
        # Abrir video
        cap = cv2.VideoCapture(filepath)
        if not cap.isOpened():
            return jsonify({'error': 'No se pudo leer el video'}), 400
        
        # Obtener propiedades
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if not fps or fps <= 0:
            fps = VIDEO_CONFIG['fps']
        
        # Redimensionar si es muy grande
        if width > 1280 or height > 720:
            scale = min(1280 / width, 720 / height)
            width = int(width * scale)
            height = int(height * scale)
        
        # Crear writer para video procesado
        output_filename = f"processed_{int(time.time())}.mp4"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        
        frame_count = 0
        total_detections = 0
        total_confidence = 0.0
        
        if yolo_model is None:
            return jsonify({'error': 'Modelo YOLO no disponible'}), 500
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # Redimensionar
            if frame.shape[1] != width or frame.shape[0] != height:
                frame = cv2.resize(frame, (width, height))
            
            # Inferencia
            results = yolo_model(
                frame,
                device=YOLO_CONFIG['device'],
                conf=YOLO_CONFIG['confidence'],
                verbose=YOLO_CONFIG['verbose'],
            )
            
            # Procesar detecciones
            frame, detection_list = draw_detections(frame, results)
            
            # Acumular estadísticas
            total_detections += len(detection_list)
            if detection_list:
                total_confidence += np.mean([d['confidence'] for d in detection_list])
            
            # Escribir frame procesado
            out.write(frame)
            frame_count += 1
        
        cap.release()
        out.release()
        
        avg_conf = (total_confidence / max(1, frame_count))
        
        # Limpiar original
        os.remove(filepath)
        
        return jsonify({
            'success': True,
            'video_url': f'/uploads/{output_filename}',
            'frames_processed': frame_count,
            'total_detections': total_detections,
            'avg_confidence': avg_conf
        })
    
    except Exception as e:
        print(f"[ERROR] En process_video_detection: {e}")
        if os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({'error': str(e)}), 500

@app.route('/history')
def history():
    """Endpoint para obtener historial de detecciones."""
    try:
        db_path = 'detections.db'
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM detections ORDER BY id DESC LIMIT 100')
        rows = cursor.fetchall()
        conn.close()
        
        detections = [dict(row) for row in rows]
        return jsonify(detections)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Inicializar BD tambien cuando el modulo se importe con flask run/uWSGI.
init_db()

# ======================== INICIALIZACIÓN ========================
if __name__ == '__main__':
    # Mensajes informativos
    print("\n" + "="*60)
    print("🚁 SERVIDOR DE DETECCIÓN DE DRONES RPAS MICRO")
    print("="*60)
    print(f"[INFO] Modelo YOLO: {'CARGADO EN GPU' if yolo_model else 'NO DISPONIBLE'}")
    print(f"[INFO] URL RTSP: {rtsp_url}")
    print(f"[INFO] Servidor Flask iniciado en: http://localhost:5000")
    print("[INFO] Interfaz disponible en: http://localhost:5000/")
    print("="*60 + "\n")
    
    # Iniciar servidor Flask
    app.run(
        debug=FLASK_CONFIG['debug'],
        host=FLASK_CONFIG['host'],
        port=FLASK_CONFIG['port'],
        threaded=FLASK_CONFIG['threaded'],
    )
