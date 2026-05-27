#!/usr/bin/env python3
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, OSError):
    pass
"""
eval_11_reporte_final.py — Reporte HTML del Capítulo IV (Sección completa)
---------------------------------------------------------------------------
Lee todos los CSVs de evaluacion/resultados/ y genera un reporte HTML
autocontenido con todas las tablas del Capítulo IV.
Abrir en cualquier navegador para copiar tablas a Word.
NO toca el código de la aplicación SIRAN.

Uso:
    python eval_11_reporte_final.py

Salida:
    evaluacion/reporte_capitulo4.html
"""

import csv
from datetime import datetime
from pathlib import Path

# -- Rutas ----------------------------------------------------------------------
SCRIPT_DIR     = Path(__file__).parent
EVAL_DIR       = SCRIPT_DIR.parent
PROJECT_ROOT   = EVAL_DIR.parent
RESULTADOS_DIR = EVAL_DIR / "resultados"
FIGURAS_DIR    = EVAL_DIR / "figuras_cap4"
SALIDA_HTML    = EVAL_DIR / "reporte_capitulo4.html"

# -- Funciones de lectura -------------------------------------------------------

def leer_csv(nombre: str) -> tuple[list[str], list[dict]]:
    """Lee un CSV y retorna (campos, filas). Retorna listas vacías si no existe."""
    ruta = RESULTADOS_DIR / nombre
    if not ruta.exists():
        return [], []
    try:
        with open(ruta, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            campos = reader.fieldnames or []
            filas  = [dict(row) for row in reader]
        return list(campos), filas
    except Exception:
        return [], []


def listar_figuras() -> list[tuple[str, str]]:
    """Retorna lista de (ruta_relativa_al_html, nombre_figura)."""
    if not FIGURAS_DIR.exists():
        return []
    figuras = []
    for ext in ("*.png", "*.jpg", "*.jpeg"):
        for fig in sorted(FIGURAS_DIR.glob(ext)):
            # Ruta relativa desde evaluacion/ (donde está el HTML)
            relativa = f"figuras_cap4/{fig.name}"
            figuras.append((relativa, fig.stem.replace("_", " ").title()))
    return figuras


# -- Funciones HTML -------------------------------------------------------------

def cls_veredicto(texto: str) -> str:
    """Devuelve la clase CSS según el veredicto."""
    if texto is None:
        return ""
    t = texto.strip()
    if "✓" in t:
        return "cumple"
    if "✗" in t:
        return "no-cumple"
    if "—" in t or "Pendiente" in t or "pendiente" in t or "PENDIENTE" in t:
        return "pendiente"
    return ""


def tabla_html(campos: list[str], filas: list[dict],
               col_veredicto: str = "Veredicto") -> str:
    """Genera una tabla HTML a partir de campos y filas."""
    if not campos or not filas:
        return "<p class='sin-datos'>Sin datos — ejecuta el script correspondiente.</p>"

    html = ["<table>", "<thead><tr>"]
    for c in campos:
        html.append(f"<th>{c}</th>")
    html.append("</tr></thead>", )
    html.append("<tbody>")

    for fila in filas:
        verd_raw = fila.get(col_veredicto, "")
        css_fila = cls_veredicto(verd_raw)
        html.append(f'<tr class="{css_fila}">')
        for c in campos:
            val = fila.get(c, "")
            css_celda = cls_veredicto(val) if c == col_veredicto else ""
            html.append(f'<td class="{css_celda}">{val}</td>')
        html.append("</tr>")

    html.append("</tbody></table>")
    return "\n".join(html)


def seccion(id_sec: str, titulo: str, numero: str, contenido: str) -> str:
    return f"""
<section id="{id_sec}">
  <h2>{numero} {titulo}</h2>
  {contenido}
</section>"""


def subseccion(id_sec: str, titulo: str, numero: str, contenido: str) -> str:
    return f"""
<div id="{id_sec}" class="subseccion">
  <h3>{numero} {titulo}</h3>
  {contenido}
</div>"""


# -- CSS integrado --------------------------------------------------------------
CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    font-size: 13px; color: #1a1a1a; background: #f5f5f5;
    padding: 20px;
}
.contenedor { max-width: 1100px; margin: auto; background: #fff;
              padding: 40px; border: 1px solid #ddd; }
h1 { font-size: 20px; color: #003366; border-bottom: 2px solid #003366;
     padding-bottom: 10px; margin-bottom: 6px; }
.subtitulo { font-size: 13px; color: #555; margin-bottom: 24px; }
h2 { font-size: 16px; color: #003366; margin: 32px 0 12px;
     border-left: 4px solid #0055a5; padding-left: 10px; }
h3 { font-size: 14px; color: #0055a5; margin: 20px 0 8px; }
.subseccion { margin-left: 16px; }
nav { background: #003366; padding: 12px 16px; margin-bottom: 28px;
      border-radius: 4px; }
nav a { color: #cce0ff; text-decoration: none; margin-right: 16px;
        font-size: 12px; }
nav a:hover { color: #fff; text-decoration: underline; }
table { width: 100%; border-collapse: collapse; margin: 10px 0 20px;
        font-size: 12px; }
thead tr { background: #003366; color: #fff; }
th { padding: 7px 10px; text-align: left; font-weight: 600; }
td { padding: 6px 10px; border-bottom: 1px solid #e0e0e0; }
tbody tr:nth-child(even) { background: #f9f9f9; }
tbody tr:hover { background: #eef3ff; }
tr.cumple td { }
tr.no-cumple td { }
td.cumple    { color: #1a7a1a; font-weight: bold; }
td.no-cumple { color: #b30000; font-weight: bold; }
td.pendiente { color: #7a6000; }
.sin-datos { color: #888; font-style: italic; padding: 10px 0; }
.figuras-grid { display: flex; flex-wrap: wrap; gap: 16px; margin: 16px 0; }
.figura-item { text-align: center; }
.figura-item img { max-width: 340px; max-height: 260px; border: 1px solid #ccc;
                   border-radius: 3px; }
.figura-item p { font-size: 11px; color: #555; margin-top: 4px; }
.resumen-badge { display: inline-block; padding: 4px 10px; border-radius: 12px;
                 font-weight: bold; font-size: 12px; margin: 4px 4px 12px 0; }
.badge-cumple    { background: #d4edda; color: #1a7a1a; border: 1px solid #a8d5b5; }
.badge-nocumple  { background: #f8d7da; color: #b30000; border: 1px solid #f0a8af; }
.badge-pendiente { background: #fff3cd; color: #7a6000; border: 1px solid #ffe08a; }
footer { margin-top: 40px; font-size: 11px; color: #888;
         border-top: 1px solid #ddd; padding-top: 10px; }
@media print {
    nav { display: none; }
    body { background: #fff; padding: 0; }
    .contenedor { border: none; padding: 10px; }
}
"""


def generar_html() -> str:
    """Genera el HTML completo del Capítulo IV."""
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # -- Leer todos los CSVs ----------------------------------------------------
    c01, f01 = leer_csv("dataset_reporte.csv")
    c02, f02 = leer_csv("metricas_modelo.csv")
    c04, f04 = leer_csv("rendimiento_live.csv")
    c06, f06 = leer_csv("resultados_por_distancia.csv")
    c07, f07 = leer_csv("analisis_falsos_positivos.csv")
    c08, f08 = leer_csv("comparativa_iluminacion.csv")
    c09, f09 = leer_csv("metricas_ptz.csv")
    c10r, f10r = leer_csv("tabla_cumplimiento_RF.csv")
    c10n, f10n = leer_csv("tabla_cumplimiento_RNF.csv")
    figuras = listar_figuras()

    # -- Badges de resumen ------------------------------------------------------
    def badges(filas, col="Veredicto"):
        c = sum(1 for f in filas if "✓" in f.get(col, ""))
        n = sum(1 for f in filas if "✗" in f.get(col, ""))
        p = len(filas) - c - n
        badges_html = ""
        if c: badges_html += f'<span class="resumen-badge badge-cumple">✓ {c} Cumple</span>'
        if n: badges_html += f'<span class="resumen-badge badge-nocumple">✗ {n} No cumple</span>'
        if p: badges_html += f'<span class="resumen-badge badge-pendiente">— {p} Pendiente</span>'
        return badges_html or '<span class="resumen-badge badge-pendiente">Sin datos</span>'

    # -- Figuras HTML -----------------------------------------------------------
    figuras_html = ""
    if figuras:
        items = ""
        for ruta, nombre in figuras:
            items += (f'<div class="figura-item">'
                      f'<img src="{ruta}" alt="{nombre}" />'
                      f'<p>{nombre}</p></div>\n')
        figuras_html = f'<div class="figuras-grid">{items}</div>'
    else:
        figuras_html = "<p class='sin-datos'>Sin figuras — ejecuta eval_03_curvas.py.</p>"

    # -- Navegación -------------------------------------------------------------
    nav_links = [
        ("#sec-41", "4.1 Modelo"),
        ("#sec-411", "4.1.1 Dataset"),
        ("#sec-412", "4.1.2 Métricas"),
        ("#sec-413", "4.1.3 Curvas"),
        ("#sec-42", "4.2 Rendimiento"),
        ("#sec-43", "4.3 Pruebas"),
        ("#sec-431", "4.3.1 Distancia"),
        ("#sec-433", "4.3.3 FP"),
        ("#sec-434", "4.3.4 Iluminación"),
        ("#sec-435", "4.3.5 PTZ"),
        ("#sec-44", "4.4 Cumplimiento"),
    ]
    nav_html = "".join(f'<a href="{href}">{txt}</a>' for href, txt in nav_links)

    # -- Contenido del reporte --------------------------------------------------
    contenido = f"""
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Capítulo IV — Evaluación del Sistema SIRAN</title>
<style>{CSS}</style>
</head>
<body>
<div class="contenedor">

<h1>CAPÍTULO IV — Evaluación del Sistema SIRAN</h1>
<p class="subtitulo">
  Sistema de Identificación y Rastreo de Aeronaves No Tripuladas (SIRAN)<br>
  Reporte generado: {ahora}
</p>

<nav>{nav_html}</nav>

<!-- ======================================================================= -->
{seccion("sec-41", "Validación del Modelo de Detección", "4.1",
    subseccion("sec-411", "Composición del dataset", "4.1.1",
        "<p>Distribución de imágenes por split del dataset de entrenamiento.</p>"
        + tabla_html(c01, f01, "Porcentaje_real"))
    + subseccion("sec-412", "Métricas del modelo (RNF-02)", "4.1.2",
        "<p>Resultados de la última época de entrenamiento vs. criterios de aceptación.</p>"
        + badges(f02)
        + tabla_html(c02, f02))
    + subseccion("sec-413", "Curvas de entrenamiento", "4.1.3",
        "<p>Figuras generadas por Ultralytics durante el entrenamiento.</p>"
        + figuras_html)
)}

<!-- ======================================================================= -->
{seccion("sec-42", "Rendimiento del Sistema en Tiempo Real", "4.2",
    subseccion("sec-421", "FPS y latencia de inferencia (RNF-01)", "4.2.1",
        "<p>Métricas de rendimiento medidas sobre inference_frames de la base de datos.</p>"
        + badges(f04)
        + tabla_html(c04, f04))
)}

<!-- ======================================================================= -->
{seccion("sec-43", "Pruebas Experimentales en Campo", "4.3",
    subseccion("sec-431", "Desempeño por distancia de detección (RF-03)", "4.3.1",
        "<p>Confianza, tasa de detección y FPS agrupados por distancia de vuelo.</p>"
        + badges(f06)
        + tabla_html(c06, f06))
    + subseccion("sec-433", "Tasa de falsos positivos con distractores (RNF-03)", "4.3.3",
        "<p>Análisis de alertas falsas generadas ante objetos que no son UAV.</p>"
        + badges(f07)
        + tabla_html(c07, f07))
    + subseccion("sec-434", "Comparativa por condición de iluminación (RNF-04)", "4.3.4",
        "<p>Recall y confianza bajo distintas condiciones lumínicas.</p>"
        + badges(f08)
        + tabla_html(c08, f08, "Veredicto"))
    + subseccion("sec-435", "Métricas del seguimiento PTZ (RF-10, RNF-08, RNF-09)", "4.3.5",
        "<p>TSE, tiempos de readquisición y jitter del sistema pan-tilt-zoom.</p>"
        + badges(f09)
        + tabla_html(c09, f09))
)}

<!-- ======================================================================= -->
{seccion("sec-44", "Análisis de Cumplimiento de Requerimientos", "4.4",
    subseccion("sec-441", "Requisitos Funcionales (RF-01 a RF-11)", "4.4.1",
        badges(f10r)
        + tabla_html(c10r, f10r))
    + subseccion("sec-442", "Requisitos No Funcionales (RNF-01 a RNF-10)", "4.4.2",
        badges(f10n)
        + tabla_html(c10n, f10n))
)}

<footer>
  Reporte generado automáticamente por eval_11_reporte_final.py — EVAL-SUITE SIRAN &nbsp;|&nbsp;
  Fecha: {ahora} &nbsp;|&nbsp;
  Para copiar tablas a Word: abre este archivo en Chrome/Edge → selecciona la tabla → Ctrl+C → pegar en Word.
</footer>

</div>
</body>
</html>"""

    return contenido


def main():
    print("=" * 65)
    print("EVAL-11 — Reporte HTML del Capítulo IV")
    print("=" * 65)

    # Verificar qué CSVs están disponibles
    todos = [
        "dataset_reporte.csv", "metricas_modelo.csv", "rendimiento_live.csv",
        "resultados_por_distancia.csv", "analisis_falsos_positivos.csv",
        "comparativa_iluminacion.csv", "metricas_ptz.csv",
        "tabla_cumplimiento_RF.csv", "tabla_cumplimiento_RNF.csv",
    ]
    presentes = [f for f in todos if (RESULTADOS_DIR / f).exists()]
    faltantes = [f for f in todos if f not in presentes]

    print(f"\n  CSVs encontrados : {len(presentes)}/{len(todos)}")
    if faltantes:
        print(f"  Sin datos aún    : {', '.join(faltantes)}")
        print("  (Se incluirán como 'Sin datos' en el reporte)")

    figuras = listar_figuras()
    print(f"  Figuras cap4     : {len(figuras)}")

    # Generar HTML
    html = generar_html()

    with open(SALIDA_HTML, "w", encoding="utf-8") as fh:
        fh.write(html)

    tam_kb = SALIDA_HTML.stat().st_size / 1024
    print(f"\n✓ Reporte generado: {SALIDA_HTML.relative_to(PROJECT_ROOT)}")
    print(f"  Tamaño: {tam_kb:.1f} KB")
    print(f"\n  Abre el archivo en tu navegador para visualizarlo.")
    print(f"  Para copiar una tabla a Word: selecciona la tabla en el navegador")
    print(f"  → Ctrl+C → pegar en Word (mantiene el formato de tabla).")


if __name__ == "__main__":
    main()

