#!/usr/bin/env python3
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, OSError):
    pass
"""
eval_06_por_distancia.py — Métricas por distancia (Sección 4.3.1)
------------------------------------------------------------------
Analiza el rendimiento del sistema SIRAN agrupado por distancia de detección,
leyendo las sesiones experimentales registradas con eval_05.
NO toca el código de la aplicación SIRAN.

Tablas usadas:
  - experiment_sessions  (creada por eval_05)
  - inference_frames     (detections.db)
  - detections_v2        (detections.db)

Criterio de aceptación (RF-03):
  Confianza promedio de detección ≥ 0.60 en todas las distancias.

Uso:
    python eval_06_por_distancia.py

Salida:
    evaluacion/resultados/resultados_por_distancia.csv
"""

import csv
import sqlite3
from pathlib import Path

# -- Rutas ----------------------------------------------------------------------
SCRIPT_DIR   = Path(__file__).parent
EVAL_DIR     = SCRIPT_DIR.parent
PROJECT_ROOT = EVAL_DIR.parent
RESULTADOS_DIR = EVAL_DIR / "resultados"
DB_PATH = PROJECT_ROOT / "detections.db"

# -- Criterio de aceptación (RF-03) --------------------------------------------
CRITERIO_CONFIANZA_MIN = 0.60   # Confianza promedio ≥ 0.60

# -- Funciones ------------------------------------------------------------------

def verificar_tablas(conn: sqlite3.Connection) -> list[str]:
    """Retorna lista de tablas faltantes."""
    existentes = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    requeridas = {"experiment_sessions", "inference_frames", "detections_v2"}
    return sorted(requeridas - existentes)


def obtener_sesiones(conn: sqlite3.Connection) -> list:
    """Lista todas las sesiones completadas (con timestamp_fin)."""
    return conn.execute("""
        SELECT session_id, distancia_m, iluminacion,
               timestamp_inicio, timestamp_fin
        FROM experiment_sessions
        WHERE timestamp_fin IS NOT NULL
        ORDER BY distancia_m, timestamp_inicio
    """).fetchall()


def metricas_sesion(conn: sqlite3.Connection,
                    ts_inicio: str, ts_fin: str) -> dict:
    """
    Calcula métricas para una sesión dado su rango de tiempo.

    Retorna:
        total_frames     — frames procesados
        frames_confirmados — frames con detección confirmada
        tasa_deteccion   — ratio frames confirmados / total
        fps_promedio     — FPS promedio (1000 / inference_ms)
        confianza_prom   — confianza media de detecciones_v2
        n_detecciones    — total de detecciones individuales
    """
    # Frames de inferencia
    frames = conn.execute("""
        SELECT inference_ms, confirmed
        FROM inference_frames
        WHERE timestamp >= ? AND timestamp <= ?
          AND inference_ms IS NOT NULL AND inference_ms > 0
    """, (ts_inicio, ts_fin)).fetchall()

    if not frames:
        return {
            "total_frames": 0, "frames_confirmados": 0,
            "tasa_deteccion": 0.0, "fps_promedio": 0.0,
            "confianza_prom": None, "n_detecciones": 0,
        }

    total_frames      = len(frames)
    frames_confirmados = sum(1 for f in frames if f[1])
    tasa_deteccion    = frames_confirmados / total_frames
    fps_promedio      = sum(1000.0 / f[0] for f in frames) / total_frames

    # Confianza de detecciones individuales
    confs = conn.execute("""
        SELECT confidence FROM detections_v2
        WHERE timestamp >= ? AND timestamp <= ?
          AND confirmed = 1
    """, (ts_inicio, ts_fin)).fetchall()

    confianza_prom = (sum(c[0] for c in confs) / len(confs)) if confs else None
    n_detecciones  = len(confs)

    return {
        "total_frames":      total_frames,
        "frames_confirmados": frames_confirmados,
        "tasa_deteccion":    tasa_deteccion,
        "fps_promedio":      fps_promedio,
        "confianza_prom":    confianza_prom,
        "n_detecciones":     n_detecciones,
    }


def veredicto_confianza(conf: float | None) -> str:
    if conf is None:
        return "— SIN DATOS"
    return "✓ CUMPLE" if conf >= CRITERIO_CONFIANZA_MIN else "✗ NO CUMPLE"


def main():
    RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print("EVAL-06 — Métricas por distancia  (Sección 4.3.1 / RF-03)")
    print("=" * 65)

    if not DB_PATH.exists():
        print(f"\n[ERROR] No se encontró: {DB_PATH}")
        print("  Registra sesiones con eval_05_sesion_prueba.py primero.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        faltantes = verificar_tablas(conn)
        if faltantes:
            print(f"\n[ERROR] Faltan estas tablas en la BD: {faltantes}")
            if "experiment_sessions" in faltantes:
                print("  Ejecuta eval_05_sesion_prueba.py para crear la tabla.")
            return

        sesiones = obtener_sesiones(conn)
        if not sesiones:
            print("\n[SIN DATOS] No hay sesiones completadas registradas.")
            print("  Usa eval_05_sesion_prueba.py para registrar vuelos de prueba.")
            return

        print(f"\nSesiones encontradas: {len(sesiones)}\n")

        filas_csv = []

        # Agrupar resultados por distancia
        por_distancia: dict[int, list] = {}
        for ses in sesiones:
            sid = ses["session_id"]
            dist = ses["distancia_m"]
            ilum = ses["iluminacion"]
            ts_i = ses["timestamp_inicio"]
            ts_f = ses["timestamp_fin"]

            m = metricas_sesion(conn, ts_i, ts_f)
            entrada = {
                "Sesion_id":          sid,
                "Distancia_m":        dist,
                "Iluminacion":        ilum,
                "Total_frames":       m["total_frames"],
                "Frames_confirmados": m["frames_confirmados"],
                "Tasa_deteccion":     f"{m['tasa_deteccion']:.3f}",
                "FPS_promedio":       f"{m['fps_promedio']:.2f}" if m["fps_promedio"] else "0.00",
                "Confianza_promedio": f"{m['confianza_prom']:.4f}" if m["confianza_prom"] else "—",
                "N_detecciones":      m["n_detecciones"],
                "Veredicto":          veredicto_confianza(m["confianza_prom"]),
            }
            filas_csv.append(entrada)
            por_distancia.setdefault(dist, []).append(entrada)

        # -- Tabla por sesión ---------------------------------------------------
        hdr = (f"{'Sesión':<36} {'Dist':>5} {'Conf':>6} "
               f"{'Tasa':>6} {'FPS':>7} {'Veredicto':>14}")
        sep = "-" * 80
        print(hdr)
        print(sep)
        for f in filas_csv:
            print(f"{f['Sesion_id']:<36} {f['Distancia_m']:>4}m "
                  f"{f['Confianza_promedio']:>6} {f['Tasa_deteccion']:>6} "
                  f"{f['FPS_promedio']:>7} {f['Veredicto']:>14}")

        # -- Resumen agrupado por distancia -------------------------------------
        print(f"\n{'-'*65}")
        print("RESUMEN POR DISTANCIA")
        print(f"{'-'*65}")
        print(f"{'Distancia':>10} {'Sesiones':>9} {'Conf prom':>10} "
              f"{'Tasa prom':>10} {'FPS prom':>9} {'Veredicto':>14}")
        print("-" * 65)

        filas_resumen = []
        for dist in sorted(por_distancia.keys()):
            grupo = por_distancia[dist]
            confs_validas = [float(g["Confianza_promedio"])
                             for g in grupo if g["Confianza_promedio"] != "—"]
            tasas = [float(g["Tasa_deteccion"]) for g in grupo]
            fps_vals = [float(g["FPS_promedio"]) for g in grupo]

            conf_prom = sum(confs_validas) / len(confs_validas) if confs_validas else None
            tasa_prom = sum(tasas) / len(tasas) if tasas else 0.0
            fps_prom  = sum(fps_vals) / len(fps_vals) if fps_vals else 0.0

            verd = veredicto_confianza(conf_prom)
            conf_str = f"{conf_prom:.4f}" if conf_prom is not None else "—"
            print(f"{str(dist) + ' m':>10} {len(grupo):>9} {conf_str:>10} "
                  f"{tasa_prom:>10.3f} {fps_prom:>9.2f} {verd:>14}")
            filas_resumen.append({
                "Distancia_m":        dist,
                "Num_sesiones":       len(grupo),
                "Confianza_promedio": conf_str,
                "Tasa_deteccion_prom": f"{tasa_prom:.3f}",
                "FPS_promedio":       f"{fps_prom:.2f}",
                "Veredicto":          verd,
            })

    finally:
        conn.close()

    # -- Guardar CSV (detalle de sesiones + resumen) ----------------------------
    salida = RESULTADOS_DIR / "resultados_por_distancia.csv"
    campos = ["Sesion_id", "Distancia_m", "Iluminacion", "Total_frames",
              "Frames_confirmados", "Tasa_deteccion", "FPS_promedio",
              "Confianza_promedio", "N_detecciones", "Veredicto"]
    with open(salida, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=campos)
        writer.writeheader()
        writer.writerows(filas_csv)
        # Separador + resumen
        writer.writerow({c: "" for c in campos})
        writer.writerow({c: ("RESUMEN_POR_DISTANCIA" if c == "Sesion_id" else "")
                         for c in campos})
        campos_res = ["Distancia_m", "Num_sesiones", "Confianza_promedio",
                      "Tasa_deteccion_prom", "FPS_promedio", "Veredicto"]
        for fr in filas_resumen:
            row = {c: fr.get(c, "") for c in campos}
            writer.writerow(row)

    print(f"\n✓ Reporte guardado en: {salida.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()

