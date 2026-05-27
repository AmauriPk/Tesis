#!/usr/bin/env python3
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, OSError):
    pass
"""
eval_09_ptz_tracking.py — TSE y readquisición PTZ (Sección 4.3.5)
------------------------------------------------------------------
Analiza el rendimiento del sistema de seguimiento PTZ leyendo el log
de SIRAN y las anotaciones manuales de pasadas_dron.csv.
NO toca el código de la aplicación SIRAN.

Métricas calculadas:
  - Tasa de Seguimiento Efectivo (TSE):  RF-10
      TSE = Σ tiempo_en_encuadre_s / Σ tiempo_total_s
      (datos de evaluacion/anotaciones/pasadas_dron.csv)

  - Tiempo de readquisición PTZ:         RNF-09
      t_reacq = timestamp "recuperado" − timestamp "pérdida"

  - Tasa de pérdidas sin recuperación    (informativo)

  - Jitter PTZ:                          RNF-08
      El log no registra ángulos directamente; este valor requiere
      medición con herramienta externa. El script deja un placeholder
      "Pendiente de medición" si no hay datos.

Líneas de log buscadas (case-insensitive):
  "PTZ readquisición iniciada"  → pérdida de objetivo
  "PTZ target recuperado"       → recuperación
  "PTZ readquisición agotada"   → pérdida sin recuperación

Uso:
    python eval_09_ptz_tracking.py

Salida:
    evaluacion/resultados/metricas_ptz.csv
"""

import csv
import re
from datetime import datetime
from pathlib import Path

# -- Rutas ----------------------------------------------------------------------
SCRIPT_DIR      = Path(__file__).parent
EVAL_DIR        = SCRIPT_DIR.parent
PROJECT_ROOT    = EVAL_DIR.parent
RESULTADOS_DIR  = EVAL_DIR / "resultados"
ANOTACIONES_DIR = EVAL_DIR / "anotaciones"

LOG_PATH        = PROJECT_ROOT / "logs" / "siran.log"
ARCHIVO_PASADAS = ANOTACIONES_DIR / "pasadas_dron.csv"

# -- Criterios de aceptación ----------------------------------------------------
CRITERIO_TSE_MIN        = 0.80   # RF-10:   TSE ≥ 0.80
CRITERIO_REACQ_MAX_S    = 3.0    # RNF-09:  t_reacq promedio ≤ 3.0 s
CRITERIO_JITTER_MAX_DEG = 2.0    # RNF-08:  jitter ≤ 2.0 °

# -- Patrones de log ------------------------------------------------------------
# Soporta formatos comunes de Python logging:
#   2024-01-15 10:30:45,123 - INFO - mensaje
#   [2024-01-15 10:30:45] INFO: mensaje
#   2024-01-15 10:30:45 INFO mensaje
TS_PATTERNS = [
    re.compile(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})[,.](\d+)?"),
    re.compile(r"\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]"),
]

LOG_PERDIDA      = re.compile(r"PTZ\s+readquisici[oó]n\s+iniciada", re.IGNORECASE)
LOG_RECUPERACION = re.compile(r"PTZ\s+target\s+recuperado",          re.IGNORECASE)
LOG_AGOTADA      = re.compile(r"PTZ\s+readquisici[oó]n\s+agotada",   re.IGNORECASE)

# -- Funciones ------------------------------------------------------------------

def extraer_timestamp(linea: str) -> datetime | None:
    """Extrae el primer timestamp encontrado en una línea de log."""
    for pat in TS_PATTERNS:
        m = pat.search(linea)
        if m:
            ts_str = m.group(1)
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                try:
                    return datetime.strptime(ts_str, fmt)
                except ValueError:
                    pass
    return None


def parsear_log(log_path: Path) -> dict:
    """
    Lee el log y extrae eventos PTZ.

    Retorna:
        tiempos_reacq  : list[float] — segundos entre pérdida y recuperación
        n_agotadas     : int         — pérdidas sin recuperación
        n_perdidas     : int         — total de pérdidas
    """
    tiempos_reacq = []
    n_agotadas    = 0
    n_perdidas    = 0
    ts_ultima_perdida: datetime | None = None

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            for linea in fh:
                ts = extraer_timestamp(linea)

                if LOG_PERDIDA.search(linea):
                    n_perdidas += 1
                    ts_ultima_perdida = ts

                elif LOG_RECUPERACION.search(linea):
                    if ts_ultima_perdida is not None and ts is not None:
                        delta = (ts - ts_ultima_perdida).total_seconds()
                        if 0 < delta <= 60:  # ignorar valores inverosímiles
                            tiempos_reacq.append(delta)
                    ts_ultima_perdida = None

                elif LOG_AGOTADA.search(linea):
                    n_agotadas += 1
                    ts_ultima_perdida = None

    except PermissionError:
        return {"error": f"Sin permiso para leer {log_path}"}

    return {
        "tiempos_reacq": tiempos_reacq,
        "n_agotadas":    n_agotadas,
        "n_perdidas":    n_perdidas,
    }


def calcular_tse_desde_anotaciones() -> float | None:
    """
    Calcula TSE = Σ tiempo_en_encuadre_s / Σ tiempo_total_s
    usando pasadas_dron.csv.
    Retorna None si el archivo no existe o no tiene datos completos.
    """
    if not ARCHIVO_PASADAS.exists():
        return None

    total_en_encuadre = 0.0
    total_vuelo       = 0.0

    with open(ARCHIVO_PASADAS, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for fila in reader:
            enc = fila.get("tiempo_en_encuadre_s", "").strip()
            tot = fila.get("tiempo_total_s", "").strip()
            if enc and tot:
                try:
                    total_en_encuadre += float(enc)
                    total_vuelo       += float(tot)
                except ValueError:
                    pass

    if total_vuelo <= 0:
        return None
    return total_en_encuadre / total_vuelo


def veredicto(valor, criterio, mayor_mejor: bool = True) -> str:
    if valor is None:
        return "— PENDIENTE"
    if mayor_mejor:
        return "✓ CUMPLE" if valor >= criterio else "✗ NO CUMPLE"
    else:
        return "✓ CUMPLE" if valor <= criterio else "✗ NO CUMPLE"


def main():
    RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print("EVAL-09 — Métricas PTZ  (Sección 4.3.5 / RF-10, RNF-08, RNF-09)")
    print("=" * 65)

    # -- TSE desde anotaciones --------------------------------------------------
    tse = calcular_tse_desde_anotaciones()
    if tse is None:
        if not ARCHIVO_PASADAS.exists():
            print(f"\n[INFO] No se encontró {ARCHIVO_PASADAS.name}")
            print("  Ejecuta eval_08_iluminacion.py para generar la plantilla")
            print("  y rellena 'tiempo_en_encuadre_s' y 'tiempo_total_s'.")
        else:
            print("\n[INFO] Las columnas tiempo_en_encuadre_s / tiempo_total_s")
            print(f"  están vacías en {ARCHIVO_PASADAS.name}")
            print("  Rellena esos valores para calcular TSE.")

    # -- Eventos PTZ desde el log -----------------------------------------------
    if not LOG_PATH.exists():
        print(f"\n[INFO] No se encontró el archivo de log: {LOG_PATH}")
        print("  El sistema debe haber registrado actividad PTZ en logs/siran.log.")
        resultado_log = {"tiempos_reacq": [], "n_agotadas": 0, "n_perdidas": 0}
    else:
        print(f"\nLog analizado: {LOG_PATH.relative_to(PROJECT_ROOT)}")
        resultado_log = parsear_log(LOG_PATH)
        if "error" in resultado_log:
            print(f"\n[ERROR] {resultado_log['error']}")
            return

    tiempos_reacq = resultado_log["tiempos_reacq"]
    n_agotadas    = resultado_log["n_agotadas"]
    n_perdidas    = resultado_log["n_perdidas"]

    # -- Cálculos de readquisición ----------------------------------------------
    reacq_promedio = sum(tiempos_reacq) / len(tiempos_reacq) if tiempos_reacq else None
    reacq_maximo   = max(tiempos_reacq) if tiempos_reacq else None
    reacq_p95      = None
    if tiempos_reacq:
        ordered = sorted(tiempos_reacq)
        idx = int(0.95 * len(ordered))
        reacq_p95 = ordered[min(idx, len(ordered)-1)]

    n_recuperados  = len(tiempos_reacq)
    tasa_reacq     = (n_recuperados / n_perdidas) if n_perdidas > 0 else None

    # -- Tabla de resultados ----------------------------------------------------
    metricas = [
        ("TSE (Seg. Efectivo)",       tse,            CRITERIO_TSE_MIN,     True,  "RF-10"),
        ("t_reacq promedio (s)",      reacq_promedio, CRITERIO_REACQ_MAX_S, False, "RNF-09"),
        ("t_reacq máximo (s)",        reacq_maximo,   None,                 False, "—"),
        ("t_reacq P95 (s)",           reacq_p95,      None,                 False, "—"),
        ("Jitter PTZ (°)",            None,           CRITERIO_JITTER_MAX_DEG, False, "RNF-08"),
        ("Pérdidas totales",          float(n_perdidas) if n_perdidas else None, None, True, "—"),
        ("Readquisiciones exitosas",  float(n_recuperados) if tiempos_reacq else None, None, True, "—"),
        ("Pérdidas sin recuperación", float(n_agotadas) if n_agotadas else None,  None, False, "—"),
        ("Tasa readquisición",        tasa_reacq,     None,                  True, "—"),
    ]

    filas_csv = []
    hdr = f"{'Métrica':<30} {'Criterio':>10} {'Resultado':>12} {'Req':>6} {'Veredicto':>14}"
    sep = "-" * 76
    print(f"\n{hdr}")
    print(sep)

    for nombre, valor, criterio_val, mayor_mejor, req in metricas:
        if criterio_val is not None:
            crit_str = (f"≥ {criterio_val}" if mayor_mejor
                        else f"≤ {criterio_val}")
        else:
            crit_str = "—"

        verd = veredicto(valor, criterio_val, mayor_mejor) if criterio_val is not None else "—"

        if valor is None:
            val_str = "— PENDIENTE"
        elif isinstance(valor, float) and valor == int(valor):
            val_str = f"{int(valor)}"
        else:
            val_str = f"{valor:.4f}" if valor is not None else "—"

        print(f"{nombre:<30} {crit_str:>10} {val_str:>12} {req:>6} {verd:>14}")
        filas_csv.append({
            "Metrica":   nombre,
            "Criterio":  crit_str,
            "Resultado": val_str,
            "Requisito": req,
            "Veredicto": verd,
        })

    # Notas sobre jitter
    print(sep)
    print("\n[NOTA] Jitter PTZ requiere medición con herramienta externa")
    print("  (p.ej. visión por computadora sobre el video grabado).")
    print("  Registra el valor manualmente en metricas_ptz.csv una vez medido.")

    # Veredictos globales
    tse_ok   = tse is not None and tse >= CRITERIO_TSE_MIN
    reacq_ok = reacq_promedio is not None and reacq_promedio <= CRITERIO_REACQ_MAX_S

    print(f"\nVEREDICTO RF-10  (TSE)    : {'✓ CUMPLE' if tse_ok else ('✗ NO CUMPLE' if tse is not None else '— PENDIENTE')}")
    print(f"VEREDICTO RNF-09 (t_reacq): {'✓ CUMPLE' if reacq_ok else ('✗ NO CUMPLE' if reacq_promedio is not None else '— PENDIENTE')}")
    print(f"VEREDICTO RNF-08 (jitter) : — PENDIENTE (medición manual)")

    # -- Guardar CSV ------------------------------------------------------------
    salida = RESULTADOS_DIR / "metricas_ptz.csv"
    campos = ["Metrica", "Criterio", "Resultado", "Requisito", "Veredicto"]
    with open(salida, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=campos)
        writer.writeheader()
        writer.writerows(filas_csv)

    print(f"\n✓ Reporte guardado en: {salida.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()

