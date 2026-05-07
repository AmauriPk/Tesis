from __future__ import annotations

import os
import secrets
import shutil
from datetime import datetime
from typing import Any, Callable

from flask import Blueprint, abort, jsonify, request, send_file, url_for
from flask_login import login_required

dataset_bp = Blueprint("dataset", __name__)

_deps: dict[str, Any] = {}
_routes_initialized = False


def init_dataset_routes(**deps: Any) -> None:
    """
    Inicializa dependencias y registra rutas en el Blueprint.

    Evita imports circulares con `app.py` al recibir referencias explícitas.
    """
    global _deps, _routes_initialized
    _deps = dict(deps or {})

    if _routes_initialized:
        return
    _routes_initialized = True

    role_required = _deps["role_required"]
    safe_join: Callable[[str, str], str] = _deps["safe_join"]

    dataset_recoleccion_folder = _deps["dataset_recoleccion_folder"]
    dataset_training_root = _deps["dataset_training_root"]
    dataset_negative_dir = _deps["dataset_negative_dir"]
    dataset_positive_pending_dir = _deps["dataset_positive_pending_dir"]
    dataset_limpias_inbox_dir = _deps["dataset_limpias_inbox_dir"]

    def _dataset_recoleccion_root() -> str:
        """
        Devuelve la raiz absoluta del dataset de recoleccion configurado.

        Returns:
            Ruta absoluta del directorio configurado en `DATASET_RECOLECCION_FOLDER`.
        """
        return os.path.abspath(dataset_recoleccion_folder)

    def _iter_clean_dataset_images(limit: int = 200) -> list[dict]:
        """
        Lista imágenes limpias en dataset_recoleccion/**/limpias/*.(jpg|png)
        Retorna items con id relativo (para API) y metadatos básicos.
        """
        root = _dataset_recoleccion_root()
        items: list[tuple[float, str]] = []
        exts = {".jpg", ".jpeg", ".png"}

        for dirpath, dirnames, filenames in os.walk(root):
            if os.path.basename(dirpath).lower() != "limpias":
                continue
            for name in filenames:
                _, ext = os.path.splitext(name)
                if ext.lower() not in exts:
                    continue
                full = os.path.join(dirpath, name)
                try:
                    st = os.stat(full)
                    mtime = float(st.st_mtime)
                except Exception:
                    mtime = 0.0
                rel = os.path.relpath(full, root).replace("\\", "/")
                items.append((mtime, rel))

        items.sort(key=lambda x: x[0], reverse=True)
        out: list[dict] = []
        for mtime, rel in items[: max(1, int(limit))]:
            out.append(
                {
                    "id": rel,
                    "name": os.path.basename(rel),
                    "mtime": datetime.fromtimestamp(float(mtime)).isoformat() if mtime else None,
                    "url": url_for("api_get_dataset_image", path=rel),
                }
            )
        return out

    def _unique_dest_path(dest_dir: str, filename: str) -> str:
        """
        Genera una ruta destino unica dentro de un directorio.

        Args:
            dest_dir: Directorio destino.
            filename: Nombre de archivo original.

        Returns:
            Ruta absoluta candidata (no existente) dentro de `dest_dir`.
        """
        os.makedirs(dest_dir, exist_ok=True)
        base, ext = os.path.splitext(filename)
        ext = ext or ".jpg"
        candidate = os.path.join(dest_dir, filename)
        if not os.path.exists(candidate):
            return candidate
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        candidate = os.path.join(dest_dir, f"{base}_{stamp}{ext}")
        if not os.path.exists(candidate):
            return candidate
        # Fallback contador
        for i in range(1, 9999):
            c = os.path.join(dest_dir, f"{base}_{stamp}_{i}{ext}")
            if not os.path.exists(c):
                return c
        return os.path.join(dest_dir, f"{base}_{secrets.token_urlsafe(6)}{ext}")

    def _iter_classified_images(limit: int = 300) -> list[dict]:
        """
        Lista imágenes ya clasificadas:
          - Negativas: DATASET_NEGATIVE_DIR
          - Positivas (pendientes de anotación): DATASET_POSITIVE_PENDING_DIR
        """
        exts = {".jpg", ".jpeg", ".png"}
        sources = [
            ("negative", dataset_negative_dir, "Falso Positivo"),
            ("positive", dataset_positive_pending_dir, "Positiva (Pendiente de Anotación)"),
        ]

        items: list[tuple[float, dict]] = []
        for scope, base, label in sources:
            try:
                base_abs = os.path.abspath(base)
                if not os.path.exists(base_abs):
                    continue
                for name in os.listdir(base_abs):
                    full = os.path.join(base_abs, name)
                    if not os.path.isfile(full):
                        continue
                    _, ext = os.path.splitext(name)
                    if ext.lower() not in exts:
                        continue
                    try:
                        mtime = float(os.stat(full).st_mtime)
                    except Exception:
                        mtime = 0.0
                    rel = os.path.relpath(full, os.path.abspath(dataset_training_root)).replace("\\", "/")
                    category_label = "Dron" if str(scope) == "positive" else "No dron"
                    items.append(
                        (
                            mtime,
                            {
                                "scope": scope,
                                "label": label,
                                "name": name,
                                "filename": name,
                                "id": f"{scope}:{name}",
                                "path": rel,
                                "category": scope,
                                "category_label": category_label,
                                "mtime": datetime.fromtimestamp(float(mtime)).isoformat() if mtime else None,
                                "url": url_for("api_get_classified_image", path=rel),
                            },
                        )
                    )
            except Exception:
                continue

        items.sort(key=lambda x: x[0], reverse=True)
        return [it for _, it in items[: max(1, int(limit))]]

    @dataset_bp.get("/api/get_dataset_images", endpoint="api_get_dataset_images")
    @login_required
    @role_required("admin")
    def api_get_dataset_images():
        """
        Lista imagenes limpias recolectadas (dataset de mejora continua).

        Query params:
            limit: maximo de items a devolver (1..500).

        Returns:
            Tuple `(json, status_code)` con la lista de imagenes y metadatos basicos.
        """
        limit_raw = (request.args.get("limit") or "").strip()
        try:
            limit = int(limit_raw) if limit_raw else 200
        except Exception:
            limit = 200
        limit = max(1, min(500, int(limit)))
        return jsonify({"status": "success", "images": _iter_clean_dataset_images(limit=limit)}), 200

    @dataset_bp.get("/api/dataset_image", endpoint="api_get_dataset_image")
    @login_required
    @role_required("admin")
    def api_get_dataset_image():
        """
        Descarga una imagen especifica del dataset de recoleccion de forma segura.

        Query params:
            path: ruta relativa dentro de la raiz del dataset.

        Returns:
            Respuesta Flask con el archivo o error HTTP (400/404).
        """
        rel = (request.args.get("path") or "").strip()
        try:
            full = safe_join(_dataset_recoleccion_root(), rel)
        except Exception:
            abort(400)
        if not os.path.exists(full) or not os.path.isfile(full):
            abort(404)
        return send_file(full)

    @dataset_bp.post("/api/classify_image", endpoint="api_classify_image")
    @login_required
    @role_required("admin")
    def api_classify_image():
        """
        Reclasifica una imagen del dataset de recoleccion moviendola a su carpeta destino.

        Body esperado (JSON o form-data):
            - id/path: ruta relativa de la imagen dentro de dataset_recoleccion
            - label/classification: {positiva|positive|negativa|negative}
        """
        payload = request.get_json(silent=True) or {}
        if not payload:
            payload = request.form.to_dict(flat=True)

        rel = (payload.get("id") or payload.get("path") or "").strip()
        label = (payload.get("label") or payload.get("classification") or "").strip().lower()
        if not rel:
            return jsonify({"status": "error", "message": "Falta id de imagen."}), 400
        if label not in {"positiva", "positiva_dron", "positive", "negativa", "negative"}:
            return jsonify({"status": "error", "message": "Clasificación inválida."}), 400

        try:
            src = safe_join(_dataset_recoleccion_root(), rel)
        except Exception:
            return jsonify({"status": "error", "message": "Ruta inválida."}), 400
        if not os.path.exists(src) or not os.path.isfile(src):
            return jsonify({"status": "error", "message": "Imagen no encontrada."}), 404

        filename = os.path.basename(src)
        if label in {"negativa", "negative"}:
            dest = _unique_dest_path(dataset_negative_dir, filename)
        else:
            dest = _unique_dest_path(dataset_positive_pending_dir, filename)

        try:
            shutil.move(src, dest)
        except Exception as e:
            return jsonify({"status": "error", "message": f"No se pudo mover archivo: {str(e)}"}), 500

        return jsonify({"status": "success", "moved_to": dest}), 200

    @dataset_bp.get("/api/get_classified_images", endpoint="api_get_classified_images")
    @login_required
    @role_required("admin")
    def api_get_classified_images():
        """
        Lista imagenes ya clasificadas para administracion (negativas y positivas pendientes).

        Query params:
            limit: maximo de items (1..800).

        Returns:
            Tuple `(json, status_code)` con items y metadatos.
        """
        limit_raw = (request.args.get("limit") or "").strip()
        try:
            limit = int(limit_raw) if limit_raw else 300
        except Exception:
            limit = 300
        limit = max(1, min(800, int(limit)))
        return jsonify({"status": "success", "images": _iter_classified_images(limit=limit)}), 200

    @dataset_bp.get("/api/classified_image", endpoint="api_get_classified_image")
    @login_required
    @role_required("admin")
    def api_get_classified_image():
        """
        Descarga una imagen clasificada (dataset de entrenamiento) de forma segura.

        Query params:
            path: ruta relativa dentro de `DATASET_TRAINING_ROOT`.

        Returns:
            Respuesta Flask con el archivo o error HTTP (400/404).
        """
        rel = (request.args.get("path") or "").strip()
        try:
            full = safe_join(os.path.abspath(dataset_training_root), rel)
        except Exception:
            abort(400)
        if not os.path.exists(full) or not os.path.isfile(full):
            abort(404)
        return send_file(full)

    @dataset_bp.post("/api/revert_classification", endpoint="api_revert_classification")
    @login_required
    @role_required("admin")
    def api_revert_classification():
        """
        Revierte una clasificacion moviendo la imagen al inbox de "limpias".

        Body esperado (JSON o form-data):
            - id: opcionalmente `scope:name`
            - scope: `negative|positive`
            - name: nombre del archivo

        Returns:
            Tuple `(json, status_code)` indicando exito o motivo del fallo.
        """
        payload = request.get_json(silent=True) or {}
        if not payload:
            payload = request.form.to_dict(flat=True)

        req_path = (payload.get("path") or "").strip()
        img_id = (payload.get("id") or "").strip()
        scope = (payload.get("scope") or "").strip().lower()
        name = (payload.get("name") or "").strip()

        if req_path:
            print("[DATASET_REVERT] requested path=" + str(req_path))
        elif img_id:
            print("[DATASET_REVERT] requested id=" + str(img_id))

        if img_id and (":" in img_id) and (not scope or not name):
            try:
                scope, name = img_id.split(":", 1)
                scope = (scope or "").strip().lower()
                name = (name or "").strip()
            except Exception:
                pass

        src: str | None = None
        if req_path and (not scope or not name):
            try:
                full = safe_join(os.path.abspath(dataset_training_root), req_path)
            except Exception:
                return jsonify({"status": "error", "message": "Ruta inválida."}), 400
            full_abs = os.path.abspath(full)
            neg_abs = os.path.abspath(dataset_negative_dir)
            pos_abs = os.path.abspath(dataset_positive_pending_dir)
            if full_abs.startswith(neg_abs + os.sep):
                scope = "negative"
                name = os.path.basename(full_abs)
                src = full_abs
            elif full_abs.startswith(pos_abs + os.sep):
                scope = "positive"
                name = os.path.basename(full_abs)
                src = full_abs
            else:
                return jsonify({"status": "error", "message": "Ruta fuera de directorios permitidos."}), 400

        if scope not in {"negative", "positive"} or not name:
            return jsonify({"status": "error", "message": "Identificador inválido."}), 400

        if src is None:
            src_dir = dataset_negative_dir if scope == "negative" else dataset_positive_pending_dir
            src = os.path.join(src_dir, name)
        if not os.path.exists(src) or not os.path.isfile(src):
            return jsonify({"status": "error", "message": "Imagen no encontrada."}), 404

        dest = _unique_dest_path(dataset_limpias_inbox_dir, name)
        print("[DATASET_REVERT] src=" + str(src))
        print("[DATASET_REVERT] dst=" + str(dest))
        try:
            shutil.move(src, dest)
        except Exception as e:
            print("[DATASET_REVERT][ERROR]", str(e) or e.__class__.__name__)
            return jsonify({"status": "error", "message": f"No se pudo revertir: {str(e)}"}), 500

        return jsonify({"status": "success", "moved_to": dest}), 200

