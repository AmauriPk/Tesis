#!/usr/bin/env python3
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, OSError):
    pass
"""
eval_10_cumplimiento_rf.py — Tabla maestra de cumplimiento (Sección 4.4)
-------------------------------------------------------------------------
Lee los CSVs generados por eval_01 a eval_09 y consolida los veredictos
en dos tablas maestras: RF (Requisitos Funcionales) y RNF (No Funcionales).
NO toca el código de la aplicación SIRAN.

Uso:
    python eval_10_cumplimiento_rf.py

Salida:
    evaluacion/resultados/tabla_cumplimiento_RF.csv
    evaluacion/resultados/tabla_cumplimiento_RNF.csv
"""

import csv
from pathlib import Path

# -- Rutas ----------------------------------------------------------------------
SCRIPT_DIR     = Path(__file__).parent
EVAL_DIR       = SCRIPT_DIR.parent
PROJECT_ROOT   = EVAL_DIR.parent
RESULTADOS_DIR = EVAL_DIR / "resultados"

# -- Definición de RF (RF-01 a RF-11) ------------------------------------------
# Formato: (id, descripcion, criterio_legible, csv_fuente, fila_buscada, col_veredicto)
# csv_fuente=None → el RF no tiene script de medición directa
# fila_buscada: valor en la columna de identificación (None = primera fila con Veredicto)
TABLA_RF_DEF = [
    ("RF-01", "Detección de UAV en tiempo real",
     "FPS ≥ 25 y Latencia ≤ 100 ms",
     "rendimiento_live.csv",      "GLOBAL RNF-01",   "Veredicto"),

    ("RF-02", "Confirmación de alerta (umbral de confianza)",
     "Confianza promedio ≥ 0.60",
     "resultados_por_distancia.csv", None,            "Veredicto"),

    ("RF-03", "Detección a distintas distancias (10–100 m)",
     "Conf. promedio ≥ 0.60 en todas las distancias",
     "resultados_por_distancia.csv", None,            "Veredicto"),

    ("RF-04", "Operación en distintas condiciones de iluminación",
     "Recall ≥ 0.70 en todas las condiciones",
     "comparativa_iluminacion.csv", None,             "Veredicto"),

    ("RF-05", "Generación de alerta visual/sonora al detectar UAV",
     "Funcionalidad verificada manualmente",
     None, None, None),

    ("RF-06", "Registro de eventos de detección en base de datos",
     "detection_events se puebla durante operación",
     None, None, None),

    ("RF-07", "Visualización de video en tiempo real",
     "Stream MJPEG accesible en navegador",
     None, None, None),

    ("RF-08", "Panel de administración y configuración",
     "Acceso autenticado y funcional",
     None, None, None),

    ("RF-09", "Exportación de datos e historial de detecciones",
     "Descarga CSV/JSON disponible en la interfaz",
     None, None, None),

    ("RF-10", "Seguimiento automático PTZ (pan-tilt-zoom)",
     "TSE ≥ 0.80",
     "metricas_ptz.csv",          "TSE (Seg. Efectivo)",  "Veredicto"),

    ("RF-11", "Control manual de cámara PTZ",
     "Movimiento responde a comandos del operador",
     None, None, None),
]

# -- Definición de RNF (RNF-01 a RNF-10) ---------------------------------------
TABLA_RNF_DEF = [
    ("RNF-01", "Procesamiento en tiempo real",
     "FPS ≥ 25 y Latencia ≤ 100 ms",
     "rendimiento_live.csv",       "GLOBAL RNF-01",      "Veredicto"),

    ("RNF-02", "Precisión del modelo de detección",
     "Precision ≥ 0.85, Recall ≥ 0.70, mAP50 ≥ 0.80",
     "metricas_modelo.csv",        "GLOBAL RNF-02",      "Veredicto"),

    ("RNF-03", "Tasa de falsos positivos aceptable",
     "FP rate ≤ 5 %",
     "analisis_falsos_positivos.csv", "GLOBAL RNF-03",   "Veredicto"),

    ("RNF-04", "Robustez ante condiciones de iluminación",
     "Recall ≥ 0.70 en todas las condiciones",
     "comparativa_iluminacion.csv",  None,               "Veredicto"),

    ("RNF-05", "Alta disponibilidad del sistema",
     "Operación continua sin reinicio manual",
     None, None, None),

    ("RNF-06", "Tiempo de arranque rápido",
     "Sistema listo en < 60 s desde inicio",
     None, None, None),

    ("RNF-07", "Compatibilidad con cámaras IP y PTZ estándar (ONVIF/RTSP)",
     "Conexión exitosa con cámara del proyecto",
     None, None, None),

    ("RNF-08", "Estabilidad del seguimiento PTZ (jitter)",
     "Jitter ≤ 2.0 °",
     "metricas_ptz.csv",           "Jitter PTZ (°)",     "Veredicto"),

    ("RNF-09", "Tiempo de readquisición PTZ",
     "t_reacq promedio ≤ 3.0 s",
     "metricas_ptz.csv",           "t_reacq promedio (s)", "Veredicto"),

    ("RNF-10", "Seguridad de acceso al panel",
     "Autenticación requerida — acceso bloqueado sin login",
     None, None, None),
]

# -- Funciones ------------------------------------------------------------------

def leer_veredicto_csv(csv_nombre: str, fila_id: str | None,
                       col_id: str = "Metrica",
                       col_verd: str = "Veredicto") -> str:
    """
    Busca un veredicto en un CSV de resultados.

    Parámetros:
        csv_nombre : nombre del archivo en RESULTADOS_DIR
        fila_id    : valor en col_id que identifica la fila objetivo
                     (None = primera fila que tenga Veredicto no vacío)
        col_id     : columna de identificación (default "Metrica")
        col_verd   : columna que contiene el veredicto

    Retorna el veredicto como string o "— Pendiente de medición".
    """
    ruta = RESULTADOS_DIR / csv_nombre
    if not ruta.exists():
        return "— Pendiente de medición"

    try:
        with open(ruta, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            # Normalizar nombres de columnas
            filas = []
            for fila in reader:
                fila_norm = {k.strip(): v.strip() for k, v in fila.items()}
                filas.append(fila_norm)

        if not filas:
            return "— Sin datos"

        if fila_id is None:
            # Tomar la primera fila que tenga veredicto real
            for fila in filas:
                verd = fila.get(col_verd, "").strip()
                if verd and verd not in ("—", ""):
                    return verd
            return "— Sin datos"

        # Buscar por ID
        for fila in filas:
            if fila.get(col_id, "").strip() == fila_id:
                return fila.get(col_verd, "— Sin datos").strip()

        return f"— Fila '{fila_id}' no encontrada"

    except Exception as e:
        return f"— Error al leer: {e}"


def construir_tabla(definiciones: list, col_id_override: str = "Metrica") -> list[dict]:
    """
    Construye la tabla de cumplimiento leyendo los CSVs generados.

    Retorna lista de dicts con: ID, Descripcion, Criterio, Resultado, Veredicto
    """
    filas = []
    for id_req, desc, criterio, csv_nombre, fila_id, col_verd in definiciones:
        if csv_nombre is None:
            veredicto = "— Verificación manual"
            resultado = "—"
        else:
            veredicto = leer_veredicto_csv(
                csv_nombre,
                fila_id,
                col_id_override,
                col_verd or "Veredicto",
            )
            resultado = csv_nombre.replace(".csv", "")

        filas.append({
            "ID":          id_req,
            "Descripcion": desc,
            "Criterio":    criterio,
            "Resultado":   resultado,
            "Veredicto":   veredicto,
        })
    return filas


def contar_veredictos(tabla: list[dict]) -> tuple[int, int, int]:
    """Retorna (cumplidos, no_cumplidos, pendientes)."""
    cumplidos   = sum(1 for f in tabla if "✓" in f["Veredicto"])
    no_cumplidos = sum(1 for f in tabla if "✗" in f["Veredicto"])
    pendientes  = len(tabla) - cumplidos - no_cumplidos
    return cumplidos, no_cumplidos, pendientes


def imprimir_tabla(titulo: str, tabla: list[dict]):
    print(f"\n{'='*80}")
    print(f"  {titulo}")
    print(f"{'='*80}")
    print(f"{'ID':<8} {'Descripción':<42} {'Veredicto':>20}")
    print("-" * 72)
    for f in tabla:
        print(f"{f['ID']:<8} {f['Descripcion']:<42} {f['Veredicto']:>20}")
    print("-" * 72)
    c, n, p = contar_veredictos(tabla)
    print(f"  ✓ Cumplidos: {c}   ✗ No cumplidos: {n}   — Pendientes: {p}")


def guardar_csv(tabla: list[dict], nombre_archivo: str):
    salida = RESULTADOS_DIR / nombre_archivo
    campos = ["ID", "Descripcion", "Criterio", "Resultado", "Veredicto"]
    with open(salida, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=campos)
        writer.writeheader()
        writer.writerows(tabla)
    return salida


def main():
    RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("EVAL-10 — Tabla maestra de cumplimiento  (Sección 4.4)")
    print("=" * 80)
    print(f"\nLeyendo CSVs desde: {RESULTADOS_DIR.relative_to(PROJECT_ROOT)}")

    # Verificar qué CSVs están disponibles
    csvs_esperados = {
        "dataset_reporte.csv", "metricas_modelo.csv", "rendimiento_live.csv",
        "resultados_por_distancia.csv", "analisis_falsos_positivos.csv",
        "comparativa_iluminacion.csv", "metricas_ptz.csv",
    }
    presentes  = {f.name for f in RESULTADOS_DIR.glob("*.csv")}
    faltantes  = csvs_esperados - presentes
    if faltantes:
        print(f"\n[AVISO] CSVs aún no generados (se marcarán como Pendiente):")
        for f in sorted(faltantes):
            print(f"  - {f}")

    # -- Construir tablas -------------------------------------------------------
    tabla_rf  = construir_tabla(TABLA_RF_DEF)
    tabla_rnf = construir_tabla(TABLA_RNF_DEF)

    # -- Imprimir en consola ----------------------------------------------------
    imprimir_tabla("TABLA DE REQUISITOS FUNCIONALES (RF-01 a RF-11)", tabla_rf)
    imprimir_tabla("TABLA DE REQUISITOS NO FUNCIONALES (RNF-01 a RNF-10)", tabla_rnf)

    # -- Resumen global ---------------------------------------------------------
    total_rf  = len(tabla_rf)
    total_rnf = len(tabla_rnf)
    c_rf,  n_rf,  p_rf  = contar_veredictos(tabla_rf)
    c_rnf, n_rnf, p_rnf = contar_veredictos(tabla_rnf)

    print(f"\n{'='*80}")
    print(f"  RESUMEN GLOBAL DE CUMPLIMIENTO")
    print(f"{'-'*80}")
    print(f"  RF : {c_rf}/{total_rf} cumplidos  |  {n_rf} no cumplen  |  {p_rf} pendientes")
    print(f"  RNF: {c_rnf}/{total_rnf} cumplidos  |  {n_rnf} no cumplen  |  {p_rnf} pendientes")
    print(f"{'='*80}")

    # -- Guardar CSVs -----------------------------------------------------------
    salida_rf  = guardar_csv(tabla_rf,  "tabla_cumplimiento_RF.csv")
    salida_rnf = guardar_csv(tabla_rnf, "tabla_cumplimiento_RNF.csv")

    print(f"\n✓ Guardado: {salida_rf.relative_to(PROJECT_ROOT)}")
    print(f"✓ Guardado: {salida_rnf.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()

