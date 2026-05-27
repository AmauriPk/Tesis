#!/usr/bin/env python3
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, OSError):
    pass
"""
eval_02_metricas_modelo.py — Métricas del modelo entrenado (Sección 4.1.2)
---------------------------------------------------------------------------
Lee el results.csv más reciente de Ultralytics y verifica los criterios RNF-02.
NO toca el código de la aplicación SIRAN.

Uso:
    python eval_02_metricas_modelo.py

Salida:
    evaluacion/resultados/metricas_modelo.csv
"""

import csv
from pathlib import Path

# -- Rutas ----------------------------------------------------------------------
SCRIPT_DIR   = Path(__file__).parent
EVAL_DIR     = SCRIPT_DIR.parent
PROJECT_ROOT = EVAL_DIR.parent
RESULTADOS_DIR = EVAL_DIR / "resultados"

# -- Criterios de aceptación (RNF-02) ------------------------------------------
CRITERIO_PRECISION = 0.85   # metrics/precision(B)  ≥ 0.85
CRITERIO_RECALL    = 0.70   # metrics/recall(B)     ≥ 0.70
CRITERIO_MAP05     = 0.80   # metrics/mAP50(B)      ≥ 0.80
# mAP50-95 se reporta sin criterio de aceptación en la tesis

# -- Funciones ------------------------------------------------------------------

def encontrar_results_csv() -> Path | None:
    """
    Busca el results.csv más reciente en runs/detect/train*/.
    Ultralytics guarda cada entrenamiento en runs/detect/trainN/.
    Devuelve la ruta al CSV o None si no existe ninguno.
    """
    runs_root = PROJECT_ROOT / "runs" / "detect"
    if not runs_root.exists():
        return None

    candidatos = list(runs_root.glob("train*/results.csv"))
    if not candidatos:
        return None

    # El más reciente por fecha de modificación
    return max(candidatos, key=lambda p: p.stat().st_mtime)


def leer_ultima_fila(csv_path: Path) -> dict | None:
    """Lee la última fila (última época) del results.csv de Ultralytics."""
    with open(csv_path, newline="", encoding="utf-8") as fh:
        filas = list(csv.DictReader(fh))
    if not filas:
        return None
    # Normalizar: quitar espacios en nombres de columnas
    return {k.strip(): v.strip() for k, v in filas[-1].items()}


def veredicto(valor: float, criterio: float) -> str:
    return "✓ CUMPLE" if valor >= criterio else "✗ NO CUMPLE"


def main():
    RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print("EVAL-02 — Métricas del modelo  (Sección 4.1.2 / RNF-02)")
    print("=" * 65)

    csv_path = encontrar_results_csv()
    if csv_path is None:
        print("\n[ERROR] No se encontró ningún results.csv en runs/detect/train*/")
        print("  Asegúrate de haber completado al menos un entrenamiento con")
        print("  Ultralytics (train.py) antes de ejecutar este script.")
        return

    print(f"\nArchivo leído : {csv_path.relative_to(PROJECT_ROOT)}")

    fila = leer_ultima_fila(csv_path)
    if fila is None:
        print("\n[ERROR] El archivo results.csv está vacío o no tiene filas de datos.")
        return

    epoch      = fila.get("epoch", "?")
    precision  = float(fila.get("metrics/precision(B)", 0))
    recall     = float(fila.get("metrics/recall(B)", 0))
    map50      = float(fila.get("metrics/mAP50(B)", 0))
    map50_95   = float(fila.get("metrics/mAP50-95(B)", 0))

    print(f"Época evaluada: {epoch} (última del entrenamiento)\n")

    # -- Tabla de resultados ----------------------------------------------------
    metricas = [
        ("Precisión",      f"≥ {CRITERIO_PRECISION:.2f}", CRITERIO_PRECISION, precision),
        ("Recall",         f"≥ {CRITERIO_RECALL:.2f}",    CRITERIO_RECALL,    recall),
        ("mAP@0.5",        f"≥ {CRITERIO_MAP05:.2f}",     CRITERIO_MAP05,     map50),
        ("mAP@0.5:0.95",   "—",                           None,               map50_95),
    ]

    filas_csv = []
    hdr = f"{'Métrica':<20} {'Criterio':>10} {'Resultado':>10} {'Veredicto':>14}"
    sep = "-" * 58
    print(hdr)
    print(sep)

    for nombre, crit_str, criterio_val, valor in metricas:
        verd = veredicto(valor, criterio_val) if criterio_val is not None else "—"
        print(f"{nombre:<20} {crit_str:>10} {valor:>10.4f} {verd:>14}")
        filas_csv.append({
            "Metrica":   nombre,
            "Criterio":  crit_str,
            "Resultado": f"{valor:.4f}",
            "Veredicto": verd,
            "Epoca":     epoch,
        })

    # -- Veredicto global -------------------------------------------------------
    aprobado = (
        precision >= CRITERIO_PRECISION
        and recall    >= CRITERIO_RECALL
        and map50     >= CRITERIO_MAP05
    )
    print(sep)
    print(f"\nVEREDICTO RNF-02: "
          f"{'✓ MODELO APROBADO' if aprobado else '✗ MODELO NO APRUEBA — revisar entrenamiento'}")

    filas_csv.append({
        "Metrica":   "GLOBAL RNF-02",
        "Criterio":  "Todos ≥ umbral",
        "Resultado": "—",
        "Veredicto": "✓ APROBADO" if aprobado else "✗ NO APROBADO",
        "Epoca":     epoch,
    })

    # -- Guardar CSV ------------------------------------------------------------
    salida = RESULTADOS_DIR / "metricas_modelo.csv"
    campos = ["Metrica", "Criterio", "Resultado", "Veredicto", "Epoca"]
    with open(salida, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=campos)
        writer.writeheader()
        writer.writerows(filas_csv)

    print(f"\n✓ Reporte guardado en: {salida.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()

