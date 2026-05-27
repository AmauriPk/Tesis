#!/usr/bin/env python3
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, OSError):
    pass
"""
eval_04_rendimiento_live.py — Rendimiento en tiempo real (Sección 4.2.1)
-------------------------------------------------------------------------
Lee la tabla inference_frames de detections.db y calcula FPS y latencia.
Verifica los criterios del RNF-01.
NO toca el código de la aplicación SIRAN.

Tabla usada: inference_frames
  - timestamp    TEXT    Marca de tiempo del frame
  - inference_ms REAL    Tiempo de inferencia en milisegundos
  - confirmed    INTEGER 1 si hubo detección confirmada, 0 si no

Uso:
    python eval_04_rendimiento_live.py
    (Opcional: filtrar por rango de fechas respondiendo a los prompts)

Salida:
    evaluacion/resultados/rendimiento_live.csv
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

# -- Criterios de aceptación (RNF-01) ------------------------------------------
CRITERIO_FPS_MIN      = 25.0   # FPS promedio ≥ 25
CRITERIO_LATENCIA_MAX = 100.0  # Latencia promedio ≤ 100 ms

# -- Funciones ------------------------------------------------------------------

def _limpiar_fecha(raw: str) -> str | None:
    """
    Valida y limpia un string de fecha.
    Quita BOM de Windows y caracteres invisibles.
    Retorna None si el string no parece una fecha válida.
    """
    import re as _re
    s = raw.strip().strip("﻿​").strip()
    if not s:
        return None
    # Debe comenzar con YYYY-MM-DD
    if not _re.match(r"\d{4}-\d{2}-\d{2}", s):
        return None
    return s


def pedir_rango_fechas() -> tuple[str | None, str | None]:
    """
    Pregunta al usuario si desea filtrar por rango de fechas.
    Devuelve (fecha_inicio, fecha_fin) o (None, None) para no filtrar.
    Formato esperado: YYYY-MM-DD HH:MM:SS
    """
    print("\n¿Deseas filtrar por rango de fechas? (Enter para usar todos los datos)")
    try:
        raw_desde = input("  Fecha inicio (YYYY-MM-DD HH:MM:SS) o Enter para omitir: ")
    except EOFError:
        return None, None
    desde = _limpiar_fecha(raw_desde)
    if desde is None:
        return None, None
    try:
        raw_hasta = input("  Fecha fin    (YYYY-MM-DD HH:MM:SS) o Enter para usar 'ahora': ")
    except EOFError:
        return desde, None
    hasta = _limpiar_fecha(raw_hasta)
    return desde, hasta


def percentil(valores: list, p: float) -> float:
    """Calcula el percentil p (0–100) de una lista de valores."""
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    idx = (len(ordenados) - 1) * p / 100
    bajo = int(idx)
    alto = min(bajo + 1, len(ordenados) - 1)
    fraccion = idx - bajo
    return ordenados[bajo] + fraccion * (ordenados[alto] - ordenados[bajo])


def veredicto(valor: float, criterio: float, mayor_mejor: bool = True) -> str:
    if mayor_mejor:
        return "✓ CUMPLE" if valor >= criterio else "✗ NO CUMPLE"
    else:
        return "✓ CUMPLE" if valor <= criterio else "✗ NO CUMPLE"


def main():
    RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print("EVAL-04 — Rendimiento en tiempo real  (Sección 4.2.1 / RNF-01)")
    print("=" * 65)

    if not DB_PATH.exists():
        print(f"\n[ERROR] No se encontró la base de datos:")
        print(f"        {DB_PATH}")
        print("  Inicia el sistema SIRAN al menos una vez para generar datos.")
        return

    # -- Filtro de fechas opcional ----------------------------------------------
    fecha_inicio, fecha_fin = pedir_rango_fechas()

    # -- Consulta a la base de datos --------------------------------------------
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        # Verificar que la tabla existe
        tablas = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        if "inference_frames" not in tablas:
            print("\n[ERROR] La tabla 'inference_frames' no existe en la base de datos.")
            print("  El sistema SIRAN debe haber registrado al menos un frame.")
            return

        # Construir consulta con filtros opcionales
        where_clauses = ["inference_ms IS NOT NULL", "inference_ms > 0"]
        params = []
        if fecha_inicio:
            where_clauses.append("timestamp >= ?")
            params.append(fecha_inicio)
        if fecha_fin:
            where_clauses.append("timestamp <= ?")
            params.append(fecha_fin)

        where = " AND ".join(where_clauses)
        query = f"SELECT inference_ms, confirmed FROM inference_frames WHERE {where}"
        filas = conn.execute(query, params).fetchall()

    finally:
        conn.close()

    if not filas:
        print("\n[SIN DATOS] No hay registros de frames en el rango especificado.")
        print("  Ejecuta el sistema SIRAN en modo detección y vuelve a intentarlo.")
        return

    # -- Cálculos ---------------------------------------------------------------
    latencias_ms = [f["inference_ms"] for f in filas]
    fps_valores  = [1000.0 / ms for ms in latencias_ms]
    confirmados  = sum(f["confirmed"] for f in filas if f["confirmed"])
    total_frames = len(filas)

    fps_promedio    = sum(fps_valores) / len(fps_valores)
    fps_minimo      = min(fps_valores)
    fps_maximo      = max(fps_valores)
    lat_promedio    = sum(latencias_ms) / len(latencias_ms)
    lat_maxima      = max(latencias_ms)
    lat_p95         = percentil(latencias_ms, 95)
    tasa_deteccion  = confirmados / total_frames * 100 if total_frames > 0 else 0.0

    # -- Tabla de resultados ----------------------------------------------------
    resultados = [
        ("FPS promedio",        fps_promedio,   "FPS",  CRITERIO_FPS_MIN,      True),
        ("FPS mínimo",          fps_minimo,     "FPS",  None,                  True),
        ("FPS máximo",          fps_maximo,     "FPS",  None,                  True),
        ("Latencia promedio",   lat_promedio,   "ms",   CRITERIO_LATENCIA_MAX, False),
        ("Latencia máxima",     lat_maxima,     "ms",   None,                  False),
        ("Latencia P95",        lat_p95,        "ms",   None,                  False),
        ("Frames analizados",   float(total_frames), "frames", None,          True),
        ("Tasa de detección",   tasa_deteccion, "%",    None,                  True),
    ]

    filas_csv = []
    print(f"\nTotal de frames analizados: {total_frames:,}")
    if fecha_inicio:
        print(f"Filtro de fecha: {fecha_inicio}  →  {fecha_fin or 'ahora'}")

    hdr = f"\n{'Métrica':<25} {'Valor':>10} {'Unidad':<8} {'Criterio':>10} {'Veredicto':>14}"
    sep = "-" * 72
    print(hdr)
    print(sep)

    for nombre, valor, unidad, criterio, mayor_mejor in resultados:
        if criterio is not None:
            crit_str = (f"≥ {criterio:.0f}" if mayor_mejor
                        else f"≤ {criterio:.0f}")
            verd = veredicto(valor, criterio, mayor_mejor)
        else:
            crit_str = "—"
            verd = "—"

        if unidad == "frames":
            val_str = f"{int(valor):,}"
        else:
            val_str = f"{valor:.2f}"

        print(f"{nombre:<25} {val_str:>10} {unidad:<8} {crit_str:>10} {verd:>14}")
        filas_csv.append({
            "Metrica":   nombre,
            "Valor":     val_str,
            "Unidad":    unidad,
            "Criterio":  crit_str,
            "Veredicto": verd,
        })

    # -- Veredicto global -------------------------------------------------------
    cumple = fps_promedio >= CRITERIO_FPS_MIN and lat_promedio <= CRITERIO_LATENCIA_MAX
    print(sep)
    print(f"\nVEREDICTO RNF-01: "
          f"{'✓ SISTEMA APROBADO' if cumple else '✗ SISTEMA NO APRUEBA RNF-01'}")
    print(f"  FPS prom {fps_promedio:.1f} (req ≥{CRITERIO_FPS_MIN:.0f})  |  "
          f"Latencia prom {lat_promedio:.1f} ms (req ≤{CRITERIO_LATENCIA_MAX:.0f} ms)")

    filas_csv.append({
        "Metrica":   "GLOBAL RNF-01",
        "Valor":     "—",
        "Unidad":    "—",
        "Criterio":  "FPS≥25 Y Lat≤100ms",
        "Veredicto": "✓ APROBADO" if cumple else "✗ NO APROBADO",
    })

    # -- Guardar CSV ------------------------------------------------------------
    salida = RESULTADOS_DIR / "rendimiento_live.csv"
    campos = ["Metrica", "Valor", "Unidad", "Criterio", "Veredicto"]
    with open(salida, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=campos)
        writer.writeheader()
        writer.writerows(filas_csv)

    print(f"\n✓ Reporte guardado en: {salida.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()

