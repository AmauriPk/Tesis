# detect.py
# Script para inferencia en tiempo real de detección de micro drones usando YOLO
# Carga modelo entrenado, captura video RTSP de cámara Hikvision, procesa frame by frame
# Dibuja bounding boxes, etiquetas y confianza
# Lógica de zona central para simular control PTZ
# Registra detecciones en SQLite si confianza > 0.60

import cv2
from ultralytics import YOLO
import sqlite3
from datetime import datetime
import os
from config import RTSP_CONFIG, YOLO_CONFIG, STORAGE_CONFIG

# Configuración de base de datos
DB_PATH = 'detections.db'

def init_db():
    """Inicializa la base de datos SQLite para registros de detecciones."""
    conn = sqlite3.connect(DB_PATH)
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
    """Guarda una detección en la base de datos si confianza > 0.60."""
    if confianza > YOLO_CONFIG['min_confidence_db']:
        now = datetime.now()
        fecha = now.strftime('%Y-%m-%d')
        hora = now.strftime('%H:%M:%S')
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO detections (fecha, hora, confianza, fuente, x1, y1, x2, y2, image_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (fecha, hora, float(confianza), fuente, int(x1), int(y1), int(x2), int(y2), image_path))
        conn.commit()
        conn.close()


def load_model(model_path=None):
    """Carga el modelo YOLO entrenado en GPU."""
    if model_path is None:
        model_path = YOLO_CONFIG['model_path']
    model = YOLO(model_path)
    model.to(YOLO_CONFIG['device'])
    return model


def process_frame(frame, model, tolerancia=0.2):
    """Procesa un frame para detección de drones y lógica de zona central."""
    height, width = frame.shape[:2]
    center_x = width // 2
    center_y = height // 2
    tol_x = int(width * tolerancia)
    tol_y = int(height * tolerancia)

    # Realizar inferencia
    results = model(frame, device=YOLO_CONFIG['device'], conf=YOLO_CONFIG['confidence'], verbose=YOLO_CONFIG['verbose'])

    # Procesar resultados
    for result in results:
        boxes = result.boxes
        for box in boxes:
            # Coordenadas del bounding box
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
            conf = float(box.conf[0].cpu().numpy())
            cls = int(box.cls[0].cpu().numpy())

            if cls == 0:  # Clase RPAS Micro
                # Dibujar bounding box
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                # Etiqueta con confianza
                label = f"RPAS Micro: {conf:.2f}"
                cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

                # Calcular centro del bbox
                bbox_center_x = (x1 + x2) // 2
                bbox_center_y = (y1 + y2) // 2

                # Lógica de zona central
                if bbox_center_x < center_x - tol_x:
                    print("Enviar comando PTZ: Mover a la izquierda")
                elif bbox_center_x > center_x + tol_x:
                    print("Enviar comando PTZ: Mover a la derecha")
                if bbox_center_y < center_y - tol_y:
                    print("Enviar comando PTZ: Mover arriba")
                elif bbox_center_y > center_y + tol_y:
                    print("Enviar comando PTZ: Mover abajo")

                # Guardar detección
                save_detection(conf, x1, y1, x2, y2)

    return frame


def main():
    # Inicializar DB
    init_db()

    # Cargar modelo
    model = load_model()

    # URL RTSP de la cámara Hikvision (ajusta usuario, password, IP, puerto)
    rtsp_url = RTSP_CONFIG['url']
    cap = cv2.VideoCapture(rtsp_url)

    if not cap.isOpened():
        print("Error: No se pudo abrir la captura RTSP.")
        return

    print("Iniciando detección en tiempo real. Presiona 'q' para salir.")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: No se pudo leer el frame.")
            break

        # Procesar frame
        processed_frame = process_frame(frame, model)

        # Mostrar frame
        cv2.imshow('Deteccion RPAS Micro', processed_frame)

        # Salir con 'q'
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

# Notas para integración con Flask:
# - Modularizar en funciones: load_model, process_frame, etc.
# - En Flask, usar un hilo separado para la captura y procesamiento
# - Exponer endpoints para iniciar/detener detección, obtener logs de DB
# - Para PTZ real, integrar con API de Hikvision en lugar de prints
