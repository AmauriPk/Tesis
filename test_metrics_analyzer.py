"""
test_metrics_analyzer.py
=======================
Módulo de Pruebas y Análisis de Métricas para el prototipo de detección de RPAS Micro.

Objetivo (Capítulo 4: Resultados):
- Procesar registros (SQLite/JSON) del sistema y producir métricas y gráficas listas para tesis.

Contexto de investigación (respetado):
- Detección RPAS Micro con YOLO26 en GPU (sin NMS).
- Métricas: Precision, Recall, mAP y FPS.
- Logs típicos: fecha/hora, clase, confianza, bbox (xyxy) y tiempo de inferencia por cuadro (cuando exista).
- Pruebas PTZ: evaluar tasa de seguimiento exitoso (objeto en 30% central de la imagen).

Notas importantes de QA/Metodología:
- Sin "ground truth" (anotaciones por frame) NO es posible calcular métricas clásicas
  (Precision/Recall/mAP) de forma estricta. Este script:
  1) Calcula métricas EXACTAS derivables directamente del log (confianza, latencia, FPS).
  2) Ofrece un modo "proxy" determinista (heurístico) para un reporte preliminar de FP/FN/mAP.
  3) Permite extender a evaluación estricta si se aporta ground truth compatible.

Uso rápido:
  python test_metrics_analyzer.py --sqlite detections.db --out chapter4_out

Salida:
- `metrics_summary.json`: resumen numérico para el Capítulo 4.
- Figuras `.png` en `figures/` (FPS, dispersión de bbox, matriz de confusión proxy/real).

Dependencias sugeridas:
- pandas, numpy, matplotlib, seaborn, pytest (para tests rápidos al final del archivo).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

# Reglas puras del backend (testeables sin importar Flask).
from backend_rules import assert_ptz_capable, select_priority_detection, should_allow_ptz_move


LogSourceType = Literal["sqlite", "json", "jsonl"]


@dataclass(frozen=True, slots=True)
class AnalyzerConfig:
    """
    Parámetros del análisis. Se mantienen explícitos para reproducibilidad (tesis).
    """

    confidence_threshold: float = 0.50
    tolerance_ratio: float = 0.30  # 30% central
    frame_width: int = 1920
    frame_height: int = 1080
    expected_fps: float | None = None  # opcional: para estimaciones proxy


_FILENAME_TS_RE = re.compile(
    r"detection_(?P<ymd>\d{8})_(?P<hms>\d{6})_(?P<micro>\d+?)_(?P<conf>\d+(?:\.\d+)?)\.(?:jpg|jpeg|png)$",
    re.IGNORECASE,
)


def _safe_float(v: Any) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def _safe_int(v: Any) -> int | None:
    try:
        if v is None:
            return None
        return int(v)
    except Exception:
        return None


def _parse_ts_from_fecha_hora(fecha: Any, hora: Any) -> datetime | None:
    """
    Convierte columnas `fecha` + `hora` a datetime. En el prototipo actual:
    - fecha: "YYYY-MM-DD"
    - hora:  "HH:MM:SS"
    """

    if not fecha or not hora:
        return None
    text = f"{str(fecha).strip()} {str(hora).strip()}"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue
    return None


def _parse_ts_from_image_path(image_path: Any) -> datetime | None:
    """
    Intenta extraer timestamp de alta resolución desde el nombre de archivo:
      detection_YYYYmmdd_HHMMSS_micro_conf.jpg
    """

    if not image_path:
        return None
    name = Path(str(image_path)).name
    m = _FILENAME_TS_RE.match(name)
    if not m:
        return None
    ymd = m.group("ymd")
    hms = m.group("hms")
    micro_raw = m.group("micro")
    # Normaliza microsegundos a 6 dígitos (Python datetime usa microseconds).
    micro = int(micro_raw[:6].ljust(6, "0"))
    dt = datetime.strptime(f"{ymd} {hms}", "%Y%m%d %H%M%S")
    return dt.replace(microsecond=micro)


def _coalesce_timestamp(row: pd.Series) -> datetime | None:
    """
    Define un timestamp por fila:
    1) timestamp explícito (si existe).
    2) fecha + hora.
    3) timestamp parseado del image_path.
    """

    ts = row.get("timestamp", None)
    if ts is not None and ts != "":
        # Acepta strings ISO (o datetime).
        if isinstance(ts, datetime):
            return ts
        try:
            return pd.to_datetime(ts).to_pydatetime()
        except Exception:
            pass

    ts2 = _parse_ts_from_fecha_hora(row.get("fecha", None), row.get("hora", None))
    if ts2 is not None:
        # Si además existe image_path con microsegundos, lo usamos para ordenar mejor.
        hi = _parse_ts_from_image_path(row.get("image_path", None))
        return hi or ts2

    return _parse_ts_from_image_path(row.get("image_path", None))


def cargar_logs_deteccion(
    *,
    sqlite_path: str | None = None,
    sqlite_table: str = "auto",
    json_path: str | None = None,
) -> pd.DataFrame:
    """
    Carga logs del sistema en un DataFrame normalizado.

    Fuentes soportadas:
    - SQLite: tabla `detections` (como `detections.db` en este repo).
    - JSON/JSONL: lista de dicts o JSON Lines (1 dict por línea).

    Columnas normalizadas (cuando existan):
    - timestamp (datetime)
    - class_name (str)
    - confidence (float)
    - x1,y1,x2,y2 (int)
    - inference_ms (float)  (si el log lo incluye)
    - frame_w, frame_h (int) (si el log lo incluye)
    - source (str)
    - image_path (str)
    """

    frames: list[pd.DataFrame] = []

    if sqlite_path:
        con = sqlite3.connect(str(sqlite_path))
        try:
            table = sqlite_table
            if table.strip().lower() == "auto":
                rows = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                names = {r[0] for r in rows}
                table = "detections_v2" if "detections_v2" in names else "detections"

            df = pd.read_sql_query(f"SELECT * FROM {table}", con)
        finally:
            con.close()

        # Mapeo específico del prototipo: confianza/fuente/bbox.
        rename_map = {
            "confianza": "confidence",
            "fuente": "source",
            "class_name": "class_name",
        }
        df = df.rename(columns=rename_map)

        # Asegura columnas estándar de bbox.
        for col in ("x1", "y1", "x2", "y2"):
            if col not in df.columns:
                df[col] = None

        # Clase: si no existe, se asume 1-clase (RPAS Micro).
        if "class_name" not in df.columns:
            df["class_name"] = "RPAS Micro"

        # Timestamp en v2 ya viene como `timestamp`.
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

        frames.append(df)

    if json_path:
        path = Path(json_path)
        if not path.exists():
            raise FileNotFoundError(f"No existe: {path}")

        raw_text = path.read_text(encoding="utf-8", errors="replace").strip()
        items: list[dict[str, Any]] = []
        if not raw_text:
            items = []
        elif raw_text[0] == "[":
            items = json.loads(raw_text)
        else:
            # JSONL: 1 dict por línea
            for line in raw_text.splitlines():
                line = line.strip()
                if not line:
                    continue
                items.append(json.loads(line))

        df = pd.DataFrame(items)

        # Normaliza claves frecuentes.
        key_map = {
            "cls": "class_name",
            "class": "class_name",
            "conf": "confidence",
            "confidence": "confidence",
            "inference_time_ms": "inference_ms",
            "latency_ms": "inference_ms",
            "frame_width": "frame_w",
            "frame_height": "frame_h",
        }
        df = df.rename(columns={k: v for k, v in key_map.items() if k in df.columns})

        # bbox puede venir como [x1,y1,x2,y2]
        if "bbox" in df.columns and not {"x1", "y1", "x2", "y2"}.issubset(df.columns):
            bbox = df["bbox"].apply(lambda v: v if isinstance(v, (list, tuple)) and len(v) == 4 else [None] * 4)
            df[["x1", "y1", "x2", "y2"]] = pd.DataFrame(bbox.tolist(), index=df.index)

        frames.append(df)

    if not frames:
        raise ValueError("Debes indicar `sqlite_path` y/o `json_path`.")

    df_all = pd.concat(frames, ignore_index=True, sort=False)

    # Normalización final de tipos.
    df_all["confidence"] = df_all.get("confidence", pd.Series([None] * len(df_all))).apply(_safe_float)
    for col in ("x1", "y1", "x2", "y2"):
        df_all[col] = df_all.get(col, pd.Series([None] * len(df_all))).apply(_safe_int)

    if "class_name" not in df_all.columns:
        df_all["class_name"] = "RPAS Micro"

    # Crea timestamp final.
    df_all["timestamp"] = df_all.apply(_coalesce_timestamp, axis=1)
    df_all = df_all.dropna(subset=["timestamp"]).copy()
    df_all["timestamp"] = pd.to_datetime(df_all["timestamp"])
    df_all = df_all.sort_values("timestamp").reset_index(drop=True)

    return df_all


def cargar_logs_inferencia(
    *,
    sqlite_path: str,
    sqlite_table: str = "inference_frames",
) -> pd.DataFrame:
    """
    Carga telemetría por frame (latencia/FPS real).

    Requiere que exista la tabla `inference_frames` creada por el backend.
    """

    con = sqlite3.connect(str(sqlite_path))
    try:
        df = pd.read_sql_query(f"SELECT * FROM {sqlite_table}", con)
    finally:
        con.close()

    if "timestamp" not in df.columns:
        raise ValueError(f"Tabla {sqlite_table} no contiene `timestamp`.")
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df


def _fps_series_from_logs(df: pd.DataFrame) -> pd.Series:
    """
    Genera una serie de FPS por evento:
    - Si hay `inference_ms`: FPS = 1000 / inference_ms
    - Si no: FPS aproximado = 1 / delta_t (entre timestamps consecutivos)
    """

    if "inference_ms" in df.columns and df["inference_ms"].notna().any():
        ms = pd.to_numeric(df["inference_ms"], errors="coerce")
        fps = 1000.0 / ms
        return fps.replace([np.inf, -np.inf], np.nan)

    ts = pd.to_datetime(df["timestamp"])
    dt = ts.diff().dt.total_seconds()
    fps = 1.0 / dt
    return fps.replace([np.inf, -np.inf], np.nan)


def _proxy_precision_recall_ap(df: pd.DataFrame, *, thresholds: np.ndarray) -> dict[str, Any]:
    """
    Reporte PROXY determinista de Precision/Recall/AP (mAP en 1 clase).

    Importante:
    - Esto NO sustituye evaluación con ground truth.
    - Sirve para un reporte preliminar cuando sólo existe el log de detecciones.
    """

    conf = pd.to_numeric(df["confidence"], errors="coerce").fillna(0.0).to_numpy()

    # Positivos proxy: "hubo señal" si confianza supera umbral muy bajo.
    positives_proxy = int(np.sum(conf >= 0.05))
    positives_proxy = max(positives_proxy, 1)  # evita división por cero

    precisions: list[float] = []
    recalls: list[float] = []
    for t in thresholds:
        tp = int(np.sum(conf >= float(t)))
        fp = int(np.sum(conf < float(t)))
        fn = max(0, positives_proxy - tp)

        precision = tp / max(1, tp + fp)
        recall = tp / max(1, tp + fn)
        precisions.append(float(precision))
        recalls.append(float(recall))

    # AP por área bajo la curva P-R (trapezoidal).
    order = np.argsort(recalls)
    r = np.array(recalls)[order]
    p = np.array(precisions)[order]
    # Numpy 2.x deprecó/removió `trapz`; preferimos `trapezoid`.
    try:
        ap = float(np.trapezoid(p, r))  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover
        ap = float(np.trapz(p, r))  # type: ignore[attr-defined]

    return {
        "mode": "proxy",
        "positives_proxy": positives_proxy,
        "thresholds": thresholds.tolist(),
        "precision_curve": precisions,
        "recall_curve": recalls,
        "ap": ap,
        "map": ap,  # 1 clase => mAP = AP
    }


def calcular_rendimiento_ia(
    df: pd.DataFrame,
    *,
    confidence_threshold: float = 0.50,
    expected_fps: float | None = None,
    frames_df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """
    Lee logs de detección y calcula:
    - Promedio de confianza (exacto desde logs).
    - Latencia promedio y FPS real (exacto si existe inference_ms; si no, FPS estimado por delta_t).
    - Reporte proxy determinista de FP/FN y mAP (cuando no existe ground truth).
    """

    if df.empty:
        raise ValueError("DataFrame vacío: no hay logs para analizar.")

    conf = pd.to_numeric(df["confidence"], errors="coerce")
    conf_mean = float(conf.mean(skipna=True)) if conf.notna().any() else float("nan")
    conf_median = float(conf.median(skipna=True)) if conf.notna().any() else float("nan")

    # FPS/latencia: preferimos telemetría por frame si existe.
    fps_series: pd.Series
    if frames_df is not None and not frames_df.empty and "inference_ms" in frames_df.columns:
        ms = pd.to_numeric(frames_df["inference_ms"], errors="coerce")
        fps_series = (1000.0 / ms).replace([np.inf, -np.inf], np.nan)
    else:
        fps_series = _fps_series_from_logs(df)
    fps_real_mean = float(fps_series.mean(skipna=True)) if fps_series.notna().any() else float("nan")
    fps_real_median = float(fps_series.median(skipna=True)) if fps_series.notna().any() else float("nan")

    latency_ms_mean = float("nan")
    latency_ms_median = float("nan")
    if frames_df is not None and not frames_df.empty and "inference_ms" in frames_df.columns and frames_df["inference_ms"].notna().any():
        ms = pd.to_numeric(frames_df["inference_ms"], errors="coerce")
        latency_ms_mean = float(ms.mean(skipna=True))
        latency_ms_median = float(ms.median(skipna=True))
    else:
        # Si no existe inference_ms, convertimos FPS estimado a latencia aproximada.
        if fps_real_mean and not math.isnan(fps_real_mean) and fps_real_mean > 0:
            latency_ms_mean = float(1000.0 / fps_real_mean)
        if fps_real_median and not math.isnan(fps_real_median) and fps_real_median > 0:
            latency_ms_median = float(1000.0 / fps_real_median)

    # Proxy FP/FN por umbral de confianza (determinista).
    conf_filled = conf.fillna(0.0)
    tp_proxy = int((conf_filled >= confidence_threshold).sum())
    fp_proxy = int((conf_filled < confidence_threshold).sum())

    # FN proxy: si el usuario provee expected_fps, se estima cuántos eventos "faltaron".
    fn_proxy = 0
    if expected_fps and expected_fps > 0:
        t0 = pd.to_datetime(df["timestamp"]).min()
        t1 = pd.to_datetime(df["timestamp"]).max()
        duration_s = max(0.0, (t1 - t0).total_seconds())
        expected_events = int(round(duration_s * float(expected_fps)))
        fn_proxy = max(0, expected_events - len(df))

    precision_proxy = tp_proxy / max(1, (tp_proxy + fp_proxy))
    recall_proxy = tp_proxy / max(1, (tp_proxy + fn_proxy))

    pr_curve = _proxy_precision_recall_ap(df, thresholds=np.linspace(0.05, 0.95, 19))

    return {
        "confidence_threshold": float(confidence_threshold),
        "n_events": int(len(df)),
        "confidence": {
            "mean": conf_mean,
            "median": conf_median,
            "min": float(conf.min(skipna=True)) if conf.notna().any() else float("nan"),
            "max": float(conf.max(skipna=True)) if conf.notna().any() else float("nan"),
        },
        "latency_ms": {
            "mean": latency_ms_mean,
            "median": latency_ms_median,
            "source": "inference_ms" if (frames_df is not None and "inference_ms" in frames_df.columns and frames_df["inference_ms"].notna().any()) else "timestamp_delta",
        },
        "fps": {
            "mean": fps_real_mean,
            "median": fps_real_median,
            "source": "inference_ms" if (frames_df is not None and "inference_ms" in frames_df.columns and frames_df["inference_ms"].notna().any()) else "timestamp_delta",
        },
        "proxy_classic_metrics": {
            "mode": "proxy",
            "tp": tp_proxy,
            "fp": fp_proxy,
            "fn": fn_proxy,
            "precision": float(precision_proxy),
            "recall": float(recall_proxy),
            "map": float(pr_curve["map"]),
        },
        "proxy_pr_curve": pr_curve,
    }


def evaluar_tracking_ptz(
    df: pd.DataFrame,
    *,
    frame_width: int,
    frame_height: int,
    tolerance_ratio: float = 0.30,
) -> dict[str, Any]:
    """
    Evalúa seguimiento PTZ: % de tiempo/eventos donde el dron estuvo dentro del 30% central.

    Interpretación de "30% central":
    - Una ventana centrada que ocupa 30% del ancho y 30% del alto.
    - Por tanto, el centro del bbox debe caer dentro de:
      x in [0.5w - 0.15w, 0.5w + 0.15w]
      y in [0.5h - 0.15h, 0.5h + 0.15h]

    Retorna:
    - success_rate_event: porcentaje por conteo de eventos.
    - success_rate_time:  porcentaje ponderado por delta_t (si hay timestamps suficientes).
    """

    if df.empty:
        raise ValueError("DataFrame vacío: no hay logs para tracking.")

    for col in ("x1", "y1", "x2", "y2"):
        if col not in df.columns:
            raise ValueError(f"Falta columna requerida: {col}")

    x1 = pd.to_numeric(df["x1"], errors="coerce")
    y1 = pd.to_numeric(df["y1"], errors="coerce")
    x2 = pd.to_numeric(df["x2"], errors="coerce")
    y2 = pd.to_numeric(df["y2"], errors="coerce")

    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0

    half_w = (tolerance_ratio / 2.0) * float(frame_width)
    half_h = (tolerance_ratio / 2.0) * float(frame_height)
    center_x = float(frame_width) / 2.0
    center_y = float(frame_height) / 2.0

    x_lo, x_hi = center_x - half_w, center_x + half_w
    y_lo, y_hi = center_y - half_h, center_y + half_h

    inside = (cx >= x_lo) & (cx <= x_hi) & (cy >= y_lo) & (cy <= y_hi)
    inside = inside.fillna(False)

    success_rate_event = float(inside.mean()) if len(inside) else float("nan")

    # Ponderación por tiempo (si hay timestamps).
    ts = pd.to_datetime(df["timestamp"], errors="coerce")
    dt = ts.diff().dt.total_seconds().fillna(0.0)
    # Para la primera fila, usamos el siguiente dt como aproximación si existe.
    if len(dt) >= 2:
        dt.iloc[0] = float(dt.iloc[1])
    dt = dt.clip(lower=0.0)

    total_time = float(dt.sum())
    if total_time > 0:
        success_time = float((dt * inside.astype(float)).sum())
        success_rate_time = success_time / total_time
    else:
        success_rate_time = float("nan")

    return {
        "tolerance_ratio": float(tolerance_ratio),
        "frame_width": int(frame_width),
        "frame_height": int(frame_height),
        "n_events": int(len(df)),
        "success_events": int(inside.sum()),
        "success_rate_event": success_rate_event,
        "success_rate_time": success_rate_time,
        "central_window": {"x_lo": x_lo, "x_hi": x_hi, "y_lo": y_lo, "y_hi": y_hi},
    }


def generar_graficas_capitulo4(
    df: pd.DataFrame,
    *,
    metrics_report: dict[str, Any],
    tracking_report: dict[str, Any],
    frames_df: pd.DataFrame | None = None,
    output_dir: str = "chapter4_out",
    prefix: str = "cap4",
) -> dict[str, str]:
    """
    Exporta gráficas profesionales en PNG:
    1) FPS a lo largo del tiempo
    2) Dispersión de centros de bbox + ventana central de tolerancia
    3) Matriz de confusión (proxy) basada en el umbral de confianza
    """

    # Importación diferida: permite usar el script para métricas/tablas aunque no esté instalado
    # el stack de visualización (matplotlib/seaborn). Para tesis se recomienda instalarlo.
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import seaborn as sns
    except Exception as e:  # pragma: no cover (depende del entorno)
        raise RuntimeError(
            "Faltan dependencias de gráficas. Instala: pip install matplotlib seaborn"
        ) from e

    out = Path(output_dir)
    fig_dir = out / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    sns.set_theme(style="whitegrid", context="talk")

    # 1) FPS vs tiempo
    if frames_df is not None and not frames_df.empty and "inference_ms" in frames_df.columns:
        ms = pd.to_numeric(frames_df["inference_ms"], errors="coerce")
        fps = (1000.0 / ms).replace([np.inf, -np.inf], np.nan)
        fps_ts = pd.to_datetime(frames_df["timestamp"])
    else:
        fps = _fps_series_from_logs(df)
        fps_ts = pd.to_datetime(df["timestamp"])
    fig1, ax1 = plt.subplots(figsize=(12, 5))
    ax1.plot(fps_ts, fps, linewidth=1.5)
    ax1.set_title("FPS (rendimiento) a lo largo del tiempo")
    ax1.set_xlabel("Tiempo")
    ax1.set_ylabel("FPS")
    ax1.grid(True, alpha=0.3)
    fps_path = fig_dir / f"{prefix}_fps_time.png"
    fig1.tight_layout()
    fig1.savefig(fps_path, dpi=200)
    plt.close(fig1)

    # 2) Dispersión bbox centers
    x1 = pd.to_numeric(df["x1"], errors="coerce")
    y1 = pd.to_numeric(df["y1"], errors="coerce")
    x2 = pd.to_numeric(df["x2"], errors="coerce")
    y2 = pd.to_numeric(df["y2"], errors="coerce")
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0

    fig2, ax2 = plt.subplots(figsize=(8, 6))
    ax2.scatter(cx, cy, s=12, alpha=0.45)
    ax2.set_title("Dispersión de centros de Bounding Boxes")
    ax2.set_xlabel("Centro X (px)")
    ax2.set_ylabel("Centro Y (px)")
    ax2.invert_yaxis()  # convención de imagen: y crece hacia abajo

    win = tracking_report.get("central_window", {})
    x_lo = float(win.get("x_lo", 0.0))
    x_hi = float(win.get("x_hi", 0.0))
    y_lo = float(win.get("y_lo", 0.0))
    y_hi = float(win.get("y_hi", 0.0))
    rect = plt.Rectangle((x_lo, y_lo), x_hi - x_lo, y_hi - y_lo, fill=False, linewidth=2.5, color="red")
    ax2.add_patch(rect)
    ax2.text(
        x_lo,
        y_lo,
        f"Zona central {int(tracking_report.get('tolerance_ratio', 0.30) * 100)}%",
        color="red",
        fontsize=12,
        verticalalignment="bottom",
    )

    scatter_path = fig_dir / f"{prefix}_bbox_scatter.png"
    fig2.tight_layout()
    fig2.savefig(scatter_path, dpi=200)
    plt.close(fig2)

    # 3) Matriz de confusión (proxy)
    proxy = metrics_report.get("proxy_classic_metrics", {})
    tp = int(proxy.get("tp", 0))
    fp = int(proxy.get("fp", 0))
    fn = int(proxy.get("fn", 0))
    tn = 0  # no observable sin ground truth

    cm = np.array([[tp, fn], [fp, tn]], dtype=int)
    fig3, ax3 = plt.subplots(figsize=(6, 5))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", cbar=False, ax=ax3)
    ax3.set_title("Matriz de Confusión (Proxy)")
    ax3.set_xlabel("Predicción")
    ax3.set_ylabel("Real")
    ax3.set_xticklabels(["Positivo", "Negativo"])
    ax3.set_yticklabels(["Positivo", "Negativo"], rotation=0)
    cm_path = fig_dir / f"{prefix}_confusion_proxy.png"
    fig3.tight_layout()
    fig3.savefig(cm_path, dpi=200)
    plt.close(fig3)

    return {
        "fps_time_png": str(fps_path),
        "bbox_scatter_png": str(scatter_path),
        "confusion_png": str(cm_path),
    }


def cargar_resultados_entrenamiento(*, run_dir: str) -> pd.DataFrame:
    """
    Carga el `results.csv` generado por Ultralytics (YOLO) durante entrenamiento.

    Estructura típica:
      runs/detect/train-*/results.csv

    Columnas esperadas (pueden variar por versión):
      - epoch
      - metrics/precision(B), metrics/recall(B), metrics/mAP50(B), metrics/mAP50-95(B)
      - train/box_loss, train/cls_loss, train/dfl_loss
      - val/box_loss, val/cls_loss, val/dfl_loss
      - lr/pg*
    """

    base = Path(run_dir)
    csv_path = base / "results.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"No existe: {csv_path}")
    df = pd.read_csv(csv_path)
    if "epoch" not in df.columns:
        raise ValueError(f"`results.csv` no contiene columna `epoch`: {csv_path}")
    return df


def analizar_entrenamiento_modelo(*, run_dir: str) -> dict[str, Any]:
    """
    Genera un resumen científico del entrenamiento (para Capítulo 4 / anexos):
    - Mejor época según mAP50-95(B) (si existe), o mAP50(B) como fallback.
    - Métricas finales (última época) y mejores (best).
    - Argumentos de entrenamiento (args.yaml) cuando sea posible.
    """

    df = cargar_resultados_entrenamiento(run_dir=run_dir)

    map_col = "metrics/mAP50-95(B)" if "metrics/mAP50-95(B)" in df.columns else None
    if map_col is None and "metrics/mAP50(B)" in df.columns:
        map_col = "metrics/mAP50(B)"

    if map_col is None:
        raise ValueError("No se encontró mAP en results.csv (mAP50 o mAP50-95).")

    best_idx = int(pd.to_numeric(df[map_col], errors="coerce").fillna(-1).idxmax())
    best_row = df.iloc[best_idx].to_dict()
    last_row = df.iloc[-1].to_dict()

    # args.yaml (si existe); parseo opcional.
    args_path = Path(run_dir) / "args.yaml"
    args_payload: dict[str, Any] | None = None
    if args_path.exists():
        try:
            import yaml  # type: ignore

            args_payload = yaml.safe_load(args_path.read_text(encoding="utf-8", errors="replace")) or None
        except Exception:
            # Si no está PyYAML o falla, guardamos el texto crudo para trazabilidad.
            args_payload = {"raw_text": args_path.read_text(encoding="utf-8", errors="replace")}

    def _pick(row: dict[str, Any], key: str) -> float | None:
        if key not in row:
            return None
        v = _safe_float(row.get(key))
        return None if v is None or math.isnan(v) else float(v)

    report = {
        "run_dir": str(Path(run_dir)),
        "n_epochs": int(len(df)),
        "best": {
            "epoch": int(best_row.get("epoch", best_idx)),
            "mAP_key": map_col,
            "precision": _pick(best_row, "metrics/precision(B)"),
            "recall": _pick(best_row, "metrics/recall(B)"),
            "mAP50": _pick(best_row, "metrics/mAP50(B)"),
            "mAP50_95": _pick(best_row, "metrics/mAP50-95(B)"),
        },
        "last": {
            "epoch": int(last_row.get("epoch", len(df) - 1)),
            "precision": _pick(last_row, "metrics/precision(B)"),
            "recall": _pick(last_row, "metrics/recall(B)"),
            "mAP50": _pick(last_row, "metrics/mAP50(B)"),
            "mAP50_95": _pick(last_row, "metrics/mAP50-95(B)"),
        },
        "args": args_payload,
        "results_csv": str(Path(run_dir) / "results.csv"),
    }
    return report


def generar_graficas_entrenamiento(*, run_dir: str, output_dir: str = "chapter4_out", prefix: str = "cap4") -> dict[str, str]:
    """
    Exporta curvas de entrenamiento (PNG) a partir de `runs/*/results.csv`:
    - mAP50 y mAP50-95 vs época
    - Precision y Recall vs época
    - Losses train/val vs época
    """

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import seaborn as sns
    except Exception as e:  # pragma: no cover
        raise RuntimeError("Faltan dependencias de gráficas. Instala: pip install matplotlib seaborn") from e

    df = cargar_resultados_entrenamiento(run_dir=run_dir)
    out = Path(output_dir)
    fig_dir = out / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="whitegrid", context="talk")

    epoch = pd.to_numeric(df["epoch"], errors="coerce")

    # Curvas de métricas
    fig1, ax1 = plt.subplots(figsize=(12, 5))
    for col, label in [
        ("metrics/precision(B)", "Precision"),
        ("metrics/recall(B)", "Recall"),
        ("metrics/mAP50(B)", "mAP@0.50"),
        ("metrics/mAP50-95(B)", "mAP@0.50:0.95"),
    ]:
        if col in df.columns:
            ax1.plot(epoch, pd.to_numeric(df[col], errors="coerce"), label=label, linewidth=2.0)
    ax1.set_title("Curvas de métricas (entrenamiento/validación)")
    ax1.set_xlabel("Época")
    ax1.set_ylabel("Valor")
    ax1.legend(loc="best")
    ax1.grid(True, alpha=0.3)
    metrics_path = fig_dir / f"{prefix}_training_metrics.png"
    fig1.tight_layout()
    fig1.savefig(metrics_path, dpi=200)
    plt.close(fig1)

    # Curvas de loss
    fig2, ax2 = plt.subplots(figsize=(12, 5))
    for col, label in [
        ("train/box_loss", "train/box_loss"),
        ("train/cls_loss", "train/cls_loss"),
        ("train/dfl_loss", "train/dfl_loss"),
        ("val/box_loss", "val/box_loss"),
        ("val/cls_loss", "val/cls_loss"),
        ("val/dfl_loss", "val/dfl_loss"),
    ]:
        if col in df.columns:
            ax2.plot(epoch, pd.to_numeric(df[col], errors="coerce"), label=label, linewidth=1.8)
    ax2.set_title("Curvas de pérdida (loss) por época")
    ax2.set_xlabel("Época")
    ax2.set_ylabel("Loss")
    ax2.legend(loc="best", ncols=2)
    ax2.grid(True, alpha=0.3)
    loss_path = fig_dir / f"{prefix}_training_losses.png"
    fig2.tight_layout()
    fig2.savefig(loss_path, dpi=200)
    plt.close(fig2)

    return {
        "training_metrics_png": str(metrics_path),
        "training_losses_png": str(loss_path),
    }


def _write_outputs(
    df: pd.DataFrame,
    *,
    metrics_report: dict[str, Any],
    tracking_report: dict[str, Any],
    figure_paths: dict[str, str],
    training_report: dict[str, Any] | None,
    output_dir: str,
) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Datos tabulares para reproducibilidad.
    df_out = df.copy()
    df_out["timestamp"] = pd.to_datetime(df_out["timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S.%f")
    df_out.to_csv(out / "normalized_logs.csv", index=False, encoding="utf-8")

    summary = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "metrics_report": metrics_report,
        "tracking_report": tracking_report,
        "training_report": training_report,
        "figures": figure_paths,
    }
    (out / "metrics_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Analizador de métricas y tracking (Capítulo 4)")
    parser.add_argument("--sqlite", dest="sqlite_path", default=None, help="Ruta a detections.db (SQLite)")
    parser.add_argument("--sqlite-table", dest="sqlite_table", default="auto", help="Tabla detecciones en SQLite (default: auto)")
    parser.add_argument(
        "--frames-table",
        dest="frames_table",
        default="inference_frames",
        help="Tabla de telemetría por frame (default: inference_frames)",
    )
    parser.add_argument("--json", dest="json_path", default=None, help="Ruta a log JSON/JSONL (opcional)")
    parser.add_argument("--out", dest="output_dir", default="chapter4_out", help="Directorio de salida")
    parser.add_argument("--conf-th", dest="conf_th", type=float, default=0.50, help="Umbral de confianza (proxy)")
    parser.add_argument("--frame-w", dest="frame_w", type=int, default=1920, help="Ancho del frame (px)")
    parser.add_argument("--frame-h", dest="frame_h", type=int, default=1080, help="Alto del frame (px)")
    parser.add_argument(
        "--expected-fps",
        dest="expected_fps",
        type=float,
        default=None,
        help="FPS esperado (opcional) para estimar FN proxy",
    )
    parser.add_argument(
        "--train-run",
        dest="train_run_dir",
        default=None,
        help="Directorio de entrenamiento Ultralytics (ej. runs/detect/train-10) para incluir resultados de entrenamiento",
    )
    args = parser.parse_args()

    df = cargar_logs_deteccion(sqlite_path=args.sqlite_path, sqlite_table=args.sqlite_table, json_path=args.json_path)

    frames_df: pd.DataFrame | None = None
    if args.sqlite_path:
        try:
            frames_df = cargar_logs_inferencia(sqlite_path=args.sqlite_path, sqlite_table=args.frames_table)
        except Exception:
            frames_df = None

    metrics = calcular_rendimiento_ia(df, confidence_threshold=args.conf_th, expected_fps=args.expected_fps, frames_df=frames_df)
    tracking = evaluar_tracking_ptz(
        df,
        frame_width=args.frame_w,
        frame_height=args.frame_h,
        tolerance_ratio=AnalyzerConfig().tolerance_ratio,
    )
    figs: dict[str, str] = {}
    try:
        figs = generar_graficas_capitulo4(
            df,
            metrics_report=metrics,
            tracking_report=tracking,
            frames_df=frames_df,
            output_dir=args.output_dir,
        )
    except RuntimeError as e:
        # Entorno sin matplotlib/seaborn: se conserva el análisis numérico y tabular.
        print(f"[WARN] No se generaron gráficas: {e}")

    training_report: dict[str, Any] | None = None
    if args.train_run_dir:
        training_report = analizar_entrenamiento_modelo(run_dir=args.train_run_dir)
        try:
            figs.update(generar_graficas_entrenamiento(run_dir=args.train_run_dir, output_dir=args.output_dir))
        except RuntimeError as e:
            print(f"[WARN] No se generaron gráficas de entrenamiento: {e}")

    _write_outputs(
        df,
        metrics_report=metrics,
        tracking_report=tracking,
        figure_paths=figs,
        training_report=training_report,
        output_dir=args.output_dir,
    )

    print(f"[OK] Resumen: {Path(args.output_dir) / 'metrics_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ======================================================================
# Tests unitarios rápidos (pytest)
# ======================================================================
#
# Nota:
# - Se incluyen aquí por requerimiento del anexo.
# - Para ejecutarlos:
#     pytest -q test_metrics_analyzer.py
#
# Estos tests validan reglas del backend:
# 1) "Enjambre": priorizar bbox más grande.
# 2) Fail-safe ONVIF: bloquear movimiento si la cámara es fija (no PTZ).


def test_regla_enjambre_prioriza_bbox_mas_grande() -> None:
    detections = [
        {"confidence": 0.90, "bbox": (10, 10, 20, 20)},  # área 100
        {"confidence": 0.60, "bbox": (0, 0, 50, 10)},  # área 500 (debe ganar)
        {"confidence": 0.99, "bbox": (5, 5, 15, 15)},  # área 100
    ]
    picked = select_priority_detection(detections)
    assert picked is detections[1]


def test_regla_enjambre_lista_vacia_devuelve_none() -> None:
    assert select_priority_detection([]) is None


def test_fail_safe_onvif_rechaza_movimiento_si_camara_fija() -> None:
    assert should_allow_ptz_move(is_ptz_capable=False) is False
    try:
        assert_ptz_capable(is_ptz_capable=False)
    except PermissionError:
        pass
    else:
        raise AssertionError("Se esperaba PermissionError cuando PTZ no está disponible.")
