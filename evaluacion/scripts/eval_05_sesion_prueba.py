#!/usr/bin/env python3
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, OSError):
    pass
"""
eval_05_sesion_prueba.py — Registrar sesión experimental (Sección 4.3)
------------------------------------------------------------------------
Script INTERACTIVO. Ejecutar ANTES de cada vuelo de prueba.
Registra parámetros de la sesión en detections.db y exporta
las detecciones capturadas durante la sesión.
NO toca el código de la aplicación SIRAN.

Crea tabla experiment_sessions en detections.db si no existe:
  - id                    INTEGER PRIMARY KEY AUTOINCREMENT
  - session_id            TEXT UNIQUE
  - timestamp_inicio      TEXT
  - timestamp_fin         TEXT
  - distancia_m           INTEGER
  - iluminacion           TEXT
  - duracion_estimada_min INTEGER
  - notas                 TEXT

Uso:
    python eval_05_sesion_prueba.py

Salida:
    evaluacion/resultados/sesion_{session_id}.csv
"""

import csv
import sqlite3
from datetime import datetime
from pathlib import Path

# -- Rutas ----------------------------------------------------------------------
SCRIPT_DIR   = Path(__file__).parent
EVAL_DIR     = SCRIPT_DIR.parent
PROJECT_ROOT = EVAL_DIR.parent
RESULTADOS_DIR = EVAL_DIR / "resultados"
DB_PATH = PROJECT_ROOT / "detections.db"

# -- Opciones válidas -----------------------------------------------------------
DISTANCIAS_VALIDAS   = [10, 25, 50, 75, 100]
ILUMINACIONES_VALIDAS = ["diurno_optimo", "contraluz", "sombra"]

# -- Funciones de entrada -------------------------------------------------------

def pedir_opcion(prompt: str, opciones: list) -> str:
    """Pide al usuario que elija una de las opciones. No retorna hasta que elija."""
    opts_str = " / ".join(str(o) for o in opciones)
    while True:
        valor = input(f"{prompt} [{opts_str}]: ").strip()
        # Aceptar texto o número de posición
        if valor in [str(o) for o in opciones]:
            return valor
        try:
            idx = int(valor) - 1
            if 0 <= idx < len(opciones):
                return str(opciones[idx])
        except ValueError:
            pass
        print(f"  Opción no válida. Elige entre: {opts_str}")


def pedir_entero(prompt: str, minimo: int = 1, maximo: int = 9999) -> int:
    while True:
        valor = input(f"{prompt}: ").strip()
        try:
            n = int(valor)
            if minimo <= n <= maximo:
                return n
        except ValueError:
            pass
        print(f"  Ingresa un número entero entre {minimo} y {maximo}.")


# -- Funciones de base de datos -------------------------------------------------

def crear_tabla_sessions(conn: sqlite3.Connection):
    """Crea la tabla experiment_sessions si no existe."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS experiment_sessions (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id            TEXT    UNIQUE NOT NULL,
            timestamp_inicio      TEXT    NOT NULL,
            timestamp_fin         TEXT,
            distancia_m           INTEGER NOT NULL,
            iluminacion           TEXT    NOT NULL,
            duracion_estimada_min INTEGER,
            notas                 TEXT
        )
    """)
    conn.commit()


def insertar_session(conn: sqlite3.Connection, datos: dict) -> int:
    cur = conn.execute("""
        INSERT INTO experiment_sessions
            (session_id, timestamp_inicio, distancia_m, iluminacion,
             duracion_estimada_min, notas)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        datos["session_id"],
        datos["timestamp_inicio"],
        datos["distancia_m"],
        datos["iluminacion"],
        datos["duracion_estimada_min"],
        datos["notas"],
    ))
    conn.commit()
    return cur.lastrowid


def registrar_fin(conn: sqlite3.Connection, session_id: str, ts_fin: str):
    conn.execute(
        "UPDATE experiment_sessions SET timestamp_fin = ? WHERE session_id = ?",
        (ts_fin, session_id)
    )
    conn.commit()


def exportar_detecciones(conn: sqlite3.Connection, ts_inicio: str, ts_fin: str,
                          session_id: str):
    """
    Exporta las detecciones capturadas entre ts_inicio y ts_fin.
    Usa ambas tablas: inference_frames y detections_v2.
    """
    RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)

    # -- Frames de inferencia ---------------------------------------------------
    frames = conn.execute("""
        SELECT id, timestamp, source, inference_ms, frame_w, frame_h,
               detections_count, confirmed, camera_mode
        FROM inference_frames
        WHERE timestamp >= ? AND timestamp <= ?
        ORDER BY timestamp
    """, (ts_inicio, ts_fin)).fetchall()

    salida_frames = RESULTADOS_DIR / f"sesion_{session_id}_frames.csv"
    campos_frames = ["id", "timestamp", "source", "inference_ms",
                     "frame_w", "frame_h", "detections_count", "confirmed",
                     "camera_mode"]
    with open(salida_frames, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(campos_frames)
        for row in frames:
            writer.writerow([row[c] for c in campos_frames])

    # -- Detecciones individuales -----------------------------------------------
    detecciones = conn.execute("""
        SELECT id, timestamp, class_name, confidence, x1, y1, x2, y2,
               source, inference_ms, confirmed, camera_mode, image_path, track_id
        FROM detections_v2
        WHERE timestamp >= ? AND timestamp <= ?
        ORDER BY timestamp
    """, (ts_inicio, ts_fin)).fetchall()

    salida_det = RESULTADOS_DIR / f"sesion_{session_id}_detecciones.csv"
    campos_det = ["id", "timestamp", "class_name", "confidence",
                  "x1", "y1", "x2", "y2", "source", "inference_ms",
                  "confirmed", "camera_mode", "image_path", "track_id"]
    with open(salida_det, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(campos_det)
        for row in detecciones:
            writer.writerow([row[c] for c in campos_det])

    return len(frames), len(detecciones), salida_frames, salida_det


# -- Main -----------------------------------------------------------------------

def main():
    RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print("EVAL-05 — Registro de sesión experimental  (Sección 4.3)")
    print("=" * 65)
    print("Ejecuta este script ANTES de iniciar el vuelo de prueba.\n")

    if not DB_PATH.exists():
        print(f"[ERROR] No se encontró la base de datos: {DB_PATH}")
        print("  Inicia el sistema SIRAN al menos una vez antes de usar este script.")
        return

    # -- Recopilar datos de la sesión -------------------------------------------
    print("--- Parámetros de la sesión -------------------------------------")
    distancia    = int(pedir_opcion("Distancia (metros)",
                                    DISTANCIAS_VALIDAS))
    iluminacion  = pedir_opcion("Condición de iluminación",
                                ILUMINACIONES_VALIDAS)
    duracion_est = pedir_entero("Duración estimada (minutos)", 1, 300)
    notas        = input("Notas adicionales (Enter para omitir): ").strip() or None

    # -- Generar session_id -----------------------------------------------------
    ts_inicio   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fecha_slug  = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_id  = f"SES_{fecha_slug}_{distancia}m_{iluminacion}"

    print("\n" + "-" * 65)
    print(f"  SESSION ID : {session_id}")
    print(f"  Inicio     : {ts_inicio}")
    print(f"  Distancia  : {distancia} m")
    print(f"  Iluminación: {iluminacion}")
    print(f"  Duración   : ~{duracion_est} min")
    if notas:
        print(f"  Notas      : {notas}")
    print("-" * 65)
    print("\n⚠  ANOTA EL SESSION ID — lo necesitarás para eval_06 y eval_08")
    print(f"\n  >> {session_id} <<\n")

    # -- Registrar en BD --------------------------------------------------------
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        crear_tabla_sessions(conn)
        insertar_session(conn, {
            "session_id":            session_id,
            "timestamp_inicio":      ts_inicio,
            "distancia_m":           distancia,
            "iluminacion":           iluminacion,
            "duracion_estimada_min": duracion_est,
            "notas":                 notas,
        })
        print(f"✓ Sesión registrada en la base de datos.")
        print("\n--------------------------------------------------------------")
        print("  Inicia el sistema SIRAN ahora y realiza el vuelo de prueba.")
        print("  Cuando termines, vuelve aquí y presiona Enter.")
        print("--------------------------------------------------------------")
        input("\n  Presiona Enter cuando hayas finalizado el vuelo... ")

        # -- Registrar fin de sesión --------------------------------------------
        ts_fin = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        registrar_fin(conn, session_id, ts_fin)
        print(f"\n  Fin registrado: {ts_fin}")

        # -- Exportar detecciones -----------------------------------------------
        n_frames, n_det, p_frames, p_det = exportar_detecciones(
            conn, ts_inicio, ts_fin, session_id
        )
        print(f"\n  Frames capturados    : {n_frames:,}")
        print(f"  Detecciones totales  : {n_det:,}")
        print(f"\n  ✓ Exportado: {p_frames.relative_to(PROJECT_ROOT)}")
        print(f"  ✓ Exportado: {p_det.relative_to(PROJECT_ROOT)}")

    finally:
        conn.close()

    print("\n" + "=" * 65)
    print(f"Sesión {session_id} completada y exportada.")
    print("Usa eval_06_por_distancia.py para analizar los resultados.")
    print("=" * 65)


if __name__ == "__main__":
    main()

