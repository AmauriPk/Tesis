#!/usr/bin/env python3
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, OSError):
    pass
"""
eval_01_dataset.py — Composición del dataset (Sección 4.1.1)
-------------------------------------------------------------
Cuenta imágenes y etiquetas por split del dataset de entrenamiento.
NO toca el código de la aplicación SIRAN.

Uso:
    python eval_01_dataset.py

Salida:
    evaluacion/resultados/dataset_reporte.csv
"""

import csv
from pathlib import Path

# -- Rutas (relativas al script) ------------------------------------------------
SCRIPT_DIR   = Path(__file__).parent
EVAL_DIR     = SCRIPT_DIR.parent
PROJECT_ROOT = EVAL_DIR.parent
RESULTADOS_DIR = EVAL_DIR / "resultados"

# -- Configuración del dataset --------------------------------------------------
# El dataset Roboflow/Ultralytics está en dataset/ con subcarpetas images/ y labels/
DATASET_ROOT = PROJECT_ROOT / "dataset"

# Nombres reales de los splits (Roboflow usa "valid", no "val")
# Proporción esperada: referencia teórica para la tesis
SPLITS = {
    "train": 0.70,
    "valid": 0.20,
    "test":  0.10,
}

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

# -- Funciones ------------------------------------------------------------------

def contar_split(split_path: Path) -> tuple:
    """
    Cuenta imágenes positivas y negativas en un split.

    Una imagen es POSITIVA si tiene un archivo .txt de etiqueta
    en la carpeta labels/ con contenido (al menos una línea).
    Una imagen es NEGATIVA si no tiene .txt o el .txt está vacío.

    Retorna: (positivas, negativas, total)
    """
    images_dir = split_path / "images"
    labels_dir = split_path / "labels"

    if not images_dir.exists():
        return 0, 0, 0

    imagenes = [f for f in images_dir.iterdir()
                if f.is_file() and f.suffix.lower() in IMAGE_EXTS]
    total = len(imagenes)

    positivas = 0
    if labels_dir.exists():
        for img in imagenes:
            label = labels_dir / (img.stem + ".txt")
            if label.exists() and label.stat().st_size > 0:
                positivas += 1

    negativas = total - positivas
    return positivas, negativas, total


def main():
    RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print("EVAL-01 — Composición del dataset  (Sección 4.1.1)")
    print("=" * 65)
    print(f"Dataset raíz : {DATASET_ROOT}")

    if not DATASET_ROOT.exists():
        print(f"\n[ERROR] No se encontró la carpeta del dataset:")
        print(f"        {DATASET_ROOT}")
        print("  Verifica que DATASET_ROOT apunte a la ubicación correcta.")
        return

    filas = []
    total_global_img = 0

    for split_name, prop_esperada in SPLITS.items():
        split_path = DATASET_ROOT / split_name
        pos, neg, total = contar_split(split_path)
        total_global_img += total
        filas.append({
            "Split":             split_name,
            "Positivas":         pos,
            "Negativas":         neg,
            "Total":             total,
            "Proporcion_esperada": f"{prop_esperada:.0%}",
        })

    # Calcular porcentaje real
    for f in filas:
        pct = (f["Total"] / total_global_img * 100) if total_global_img > 0 else 0.0
        f["Porcentaje_real"] = f"{pct:.1f}%"

    # -- Imprimir tabla en consola ----------------------------------------------
    header = f"{'Split':<8} {'Positivas':>12} {'Negativas':>12} {'Total':>8}  {'%Esp':>6} {'%Real':>7}"
    sep    = "-" * 60
    print(f"\n{header}")
    print(sep)
    for f in filas:
        print(f"{f['Split']:<8} {f['Positivas']:>12,} {f['Negativas']:>12,} "
              f"{f['Total']:>8,}  {f['Proporcion_esperada']:>6} {f['Porcentaje_real']:>7}")
    print(sep)
    total_pos = sum(f["Positivas"] for f in filas)
    total_neg = sum(f["Negativas"] for f in filas)
    print(f"{'TOTAL':<8} {total_pos:>12,} {total_neg:>12,} {total_global_img:>8,}")

    # Tasa de clases positivas sobre el total
    tasa = total_pos / total_global_img * 100 if total_global_img > 0 else 0.0
    print(f"\n  Imágenes con dron (positivas): {total_pos:,} ({tasa:.1f}%)")
    print(f"  Imágenes sin dron (negativas): {total_neg:,} ({100-tasa:.1f}%)")

    # -- Guardar CSV ------------------------------------------------------------
    salida = RESULTADOS_DIR / "dataset_reporte.csv"
    campos = ["Split", "Positivas", "Negativas", "Total",
              "Proporcion_esperada", "Porcentaje_real"]
    with open(salida, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=campos)
        writer.writeheader()
        writer.writerows(filas)

    print(f"\n✓ Reporte guardado en: {salida.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()

