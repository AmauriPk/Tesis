#!/usr/bin/env python3
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, OSError):
    pass
"""
eval_08_iluminacion.py — Comparativa por condición de iluminación (Sección 4.3.4)
-----------------------------------------------------------------------------------
Compara el rendimiento del sistema bajo distintas condiciones de luz.
Requiere anotaciones manuales del investigador sobre el número de pasadas
del dron por el encuadre durante cada sesión.
NO toca el código de la aplicación SIRAN.

Flujo de trabajo:
  1. Ejecuta este script una primera vez → genera plantilla de anotaciones.
  2. Abre evaluacion/anotaciones/pasadas_dron.csv con Excel/LibreOffice.
  3. Para cada sesión, completa:
       - num_pasadas            : cuántas veces cruzó el dron el encuadre
       - tiempo_en_encuadre_s   : segundos totales que el dron fue visible
       - tiempo_total_s         : duración total del vuelo en segundos
  4. Guarda y vuelve a ejecutar este script.

Criterio de aceptación (RNF-04):
  Recall ≥ 0.70 en ambas condiciones de iluminación evaluadas.

Definición de Recall aquí:
  Recall = detecciones confirmadas / pasadas totales
  (Una "pasada" se considera detectada si generó ≥1 frame confirmado)

Uso:
    python eval_08_iluminacion.py

Salida:
    evaluacion/anotaciones/pasadas_dron.csv  (plantilla si no existe)
    evaluacion/resultados/comparativa_iluminacion.csv
"""

import csv
import sqlite3
from pathlib import Path

# -- Rutas ----------------------------------------------------------------------
SCRIPT_DIR      = Path(__file__).parent
EVAL_DIR        = SCRIPT_DIR.parent
PROJECT_ROOT    = EVAL_DIR.parent
RESULTADOS_DIR  = EVAL_DIR / "resultados"
ANOTACIONES_DIR = EVAL_DIR / "anotaciones"
DB_PATH         = PROJECT_ROOT / "detections.db"
ARCHIVO_ANOT    = ANOTACIONES_DIR / "pasadas_dron.csv"

# -- Criterio de aceptación (RNF-04) -------------------------------------------
CRITERIO_RECALL_MIN = 0.70   # Recall ≥ 0.70

# Condiciones de iluminación a comparar
CONDICIONES = ["diurno_optimo", "contraluz", "sombra"]

# -- Funciones ------------------------------------------------------------------

def verificar_tablas(conn: sqlite3.Connection) -> list[str]:
    existentes = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    requeridas = {"experiment_sessions", "inference_frames", "detections_v2"}
    return sorted(requeridas - existentes)


def generar_plantilla(conn: sqlite3.Connection):
    """Genera plantilla de anotaciones con las sesiones disponibles."""
    ANOTACIONES_DIR.mkdir(parents=True, exist_ok=True)

    sesiones = conn.execute("""
        SELECT session_id, distancia_m, iluminacion,
               timestamp_inicio, timestamp_fin
        FROM experiment_sessions
        WHERE timestamp_fin IS NOT NULL
        ORDER BY iluminacion, distancia_m, timestamp_inicio
    """).fetchall()

    campos = ["session_id", "distancia_m", "iluminacion",
              "timestamp_inicio", "timestamp_fin",
              "num_pasadas", "tiempo_en_encuadre_s", "tiempo_total_s"]

    with open(ARCHIVO_ANOT, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=campos)
        writer.writeheader()
        for s in sesiones:
            writer.writerow({
                "session_id":          s["session_id"],
                "distancia_m":         s["distancia_m"],
                "iluminacion":         s["iluminacion"],
                "timestamp_inicio":    s["timestamp_inicio"],
                "timestamp_fin":       s["timestamp_fin"] or "",
                "num_pasadas":         "",   # ← el investigador completa esto
                "tiempo_en_encuadre_s": "",  # ← segundos visible (para TSE)
                "tiempo_total_s":       "",  # ← duración del vuelo (para TSE)
            })

    print(f"\n✓ Plantilla generada con {len(sesiones)} sesión(es):")
    print(f"  {ARCHIVO_ANOT.relative_to(PROJECT_ROOT)}")
    print("\n  INSTRUCCIONES:")
    print("  - num_pasadas          : cuántas veces cruzó el dron el encuadre")
    print("  - tiempo_en_encuadre_s : segundos totales que el dron fue visible")
    print("  - tiempo_total_s       : duración total del vuelo (segundos)")
    print("\n  Rellena estos campos y vuelve a ejecutar el script.")


def leer_anotaciones() -> dict[str, dict]:
    """Retorna {session_id: {num_pasadas, tiempo_en_encuadre_s, tiempo_total_s}}."""
    datos = {}
    with open(ARCHIVO_ANOT, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for i, fila in enumerate(reader, 2):
            sid = fila.get("session_id", "").strip()
            if not sid:
                continue
            try:
                datos[sid] = {
                    "distancia_m":          int(fila.get("distancia_m", 0) or 0),
                    "iluminacion":          fila.get("iluminacion", "").strip(),
                    "timestamp_inicio":     fila.get("timestamp_inicio", "").strip(),
                    "timestamp_fin":        fila.get("timestamp_fin", "").strip(),
                    "num_pasadas":          int(fila.get("num_pasadas", 0) or 0),
                    "tiempo_en_encuadre_s": float(fila.get("tiempo_en_encuadre_s") or 0),
                    "tiempo_total_s":       float(fila.get("tiempo_total_s") or 0),
                }
            except (ValueError, TypeError) as e:
                print(f"  [AVISO] Fila {i} ({sid}): {e} — ignorada")
    return datos


def detecciones_sesion(conn: sqlite3.Connection,
                       ts_inicio: str, ts_fin: str) -> dict:
    """Métricas de una sesión por rango de tiempo."""
    frames = conn.execute("""
        SELECT confirmed, inference_ms
        FROM inference_frames
        WHERE timestamp >= ? AND timestamp <= ?
          AND inference_ms IS NOT NULL AND inference_ms > 0
    """, (ts_inicio, ts_fin)).fetchall()

    if not frames:
        return {"total_frames": 0, "confirmados": 0, "conf_prom": None,
                "fps_prom": 0.0, "n_detecciones": 0, "n_eventos": 0}

    total = len(frames)
    conf_frm = sum(1 for f in frames if f[0])
    fps_prom = sum(1000.0 / f[1] for f in frames) / total

    confs = conn.execute("""
        SELECT confidence FROM detections_v2
        WHERE timestamp >= ? AND timestamp <= ? AND confirmed = 1
    """, (ts_inicio, ts_fin)).fetchall()
    conf_prom = sum(c[0] for c in confs) / len(confs) if confs else None

    n_eventos = conn.execute("""
        SELECT COUNT(*) FROM detection_events
        WHERE started_at >= ? AND started_at <= ?
    """, (ts_inicio, ts_fin)).fetchone()[0]

    return {
        "total_frames": total,
        "confirmados":  conf_frm,
        "conf_prom":    conf_prom,
        "fps_prom":     fps_prom,
        "n_detecciones": len(confs),
        "n_eventos":    n_eventos,
    }


def main():
    RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)
    ANOTACIONES_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print("EVAL-08 — Comparativa por iluminación  (Sección 4.3.4 / RNF-04)")
    print("=" * 65)

    if not DB_PATH.exists():
        print(f"\n[ERROR] No se encontró: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        faltantes = verificar_tablas(conn)
        if faltantes:
            print(f"\n[ERROR] Faltan tablas: {faltantes}")
            if "experiment_sessions" in faltantes:
                print("  Ejecuta eval_05_sesion_prueba.py primero.")
            return

        n_sesiones = conn.execute(
            "SELECT COUNT(*) FROM experiment_sessions WHERE timestamp_fin IS NOT NULL"
        ).fetchone()[0]

        if n_sesiones == 0:
            print("\n[SIN DATOS] No hay sesiones completadas.")
            print("  Usa eval_05_sesion_prueba.py para registrar vuelos.")
            return

        # Generar plantilla si no existe
        if not ARCHIVO_ANOT.exists():
            print(f"\n[INFO] Plantilla de anotaciones no encontrada.")
            generar_plantilla(conn)
            return

        # Leer anotaciones
        anotaciones = leer_anotaciones()
        sin_anotar = [sid for sid, d in anotaciones.items() if d["num_pasadas"] == 0]
        if sin_anotar:
            print(f"\n[AVISO] {len(sin_anotar)} sesión(es) sin num_pasadas anotado.")

        # Calcular métricas por sesión
        resultados_sesion = []
        for sid, anot in anotaciones.items():
            if not anot["timestamp_inicio"] or not anot["timestamp_fin"]:
                continue
            m = detecciones_sesion(conn, anot["timestamp_inicio"], anot["timestamp_fin"])

            # Recall: eventos detectados / num_pasadas
            num_pasadas = anot["num_pasadas"]
            if num_pasadas > 0 and m["n_eventos"] >= 0:
                recall = min(m["n_eventos"] / num_pasadas, 1.0)
            else:
                recall = None

            resultados_sesion.append({
                "session_id":    sid,
                "distancia_m":   anot["distancia_m"],
                "iluminacion":   anot["iluminacion"],
                "num_pasadas":   num_pasadas,
                "n_eventos":     m["n_eventos"],
                "conf_prom":     m["conf_prom"],
                "fps_prom":      m["fps_prom"],
                "recall":        recall,
                "readquisiciones": max(0, m["n_eventos"] - 1) if m["n_eventos"] > 0 else 0,
            })

    finally:
        conn.close()

    if not resultados_sesion:
        print("\n[SIN DATOS] No hay sesiones anotadas con timestamps válidos.")
        print(f"  Revisa {ARCHIVO_ANOT.name}")
        return

    # -- Agrupar por condición de iluminación ----------------------------------
    por_condicion: dict[str, list] = {}
    for r in resultados_sesion:
        cond = r["iluminacion"]
        por_condicion.setdefault(cond, []).append(r)

    filas_csv = []
    print(f"\n{'Condición':<18} {'Ses':>4} {'Conf':>6} {'Recall':>7} "
          f"{'Readq':>6} {'FPS':>7} {'Veredicto':>14}")
    sep = "-" * 68
    print(sep)

    for cond in sorted(por_condicion.keys()):
        grupo = por_condicion[cond]
        confs   = [r["conf_prom"] for r in grupo if r["conf_prom"] is not None]
        recalls = [r["recall"] for r in grupo if r["recall"] is not None]
        fps_vals = [r["fps_prom"] for r in grupo if r["fps_prom"] > 0]
        readqs  = sum(r["readquisiciones"] for r in grupo)

        conf_prom    = sum(confs) / len(confs) if confs else None
        recall_prom  = sum(recalls) / len(recalls) if recalls else None
        fps_prom_g   = sum(fps_vals) / len(fps_vals) if fps_vals else 0.0

        conf_str   = f"{conf_prom:.4f}"   if conf_prom   is not None else "—"
        recall_str = f"{recall_prom:.4f}" if recall_prom is not None else "—"

        verd = ("✓ CUMPLE" if recall_prom is not None and recall_prom >= CRITERIO_RECALL_MIN
                else ("✗ NO CUMPLE" if recall_prom is not None else "— PENDIENTE"))

        print(f"{cond:<18} {len(grupo):>4} {conf_str:>6} {recall_str:>7} "
              f"{readqs:>6} {fps_prom_g:>7.2f} {verd:>14}")

        filas_csv.append({
            "Condicion":         cond,
            "Num_sesiones":      len(grupo),
            "Confianza_promedio": conf_str,
            "Recall":            recall_str,
            "Readquisiciones":   readqs,
            "FPS_promedio":      f"{fps_prom_g:.2f}",
            "Criterio":          f"Recall ≥ {CRITERIO_RECALL_MIN:.2f}",
            "Veredicto":         verd,
        })

    print(sep)
    # Veredicto global
    todos_cumplen = all(
        float(f["Recall"]) >= CRITERIO_RECALL_MIN
        for f in filas_csv if f["Recall"] != "—"
    )
    print(f"\nVEREDICTO RNF-04: "
          f"{'✓ CUMPLE en todas las condiciones' if todos_cumplen else '✗ Alguna condición no cumple'}")

    # -- Guardar CSV ------------------------------------------------------------
    salida = RESULTADOS_DIR / "comparativa_iluminacion.csv"
    campos = ["Condicion", "Num_sesiones", "Confianza_promedio", "Recall",
              "Readquisiciones", "FPS_promedio", "Criterio", "Veredicto"]
    with open(salida, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=campos)
        writer.writeheader()
        writer.writerows(filas_csv)

    print(f"\n✓ Reporte guardado en: {salida.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()

