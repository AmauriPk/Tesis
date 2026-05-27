#!/usr/bin/env python3
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, OSError):
    pass
"""
eval_07_falsos_positivos.py — Tasa de falsos positivos (Sección 4.3.3)
------------------------------------------------------------------------
Calcula la tasa de falsas alarmas cruzando las alertas generadas por SIRAN
con anotaciones manuales del investigador.
NO toca el código de la aplicación SIRAN.

Flujo de trabajo:
  1. Ejecuta este script una primera vez → genera plantilla de anotaciones.
  2. Abre evaluacion/anotaciones/sesion_distractores.csv con Excel/LibreOffice.
  3. Para cada event_id, escribe 1 si fue falso positivo, 0 si fue correcto.
  4. Guarda el archivo y vuelve a ejecutar este script.

Archivo de anotaciones:
  evaluacion/anotaciones/sesion_distractores.csv
  Columnas: event_id, es_falso_positivo (0 = verdadero positivo, 1 = FP)

Criterio de aceptación (RNF-03):
  Tasa de falsos positivos ≤ 5 %

Uso:
    python eval_07_falsos_positivos.py

Salida:
    evaluacion/anotaciones/sesion_distractores.csv  (plantilla si no existe)
    evaluacion/resultados/analisis_falsos_positivos.csv
"""

import csv
import sqlite3
from pathlib import Path

# -- Rutas ----------------------------------------------------------------------
SCRIPT_DIR     = Path(__file__).parent
EVAL_DIR       = SCRIPT_DIR.parent
PROJECT_ROOT   = EVAL_DIR.parent
RESULTADOS_DIR = EVAL_DIR / "resultados"
ANOTACIONES_DIR = EVAL_DIR / "anotaciones"
DB_PATH        = PROJECT_ROOT / "detections.db"
ARCHIVO_ANOT   = ANOTACIONES_DIR / "sesion_distractores.csv"

# -- Criterio de aceptación (RNF-03) -------------------------------------------
CRITERIO_FP_MAX = 0.05  # Tasa de FP ≤ 5 %

# -- Funciones ------------------------------------------------------------------

def generar_plantilla(conn: sqlite3.Connection):
    """
    Genera una plantilla vacía de anotaciones con todos los eventos
    registrados en detection_events.
    El investigador debe llenar la columna es_falso_positivo.
    """
    ANOTACIONES_DIR.mkdir(parents=True, exist_ok=True)

    eventos = conn.execute("""
        SELECT id, started_at, ended_at, max_confidence,
               detection_count, status, source
        FROM detection_events
        ORDER BY started_at
    """).fetchall()

    campos = ["event_id", "started_at", "ended_at", "max_confidence",
              "detection_count", "status", "source", "es_falso_positivo"]

    with open(ARCHIVO_ANOT, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=campos)
        writer.writeheader()
        for ev in eventos:
            writer.writerow({
                "event_id":          ev["id"],
                "started_at":        ev["started_at"],
                "ended_at":          ev["ended_at"] or "",
                "max_confidence":    f"{ev['max_confidence']:.4f}" if ev["max_confidence"] else "",
                "detection_count":   ev["detection_count"] or 0,
                "status":            ev["status"] or "",
                "source":            ev["source"] or "",
                "es_falso_positivo": "",  # ← el investigador rellena esto (0 o 1)
            })

    print(f"\n✓ Plantilla generada con {len(eventos)} eventos:")
    print(f"  {ARCHIVO_ANOT.relative_to(PROJECT_ROOT)}")
    print("\n  INSTRUCCIONES:")
    print("  1. Abre el CSV con Excel o LibreOffice Calc.")
    print("  2. Para cada fila escribe en 'es_falso_positivo':")
    print("       0 → el sistema detectó correctamente (verdadero positivo)")
    print("       1 → fue una falsa alarma (falso positivo)")
    print("  3. Guarda y vuelve a ejecutar este script.")


def leer_anotaciones() -> dict[int, int]:
    """
    Lee el archivo de anotaciones. Retorna {event_id: es_falso_positivo}.
    Solo incluye filas con valor 0 o 1.
    """
    anotaciones = {}
    with open(ARCHIVO_ANOT, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for i, fila in enumerate(reader, 2):  # fila 2 = primera de datos
            eid_raw = fila.get("event_id", "").strip()
            fp_raw  = fila.get("es_falso_positivo", "").strip()
            if not eid_raw:
                continue
            try:
                eid = int(eid_raw)
            except ValueError:
                print(f"  [AVISO] Fila {i}: event_id no válido '{eid_raw}' — ignorada")
                continue
            if fp_raw == "":
                continue  # sin anotar
            if fp_raw not in ("0", "1"):
                print(f"  [AVISO] Fila {i}: valor '{fp_raw}' no es 0 ni 1 — ignorada")
                continue
            anotaciones[eid] = int(fp_raw)
    return anotaciones


def main():
    RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)
    ANOTACIONES_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print("EVAL-07 — Tasa de falsos positivos  (Sección 4.3.3 / RNF-03)")
    print("=" * 65)

    if not DB_PATH.exists():
        print(f"\n[ERROR] No se encontró: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        # Verificar que la tabla detection_events existe
        tablas = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        if "detection_events" not in tablas:
            print("\n[ERROR] La tabla 'detection_events' no existe en la BD.")
            print("  El sistema SIRAN debe haber registrado eventos de detección.")
            return

        total_eventos_db = conn.execute(
            "SELECT COUNT(*) FROM detection_events"
        ).fetchone()[0]

        # Si no existe el archivo de anotaciones, generarlo
        if not ARCHIVO_ANOT.exists():
            print(f"\n[INFO] Archivo de anotaciones no encontrado.")
            print(f"  Total de eventos en la BD: {total_eventos_db}")
            generar_plantilla(conn)
            return

        # Leer anotaciones existentes
        print(f"\nArchivo de anotaciones: {ARCHIVO_ANOT.relative_to(PROJECT_ROOT)}")
        anotaciones = leer_anotaciones()

        sin_anotar = total_eventos_db - len(anotaciones)
        if sin_anotar > 0:
            print(f"\n[AVISO] {sin_anotar} evento(s) aún sin anotar.")
            print("  Los resultados se calculan con los eventos ya anotados.")

        if not anotaciones:
            print("\n[SIN DATOS] No hay eventos anotados aún.")
            print("  Rellena la columna 'es_falso_positivo' en el archivo CSV")
            print(f"  ({ARCHIVO_ANOT.name}) y vuelve a ejecutar.")
            return

    finally:
        conn.close()

    # -- Cálculos ---------------------------------------------------------------
    total_anotados = len(anotaciones)
    total_fp       = sum(v for v in anotaciones.values() if v == 1)
    total_vp       = total_anotados - total_fp
    tasa_fp        = total_fp / total_anotados if total_anotados > 0 else 0.0
    cumple         = tasa_fp <= CRITERIO_FP_MAX

    # -- Tabla de resultados ----------------------------------------------------
    print(f"\n  Total eventos analizados : {total_anotados:>6,}")
    print(f"  Verdaderos positivos     : {total_vp:>6,}")
    print(f"  Falsos positivos (FP)    : {total_fp:>6,}")
    print(f"  Tasa de FP               : {tasa_fp:>6.2%}")
    print(f"  Criterio (RNF-03)        : ≤ {CRITERIO_FP_MAX:.0%}")
    print(f"\n  VEREDICTO: {'✓ CUMPLE RNF-03' if cumple else '✗ NO CUMPLE RNF-03'}")

    # -- Guardar CSV ------------------------------------------------------------
    salida = RESULTADOS_DIR / "analisis_falsos_positivos.csv"
    filas_csv = [
        {"Metrica": "Total eventos anotados",     "Valor": total_anotados,
         "Criterio": "—",                          "Veredicto": "—"},
        {"Metrica": "Verdaderos positivos (VP)",  "Valor": total_vp,
         "Criterio": "—",                          "Veredicto": "—"},
        {"Metrica": "Falsos positivos (FP)",      "Valor": total_fp,
         "Criterio": "—",                          "Veredicto": "—"},
        {"Metrica": "Tasa de FP",                 "Valor": f"{tasa_fp:.4f}",
         "Criterio": f"≤ {CRITERIO_FP_MAX:.2f}",  "Veredicto": "✓ CUMPLE" if cumple else "✗ NO CUMPLE"},
        {"Metrica": "GLOBAL RNF-03",              "Valor": "—",
         "Criterio": f"FP ≤ {CRITERIO_FP_MAX:.0%}", "Veredicto": "✓ APROBADO" if cumple else "✗ NO APROBADO"},
    ]
    campos = ["Metrica", "Valor", "Criterio", "Veredicto"]
    with open(salida, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=campos)
        writer.writeheader()
        writer.writerows(filas_csv)

    print(f"\n✓ Reporte guardado en: {salida.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()

