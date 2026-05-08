from __future__ import annotations

import os
import sqlite3
import time
from typing import Callable


def cleanup_old_evidence(
    *,
    root_path: str,
    evidence_dir_default: str,
    get_metrics_db_path_abs: Callable[[], str],
    env_int: Callable[[str, int], int],
    ensure_detection_events_schema: Callable[[sqlite3.Connection], None],
    dry_run: bool = True,
) -> dict:
    """
    Limpieza segura de evidencias para no saturar disco.

    - No se ejecuta automáticamente.
    - Por defecto `dry_run=True` (solo reporta).

    Nota: mantiene compatibilidad con override por env var `EVIDENCE_DIR`.
    """
    evidence_dir = (os.environ.get("EVIDENCE_DIR") or evidence_dir_default).strip() or evidence_dir_default
    max_files = int(env_int("EVIDENCE_MAX_FILES", 500))
    max_age_days = int(env_int("EVIDENCE_MAX_AGE_DAYS", 30))
    max_files = max(50, min(5000, int(max_files)))
    max_age_days = max(1, min(365, int(max_age_days)))

    abs_dir = evidence_dir
    if not os.path.isabs(abs_dir):
        abs_dir = os.path.join(root_path, evidence_dir)
    abs_dir = os.path.abspath(abs_dir)

    kept_refs: set[str] = set()
    db_path = get_metrics_db_path_abs()
    try:
        if os.path.exists(db_path):
            con = sqlite3.connect(db_path, timeout=10, check_same_thread=False)
            con.row_factory = sqlite3.Row
            try:
                ensure_detection_events_schema(con)
                cur = con.cursor()
                cur.execute(
                    """
                    SELECT best_evidence_path
                    FROM detection_events
                    ORDER BY id DESC
                    LIMIT 200
                    """
                )
                for r in cur.fetchall() or []:
                    p = (r["best_evidence_path"] or "").replace("\\", "/").lstrip("/")
                    if p:
                        kept_refs.add(p)
            finally:
                try:
                    con.close()
                except Exception:
                    pass
    except Exception:
        pass

    try:
        if not os.path.isdir(abs_dir):
            return {"ok": True, "evidence_dir": abs_dir, "files_deleted": 0, "dry_run": dry_run, "reason": "missing_dir"}

        now = time.time()
        max_age_s = float(max_age_days) * 86400.0
        files = []
        for name in os.listdir(abs_dir):
            if not name.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            abs_path = os.path.join(abs_dir, name)
            try:
                st = os.stat(abs_path)
            except Exception:
                continue
            rel_path = os.path.relpath(abs_path, root_path).replace("\\", "/")
            files.append({"abs": abs_path, "rel": rel_path, "mtime": float(st.st_mtime)})

        to_delete = []
        for f in files:
            age_s = now - float(f["mtime"])
            if age_s > max_age_s and f["rel"].replace("\\", "/") not in kept_refs:
                to_delete.append(f)

        files_sorted = sorted(files, key=lambda x: float(x["mtime"]))
        if len(files_sorted) - len(to_delete) > max_files:
            for f in files_sorted:
                if len(files_sorted) - len(to_delete) <= max_files:
                    break
                if f["rel"].replace("\\", "/") in kept_refs:
                    continue
                if f not in to_delete:
                    to_delete.append(f)

        deleted = 0
        for f in to_delete:
            if dry_run:
                continue
            try:
                os.remove(f["abs"])
                deleted += 1
            except Exception:
                continue

        return {
            "ok": True,
            "evidence_dir": abs_dir,
            "dry_run": bool(dry_run),
            "files_total": len(files),
            "files_marked": len(to_delete),
            "files_deleted": deleted,
            "kept_refs": len(kept_refs),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

