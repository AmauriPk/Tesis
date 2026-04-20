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
current_detection_state = {
    'status': 'Zona despejada',
    'avg_confidence': 0.0,
    'detected': False,
    'last_update': None,
    'detection_count': 0
}

# ======================== INICIALIZACIÓN YOLO ========================
def load_yolo_model():
    """Carga modelo YOLO en GPU (cuda:0) para RTX 4060."""
    try:
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

def process_rtsp_stream():
    """Generador para transmitir video RTSP con detecciones en tiempo real (multipart/x-mixed-replace)."""
    cap = None
    frame_count = 0
    detection_times = deque(maxlen=30)  # Últimos 30 frames
    
    try:
        print(f"[INFO] Conectando a RTSP: {rtsp_url}")
        cap = cv2.VideoCapture(rtsp_url)
        
        if not cap.isOpened():
            print("[WARNING] No se pudo conectar a RTSP. Usando webcam por defecto (índice 0)")
            cap = cv2.VideoCapture(0)
        
        # Configurar propiedades de captura
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        while True:
            ret, frame = cap.read()
            
            if not ret:
                print("[WARNING] No se pudo leer frame. Reiniciando conexión...")
                cap.release()
                time.sleep(2)
                cap = cv2.VideoCapture(rtsp_url)
                continue
            
            # Redimensionar para optimizar (inferencia más rápida)
            frame = cv2.resize(frame, (1280, 720))
            frame_count += 1
            
            # Realizar inferencia YOLO
            if yolo_model is not None:
                try:
                    t0 = time.time()
                    results = yolo_model(
                        frame,
                        device=YOLO_CONFIG['device'],
                        conf=YOLO_CONFIG['confidence'],
                        verbose=YOLO_CONFIG['verbose'],
                    )
                    inference_time = time.time() - t0
                    detection_times.append(inference_time)
                    
                    # Procesar detecciones
                    frame, detection_list = draw_detections(frame, results)
                    
                    # Actualizar estado global de detecciones
                    if detection_list:
                        avg_conf = np.mean([d['confidence'] for d in detection_list])
                        current_detection_state['status'] = '🚨 ALERTA: Dron detectado'
                        current_detection_state['avg_confidence'] = avg_conf
                        current_detection_state['detected'] = True
                        current_detection_state['detection_count'] = len(detection_list)
                    else:
                        current_detection_state['status'] = '✓ Zona despejada'
                        current_detection_state['avg_confidence'] = 0.0
                        current_detection_state['detected'] = False
                        current_detection_state['detection_count'] = 0
                    
                    current_detection_state['last_update'] = datetime.now().isoformat()
                    
                    # Mostrar FPS en el frame
                    if detection_times:
                        avg_inf_time = np.mean(list(detection_times))
                        fps = 1.0 / avg_inf_time if avg_inf_time > 0 else 0
                        cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    
                except Exception as e:
                    print(f"[ERROR] En inferencia YOLO: {e}")
                    cv2.putText(frame, "Error en inferencia", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            # Codificar frame a JPEG
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, VIDEO_CONFIG['jpeg_quality']])
            frame_bytes = buffer.tobytes()
            
            # Formato multipart/x-mixed-replace para streaming
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n'
                   b'Content-Length: ' + str(len(frame_bytes)).encode() + b'\r\n\r\n' +
                   frame_bytes + b'\r\n')
            
            # Limitar a 30 FPS para no sobrecargar
            time.sleep(0.033)
    
    except Exception as e:
        print(f"[ERROR] En stream RTSP: {e}")
    
    finally:
        if cap is not None:
            cap.release()

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
    return Response(
        process_rtsp_stream(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

@app.route('/detection_status')
def detection_status():
    """Endpoint AJAX para obtener estado actual de detecciones."""
    return jsonify(current_detection_state)

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
