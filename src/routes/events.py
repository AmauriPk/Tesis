from __future__ import annotations

import os
import sqlite3
import struct
import time
from datetime import datetime
from typing import Any, Callable

from flask import Blueprint, Response, jsonify, request
from flask_login import login_required

events_bp = Blueprint("events", __name__)

_deps: dict[str, Any] = {}
_routes_initialized = False


def _get_dep(key: str):
    try:
        return _deps[key]
    except KeyError as exc:
        raise RuntimeError(f"Dependencia faltante en events: {key}") from exc


def init_events_routes(**deps: Any) -> None:
    """
    Inicializa dependencias y registra rutas en el Blueprint.

    Evita imports circulares con `app.py` al recibir referencias explícitas.
    """
    global _deps, _routes_initialized
    _deps = dict(deps or {})

    if _routes_initialized:
        return
    _routes_initialized = True

    role_required = _get_dep("role_required")
    get_metrics_db_path_abs: Callable[[], str] = _get_dep("get_metrics_db_path_abs")
    ensure_detection_events_schema: Callable[[sqlite3.Connection], None] = _get_dep("ensure_detection_events_schema")
    parse_iso_ts_to_epoch: Callable[[str | None], float | None] = _get_dep("parse_iso_ts_to_epoch")

    @events_bp.get("/api/recent_alerts")
    @login_required
    @role_required("operator")
    def api_recent_alerts():
        """
        Retorna las últimas detecciones confirmadas (para Panel de Alertas del Operador).
        Fail-safe: ante DB inexistente/bloqueada => lista vacía (200).
        """
        db_path = _get_dep("storage_config").get("db_path", "detections.db")
        if db_path and not os.path.isabs(db_path):
            db_path = os.path.join(_get_dep("app_root_path"), db_path)
        limit_raw = (request.args.get("limit") or "").strip()
        try:
            limit = int(limit_raw) if limit_raw else 15
        except Exception:
            limit = 15
        limit = max(1, min(50, int(limit)))

        alerts = []

        try:
            if not os.path.exists(db_path):
                print(f"[ALERTS] db={db_path} missing_db=1")
                return jsonify({"status": "success", "alerts": alerts}), 200

            con = sqlite3.connect(db_path, timeout=10, check_same_thread=False)
            con.row_factory = sqlite3.Row
            try:
                cur = con.cursor()
                try:
                    cur.execute("PRAGMA journal_mode=WAL;")
                except Exception:
                    pass

                # Detecta la tabla real disponible (evita "no such table" silencioso).
                cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = {str(r[0]) for r in (cur.fetchall() or [])}

                rows = []
                using_table = None
                if "detections_v2" in tables:
                    using_table = "detections_v2"
                    cur.execute(
                        """
                        SELECT id, timestamp, confidence, x1, y1, x2, y2, class_name, source, camera_mode, image_path
                        FROM detections_v2
                        WHERE confirmed = 1
                        ORDER BY id DESC
                        LIMIT ?
                        """,
                        (limit,),
                    )
                    rows = cur.fetchall() or []
                elif "inference_frames" in tables:
                    # Fallback: existe confirmación por frame, pero no hay bbox por detección.
                    using_table = "inference_frames"
                    cur.execute(
                        """
                        SELECT id, timestamp, NULL as confidence, NULL as x1, NULL as y1, NULL as x2, NULL as y2,
                               NULL as class_name, source, camera_mode
                        FROM inference_frames
                        WHERE confirmed = 1
                        ORDER BY id DESC
                        LIMIT ?
                        """,
                        (limit,),
                    )
                    rows = cur.fetchall() or []
                else:
                    print(f"[WARN] Panel de Alertas: no hay tablas esperadas en DB. tables={sorted(tables)}")
                    return jsonify({"status": "success", "alerts": []}), 200
                alerts = []
                def _to_int(v):
                    """
                    Convierte valores heterogeneos de SQLite/Numpy a int seguro.

                    Args:
                        v: Valor proveniente de sqlite (int/str/bytes/BLOB/etc.).

                    Returns:
                        int si es convertible; si no, None.
                    """
                    if v is None:
                        return None
                    if isinstance(v, (int, bool)):
                        return int(v)
                    # En algunas filas, coordenadas se guardaron como BLOB (bytes) por tipos numpy.
                    if isinstance(v, (bytes, bytearray, memoryview)):
                        b = bytes(v)
                        try:
                            if len(b) == 4:
                                return int(struct.unpack("<i", b)[0])
                            if len(b) == 8:
                                return int(struct.unpack("<q", b)[0])
                            return int.from_bytes(b, "little", signed=False)
                        except Exception:
                            return None
                    try:
                        return int(v)
                    except Exception:
                        return None

                for r in rows:
                    x1 = _to_int(r["x1"]) if "x1" in r.keys() else None
                    y1 = _to_int(r["y1"]) if "y1" in r.keys() else None
                    x2 = _to_int(r["x2"]) if "x2" in r.keys() else None
                    y2 = _to_int(r["y2"]) if "y2" in r.keys() else None

                    image_path = None
                    try:
                        image_path = r["image_path"] if "image_path" in r.keys() else None
                    except Exception:
                        image_path = None
                    if isinstance(image_path, (bytes, bytearray, memoryview)):
                        try:
                            image_path = bytes(image_path).decode("utf-8", errors="ignore")
                        except Exception:
                            image_path = None

                    # URL web (regla solicitada):
                    # - Si DB guarda "static/..." => "/static/..."
                    # - Si viene absoluta dentro del proyecto => convertir a relativa
                    # - Si no se puede mapear => ""
                    image_url = ""
                    image_path_rel = ""
                    try:
                        raw = (str(image_path).strip() if image_path else "") or ""
                        if raw:
                            p = raw.replace("\\", "/")
                            if os.path.isabs(p):
                                try:
                                    root_abs = os.path.abspath(_get_dep("app_root_path"))
                                    p_abs = os.path.abspath(p)
                                    if p_abs.startswith(root_abs):
                                        p = os.path.relpath(p_abs, root_abs).replace("\\", "/")
                                    else:
                                        p = ""
                                except Exception:
                                    p = ""
                            if p:
                                p = p.lstrip("/")
                                image_url = "/" + p
                                image_path_rel = p
                    except Exception:
                        image_url = ""
                        image_path_rel = ""

                    bbox_text = "-"
                    if x1 is not None and y1 is not None and x2 is not None and y2 is not None:
                        bbox_text = f"{int(x1)},{int(y1)},{int(x2)},{int(y2)}"
                    alerts.append(
                        {
                            "id": int(r["id"]) if r["id"] is not None else None,
                            "timestamp": r["timestamp"],
                            "confidence": float(r["confidence"]) if r["confidence"] is not None else None,
                            "bbox": [x1, y1, x2, y2],
                            "x1": x1,
                            "y1": y1,
                            "x2": x2,
                            "y2": y2,
                            "bbox_text": bbox_text,
                            "class_name": r["class_name"],
                            "source": r["source"],
                            "camera_mode": r["camera_mode"],
                            "confirmed": True,
                            # Compat frontend: `image_path` (relativo, sin slash inicial) y `image_url`.
                            "image_path": image_path_rel,
                            "image_url": image_url,
                            "evidence_url": image_url,
                        }
                    )
                print(f"[ALERTS] db={db_path} table={using_table} rows={len(alerts)}")
                return jsonify({"ok": True, "status": "success", "alerts": alerts, "table": using_table}), 200
            finally:
                try:
                    con.close()
                except Exception:
                    pass
        except Exception as e:
            # DB bloqueada/corrupta/etc => no romper UI del operador.
            print(f"[ERROR] Panel de Alertas DB: {e}")
            return jsonify({"ok": True, "status": "success", "alerts": []}), 200

    @events_bp.get("/api/recent_detection_events")
    @login_required
    @role_required("operator")
    def api_recent_detection_events():
        """
        UI amigable: eventos agrupados en vez de miles de filas por frame.
        Fail-safe: si no hay tabla o DB => lista vacía (200).
        """
        db_path = get_metrics_db_path_abs()
        limit_raw = (request.args.get("limit") or "").strip()
        try:
            limit = int(limit_raw) if limit_raw else 15
        except Exception:
            limit = 15
        limit = max(1, min(50, int(limit)))

        events: list[dict] = []
        try:
            if not os.path.exists(db_path):
                return jsonify({"ok": True, "status": "success", "events": []}), 200

            con = sqlite3.connect(db_path, timeout=10, check_same_thread=False)
            con.row_factory = sqlite3.Row
            try:
                ensure_detection_events_schema(con)
                cur = con.cursor()
                cur.execute(
                    """
                    SELECT id, started_at, ended_at, max_confidence, detection_count, best_bbox_text, best_evidence_path, status, source
                    FROM detection_events
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                rows = cur.fetchall() or []
                for r in rows:
                    best_path = (r["best_evidence_path"] or "") if "best_evidence_path" in r.keys() else ""
                    best_url = ""
                    if best_path:
                        p = str(best_path).replace("\\", "/").lstrip("/")
                        best_url = "/" + p

                    started_at = r["started_at"]
                    ended_at = r["ended_at"]
                    duration_s = None
                    try:
                        s_epoch = parse_iso_ts_to_epoch(str(started_at)) if started_at else None
                        e_epoch = parse_iso_ts_to_epoch(str(ended_at)) if ended_at else None
                        if s_epoch is not None and e_epoch is not None:
                            duration_s = max(0.0, float(e_epoch - s_epoch))
                    except Exception:
                        duration_s = None
                    events.append(
                        {
                            "id": int(r["id"]) if r["id"] is not None else None,
                            "started_at": r["started_at"],
                            "ended_at": r["ended_at"],
                            "duration_s": duration_s,
                            "max_confidence": float(r["max_confidence"]) if r["max_confidence"] is not None else 0.0,
                            "detection_count": int(r["detection_count"]) if r["detection_count"] is not None else 0,
                            "best_bbox": (r["best_bbox_text"] or "-") if "best_bbox_text" in r.keys() else "-",
                            "best_evidence_url": best_url,
                            "status": r["status"] or "",
                            "source": r["source"] or "",
                        }
                    )
                return jsonify({"ok": True, "status": "success", "events": events}), 200
            finally:
                try:
                    con.close()
                except Exception:
                    pass
        except Exception as e:
            print(f"[EVENTS][ERROR] {e}")
            return jsonify({"ok": True, "status": "success", "events": []}), 200

    @events_bp.get("/api/export_detection_events.csv")
    @login_required
    @role_required("operator", "admin")
    def api_export_detection_events_csv():
        """Exporta eventos agrupados a CSV (útil para tesis)."""
        db_path = get_metrics_db_path_abs()
        header = "event_id,started_at,ended_at,duration_s,max_confidence,detection_count,best_bbox,best_evidence_path,status,source\n"
        if not os.path.exists(db_path):
            return Response(header, mimetype="text/csv")

        con = sqlite3.connect(db_path, timeout=10, check_same_thread=False)
        con.row_factory = sqlite3.Row
        try:
            ensure_detection_events_schema(con)
            cur = con.cursor()
            cur.execute(
                """
                SELECT id, started_at, ended_at, max_confidence, detection_count, best_bbox_text, best_evidence_path, status, source
                FROM detection_events
                ORDER BY id ASC
                """
            )
            rows = cur.fetchall() or []

            def esc(v) -> str:
                s = "" if v is None else str(v)
                s = s.replace('\"', '\"\"')
                return f"\"{s}\""

            lines = [header.rstrip("\n")]
            for r in rows:
                started_at = r["started_at"]
                ended_at = r["ended_at"]
                duration_s = ""
                try:
                    s_epoch = parse_iso_ts_to_epoch(str(started_at)) if started_at else None
                    e_epoch = parse_iso_ts_to_epoch(str(ended_at)) if ended_at else None
                    if s_epoch is not None and e_epoch is not None:
                        duration_s = f"{max(0.0, float(e_epoch - s_epoch)):.3f}"
                except Exception:
                    duration_s = ""

                lines.append(
                    ",".join(
                        [
                            str(int(r["id"])),
                            esc(r["started_at"] or ""),
                            esc(r["ended_at"] or ""),
                            duration_s,
                            f"{float(r['max_confidence'] or 0.0):.6f}",
                            str(int(r["detection_count"] or 0)),
                            esc(r["best_bbox_text"] or ""),
                            esc(r["best_evidence_path"] or ""),
                            esc(r["status"] or ""),
                            esc(r["source"] or ""),
                        ]
                    )
                )

            csv_bytes = ("\n".join(lines) + "\n").encode("utf-8")
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = f"detection_events_{stamp}.csv"
            return Response(
                csv_bytes,
                mimetype="text/csv",
                headers={"Content-Disposition": f"attachment; filename={fname}"},
            )
        finally:
            try:
                con.close()
            except Exception:
                pass

    @events_bp.get("/api/detection_summary")
    @login_required
    @role_required("operator", "admin")
    def api_detection_summary():
        """Resumen estadístico de eventos/evidencias (para UI)."""
        db_path = get_metrics_db_path_abs()
        evidence_dir = (os.environ.get("EVIDENCE_DIR") or _get_dep("evidence_dir")).strip() or _get_dep("evidence_dir")
        abs_ev = evidence_dir if os.path.isabs(evidence_dir) else os.path.join(_get_dep("app_root_path"), evidence_dir)
        abs_ev = os.path.abspath(abs_ev)

        summary = {
            "ok": True,
            "total_events": 0,
            "open_events": 0,
            "closed_events": 0,
            "total_raw_detections": 0,
            "avg_confidence": 0.0,
            "max_confidence": 0.0,
            "events_with_evidence": 0,
            "evidence_files_count": 0,
        }

        try:
            if os.path.isdir(abs_ev):
                summary["evidence_files_count"] = len([n for n in os.listdir(abs_ev) if n.lower().endswith((".jpg", ".jpeg", ".png"))])
        except Exception:
            pass

        if not os.path.exists(db_path):
            return jsonify(summary), 200

        con = sqlite3.connect(db_path, timeout=10, check_same_thread=False)
        con.row_factory = sqlite3.Row
        try:
            ensure_detection_events_schema(con)
            cur = con.cursor()
            cur.execute("SELECT COUNT(1) FROM detection_events")
            summary["total_events"] = int(cur.fetchone()[0] or 0)

            cur.execute("SELECT COUNT(1) FROM detection_events WHERE status='open'")
            summary["open_events"] = int(cur.fetchone()[0] or 0)

            cur.execute("SELECT COUNT(1) FROM detection_events WHERE status='closed'")
            summary["closed_events"] = int(cur.fetchone()[0] or 0)

            cur.execute(
                "SELECT COUNT(1) FROM detection_events WHERE best_evidence_path IS NOT NULL AND TRIM(best_evidence_path) <> ''"
            )
            summary["events_with_evidence"] = int(cur.fetchone()[0] or 0)

            cur.execute("SELECT AVG(max_confidence), MAX(max_confidence) FROM detection_events")
            row = cur.fetchone()
            if row:
                summary["avg_confidence"] = float(row[0] or 0.0)
                summary["max_confidence"] = float(row[1] or 0.0)

            # Conteos técnicos (detections_v2)
            try:
                cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = {str(r[0]) for r in (cur.fetchall() or [])}
                if "detections_v2" in tables:
                    cur.execute("SELECT COUNT(1) FROM detections_v2")
                    summary["total_raw_detections"] = int(cur.fetchone()[0] or 0)
            except Exception:
                pass

            return jsonify(summary), 200
        finally:
            try:
                con.close()
            except Exception:
                pass

    @events_bp.post("/api/admin/cleanup_test_data")
    @login_required
    @role_required("admin")
    def api_admin_cleanup_test_data():
        """
        Limpieza segura (admin). No borra nada si no se recibe true explícito.
        """
        payload = request.get_json(silent=True) or {}
        clear_raw = bool(payload.get("clear_raw_detections"))
        clear_events = bool(payload.get("clear_events"))
        clear_evidence = bool(payload.get("clear_evidence"))

        db_path = get_metrics_db_path_abs()
        evidence_dir = (os.environ.get("EVIDENCE_DIR") or _get_dep("evidence_dir")).strip() or _get_dep("evidence_dir")
        abs_ev = evidence_dir if os.path.isabs(evidence_dir) else os.path.join(_get_dep("app_root_path"), evidence_dir)
        abs_ev = os.path.abspath(abs_ev)

        counts = {"raw_detections": 0, "events": 0, "evidence_files": 0}
        try:
            if os.path.isdir(abs_ev):
                counts["evidence_files"] = len([n for n in os.listdir(abs_ev) if n.lower().endswith((".jpg", ".jpeg", ".png"))])
        except Exception:
            pass

        con = None
        try:
            if os.path.exists(db_path):
                con = sqlite3.connect(db_path, timeout=10, check_same_thread=False)
                con.row_factory = sqlite3.Row
                ensure_detection_events_schema(con)
                cur = con.cursor()
                try:
                    cur.execute("SELECT COUNT(1) FROM detection_events")
                    counts["events"] = int(cur.fetchone()[0] or 0)
                except Exception:
                    pass
                try:
                    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tables = {str(r[0]) for r in (cur.fetchall() or [])}
                    if "detections_v2" in tables:
                        cur.execute("SELECT COUNT(1) FROM detections_v2")
                        counts["raw_detections"] = int(cur.fetchone()[0] or 0)
                except Exception:
                    pass
        except Exception:
            pass

        if not (clear_raw or clear_events or clear_evidence):
            try:
                if con is not None:
                    con.close()
            except Exception:
                pass
            return (
                jsonify(
                    {
                        "ok": True,
                        "preview_only": True,
                        "counts": counts,
                        "message": "Nada borrado. Envía true explícito en clear_* para ejecutar.",
                    }
                ),
                200,
            )

        deleted = {"raw_detections": 0, "events": 0, "evidence_files": 0}
        errors: list[str] = []

        if con is not None:
            try:
                cur = con.cursor()
                if clear_events:
                    cur.execute("DELETE FROM detection_events")
                    deleted["events"] = int(cur.rowcount or 0)
                if clear_raw:
                    try:
                        cur.execute("DELETE FROM detections_v2")
                        deleted["raw_detections"] = int(cur.rowcount or 0)
                    except Exception:
                        pass
                    try:
                        cur.execute("DELETE FROM inference_frames")
                    except Exception:
                        pass
                if clear_events or clear_raw:
                    con.commit()
            except Exception as e:
                errors.append(f"db_delete_failed: {e}")
                try:
                    con.rollback()
                except Exception:
                    pass
        else:
            if clear_events or clear_raw:
                errors.append("db_missing_or_unavailable")

        if clear_evidence:
            try:
                if os.path.isdir(abs_ev):
                    for name in os.listdir(abs_ev):
                        if not name.lower().endswith((".jpg", ".jpeg", ".png")):
                            continue
                        abs_path = os.path.abspath(os.path.join(abs_ev, name))
                        if not (abs_path == abs_ev or abs_path.startswith(abs_ev + os.sep)):
                            continue
                        try:
                            os.remove(abs_path)
                            deleted["evidence_files"] += 1
                        except Exception:
                            continue
            except Exception as e:
                errors.append(f"evidence_delete_failed: {e}")

        try:
            if con is not None:
                con.close()
        except Exception:
            pass

        return (
            jsonify(
                {
                    "ok": True,
                    "preview_only": False,
                    "requested": {
                        "clear_raw_detections": clear_raw,
                        "clear_events": clear_events,
                        "clear_evidence": clear_evidence,
                    },
                    "counts_before": counts,
                    "deleted": deleted,
                    "errors": errors,
                }
            ),
            200,
        )
