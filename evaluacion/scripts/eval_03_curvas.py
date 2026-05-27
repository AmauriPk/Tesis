#!/usr/bin/env python3
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, OSError):
    pass
"""
eval_03_curvas.py — Copiar figuras de Ultralytics (Sección 4.1.3)
------------------------------------------------------------------
Busca las figuras de entrenamiento generadas por Ultralytics y las copia
a evaluacion/figuras_cap4/ con nombres normalizados para la tesis.
ÚNICO script que usa shutil (permitido por las reglas de la suite).
NO toca el código de la aplicación SIRAN.

Uso:
    python eval_03_curvas.py

Salida:
    evaluacion/figuras_cap4/fig_4_1_curvas_perdida.png
    evaluacion/figuras_cap4/fig_4_1_curva_PR.png
    evaluacion/figuras_cap4/fig_4_1_matriz_confusion.png
"""

import shutil
from pathlib import Path

# -- Rutas ----------------------------------------------------------------------
SCRIPT_DIR   = Path(__file__).parent
EVAL_DIR     = SCRIPT_DIR.parent
PROJECT_ROOT = EVAL_DIR.parent
FIGURAS_DIR  = EVAL_DIR / "figuras_cap4"

# -- Mapeo: nombre original → nombre para la tesis -----------------------------
FIGURAS_OBJETIVO = {
    "results.png":             "fig_4_1_curvas_perdida.png",
    "PR_curve.png":            "fig_4_1_curva_PR.png",
    "confusion_matrix.png":    "fig_4_1_matriz_confusion.png",
}

# Figuras opcionales (no interrumpen si no existen)
FIGURAS_OPCIONALES = {
    "F1_curve.png":            "fig_4_1_curva_F1.png",
    "P_curve.png":             "fig_4_1_curva_precision.png",
    "R_curve.png":             "fig_4_1_curva_recall.png",
    "confusion_matrix_normalized.png": "fig_4_1_matriz_confusion_norm.png",
    "val_batch0_pred.jpg":     "fig_4_1_predicciones_val.jpg",
}

# -- Funciones ------------------------------------------------------------------

def encontrar_carpeta_entrenamiento() -> Path | None:
    """
    Devuelve la carpeta train* más reciente dentro de runs/detect/.
    Ultralytics guarda cada run en runs/detect/trainN/.
    """
    runs_root = PROJECT_ROOT / "runs" / "detect"
    if not runs_root.exists():
        return None

    carpetas = [p for p in runs_root.iterdir()
                if p.is_dir() and p.name.startswith("train")]
    if not carpetas:
        return None

    return max(carpetas, key=lambda p: p.stat().st_mtime)


def copiar_figura(origen: Path, destino: Path) -> bool:
    """Copia un archivo si existe. Retorna True si tuvo éxito."""
    if not origen.exists():
        return False
    shutil.copy2(origen, destino)
    return True


def formatear_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    elif n < 1024 ** 2:
        return f"{n/1024:.1f} KB"
    else:
        return f"{n/1024**2:.1f} MB"


def main():
    FIGURAS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print("EVAL-03 — Figuras del entrenamiento  (Sección 4.1.3)")
    print("=" * 65)

    carpeta = encontrar_carpeta_entrenamiento()
    if carpeta is None:
        print("\n[ERROR] No se encontró ninguna carpeta train* en runs/detect/")
        print("  Asegúrate de haber completado al menos un entrenamiento.")
        return

    print(f"\nCarpeta de entrenamiento : {carpeta.relative_to(PROJECT_ROOT)}")
    print(f"Destino de figuras       : {FIGURAS_DIR.relative_to(PROJECT_ROOT)}\n")

    copiadas   = []
    faltantes  = []
    opcionales = []

    # Figuras obligatorias
    for nombre_orig, nombre_dest in FIGURAS_OBJETIVO.items():
        origen  = carpeta / nombre_orig
        destino = FIGURAS_DIR / nombre_dest
        if copiar_figura(origen, destino):
            tam = destino.stat().st_size
            copiadas.append((nombre_orig, nombre_dest, tam))
        else:
            faltantes.append(nombre_orig)

    # Figuras opcionales
    for nombre_orig, nombre_dest in FIGURAS_OPCIONALES.items():
        origen  = carpeta / nombre_orig
        destino = FIGURAS_DIR / nombre_dest
        if copiar_figura(origen, destino):
            tam = destino.stat().st_size
            opcionales.append((nombre_orig, nombre_dest, tam))

    # -- Resumen en consola -----------------------------------------------------
    if copiadas:
        print("Figuras principales copiadas:")
        print(f"  {'Origen':<35} {'Destino':<40} {'Tamaño':>8}")
        print("  " + "-" * 85)
        for orig, dest, tam in copiadas:
            print(f"  {orig:<35} {dest:<40} {formatear_bytes(tam):>8}")

    if opcionales:
        print("\nFiguras opcionales copiadas:")
        for orig, dest, tam in opcionales:
            print(f"  {orig:<35} → {dest}  ({formatear_bytes(tam)})")

    if faltantes:
        print(f"\n[ADVERTENCIA] Las siguientes figuras no se encontraron en {carpeta.name}/:")
        for f in faltantes:
            print(f"  - {f}")
        print("  Es posible que el entrenamiento esté incompleto o use una")
        print("  versión de Ultralytics que genera nombres distintos.")

    total = len(copiadas) + len(opcionales)
    print(f"\nResumen: {total} figura(s) copiada(s) a evaluacion/figuras_cap4/")

    if not copiadas and not opcionales:
        print("\n[ATENCIÓN] No se copió ninguna figura.")
        print("  Para generar las figuras, completa el entrenamiento con train.py")
        print("  y vuelve a ejecutar este script.")


if __name__ == "__main__":
    main()

