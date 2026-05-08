from __future__ import annotations

import base64
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Callable
from urllib.parse import urlparse

import cv2
from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required

admin_camera_bp = Blueprint("admin_camera", __name__)

_deps: dict[str, Any] = {}
_routes_initialized = False


def _get_dep(key: str):
    try:
        return _deps[key]
    except KeyError as exc:
        raise RuntimeError(f"Dependencia faltante en admin_camera: {key}") from exc


def init_admin_camera_routes(**deps: Any) -> None:
    """
    Inicializa dependencias y registra rutas admin de cámara en el Blueprint.

    Evita imports circulares con `app.py` al recibir referencias explícitas.
    """
    global _deps, _routes_initialized
    _deps = dict(deps or {})

    if _routes_initialized:
        return
    _routes_initialized = True

    role_required = _get_dep("role_required")

    db = _get_dep("db")
    get_or_create_camera_config = _get_dep("get_or_create_camera_config")
    guardar_config_camara = _get_dep("guardar_config_camara")
    normalized_onvif_port: Callable[[int | None], int] = _get_dep("normalized_onvif_port")
    PTZController = _get_dep("PTZController")
    probe_onvif_ptz_capability = _get_dep("probe_onvif_ptz_capability")
    get_model_params = _get_dep("get_model_params")

    def _humanize_onvif_error(err: Exception) -> str:
        msg = (str(err) or err.__class__.__name__).strip()
        low = msg.lower()

        if "not authorized" in low or "unauthorized" in low or "authentication" in low or "auth" in low:
            return "Error de Autenticación: credenciales incorrectas o permisos insuficientes."

        if "timed out" in low or "timeout" in low:
            return "Host inalcanzable (Timeout)."
        if "name or service not known" in low or "no such host" in low or "could not resolve" in low:
            return "Host inválido: no se pudo resolver DNS."
        if "connection refused" in low:
            return "Conexión rechazada: puerto ONVIF cerrado o incorrecto."
        if "network is unreachable" in low:
            return "Red inalcanzable: revisa conectividad y rutas."

        if "wsdl" in low:
            return "Error ONVIF/WSDL: endpoint no compatible o respuesta inválida."

        return msg

    def _detect_ptz_capability(host: str, port: int, username: str, password: str) -> bool:
        """Conecta por ONVIF y determina si expone PTZ (sin movimientos)."""
        from onvif import ONVIFCamera  # type: ignore

        cam = ONVIFCamera(host, int(port), username, password)

        try:
            dev = cam.create_devicemgmt_service()
            caps = dev.GetCapabilities({"Category": "All"})
            ptz_caps = getattr(caps, "PTZ", None)
            xaddr = getattr(ptz_caps, "XAddr", None) if ptz_caps is not None else None
            if xaddr:
                return True
        except Exception:
            pass

        try:
            ptz = cam.create_ptz_service()
            _ = ptz.GetServiceCapabilities()
            return True
        except Exception:
            return False

    def _build_rtsp_url(rtsp_url: str, username: str | None, password: str | None) -> str:
        raw = (rtsp_url or "").strip()
        if not raw:
            return ""
        try:
            u = urlparse(raw)
        except Exception:
            return raw

        if (u.scheme or "").lower() != "rtsp":
            return raw

        # Si ya trae usuario, no tocar.
        if u.username:
            return raw

        user = (username or "").strip()
        pwd = password or ""
        if not user or not pwd:
            return raw

        host = u.hostname or ""
        if not host:
            return raw

        netloc = f"{user}:{pwd}@{host}"
        if u.port:
            netloc += f":{u.port}"

        rebuilt = u._replace(netloc=netloc)
        return rebuilt.geturl()

    def _grab_rtsp_snapshot_b64(rtsp_url: str) -> str:
        cap = cv2.VideoCapture(rtsp_url)
        try:
            if not cap.isOpened():
                raise RuntimeError("No se pudo abrir el stream RTSP.")
            ret, frame = cap.read()
            if not ret or frame is None:
                raise RuntimeError("No se pudo leer un fotograma del RTSP.")
        finally:
            try:
                cap.release()
            except Exception:
                pass

        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            raise RuntimeError("No se pudo codificar el fotograma (JPEG).")
        return base64.b64encode(buf.tobytes()).decode("ascii")

    @admin_camera_bp.get("/admin_dashboard", endpoint="admin_dashboard")
    @login_required
    @role_required("admin")
    def admin_dashboard():
        """Dashboard exclusivo para Administrador (config HW + parámetros IA)."""
        cfg = get_or_create_camera_config()
        params = get_model_params()
        return render_template("admin.html", cfg=cfg, model_params=params)

    @admin_camera_bp.route("/admin/camera", methods=["GET", "POST"], endpoint="admin_camera")
    @login_required
    @role_required("admin")
    def admin_camera():
        """Panel admin para editar RTSP/ONVIF (persistido en DB)."""
        cfg = get_or_create_camera_config()

        if request.method == "POST":
            cfg.camera_type = (request.form.get("camera_type") or "fixed").lower()
            try:
                guardar_config_camara((cfg.camera_type or "fixed").strip().lower() == "ptz")
            except Exception:
                pass

            cfg.rtsp_url = (request.form.get("rtsp_url") or "").strip() or None
            cfg.rtsp_username = (request.form.get("rtsp_username") or "").strip() or None
            cfg.rtsp_password = (request.form.get("rtsp_password") or "").strip() or None

            cfg.onvif_host = (request.form.get("onvif_host") or "").strip() or None
            try:
                cfg.onvif_port = int(request.form.get("onvif_port") or 80)
            except Exception:
                cfg.onvif_port = 80
            cfg.onvif_username = (request.form.get("onvif_username") or "").strip() or None
            cfg.onvif_password = (request.form.get("onvif_password") or "").strip() or None

            db.session.commit()
            # Autodescubrimiento (no confiar en camera_type).
            probe_onvif_ptz_capability()
            flash("Configuración de cámara guardada.", "success")
            return redirect(url_for("admin_camera.admin_dashboard"))

        return redirect(url_for("admin_camera.admin_dashboard"))

    @admin_camera_bp.route("/admin/camera/test", methods=["POST"], endpoint="admin_camera_test")
    @login_required
    @role_required("admin")
    def admin_camera_test():
        """Prueba rápida de conexión ONVIF (requiere `onvif-zeep`)."""
        cfg = get_or_create_camera_config()
        if not cfg.onvif_host or not cfg.onvif_username or not cfg.onvif_password:
            return jsonify({"ok": False, "error": "Completa host/usuario/contraseña ONVIF."}), 400
        try:
            port = normalized_onvif_port(cfg.onvif_port)
            if int(cfg.onvif_port or 0) == 554:
                print("[ONVIF][WARN] onvif_port=554 parece RTSP; usando 80 para ONVIF.")
            print(
                "[PTZ_CFG]",
                {
                    "host": str(cfg.onvif_host or ""),
                    "port": int(port),
                    "username": str(cfg.onvif_username or ""),
                    "password_configurada": bool(cfg.onvif_password),
                    "password_len": len(cfg.onvif_password) if cfg.onvif_password else 0,
                },
            )
            controller = PTZController(cfg.onvif_host, int(port), cfg.onvif_username, cfg.onvif_password)
            return jsonify(controller.test_connection())
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @admin_camera_bp.post("/api/test_connection", endpoint="api_test_connection")
    @login_required
    @role_required("admin")
    def api_test_connection():
        """
        Prueba conectividad ONVIF y (opcionalmente) RTSP, sin bloquear el request indefinidamente.
        """
        payload = request.get_json(silent=True) or {}
        if not payload:
            payload = request.form.to_dict(flat=True)

        host = (payload.get("host") or payload.get("ip") or payload.get("onvif_host") or "").strip()
        port_raw = payload.get("port") or payload.get("onvif_port") or 80
        username = (payload.get("username") or payload.get("user") or payload.get("onvif_username") or "").strip()
        password = payload.get("password") or payload.get("onvif_password") or ""
        rtsp_url = (payload.get("rtsp_url") or "").strip()
        rtsp_username = (payload.get("rtsp_username") or "").strip()
        rtsp_password = payload.get("rtsp_password") or ""

        if not host:
            return jsonify({"status": "error", "message": "Host requerido."}), 400
        try:
            port = int(port_raw)
            if port <= 0 or port > 65535:
                raise ValueError("out_of_range")
        except Exception:
            return jsonify({"status": "error", "message": "Puerto ONVIF inválido."}), 400
        if not username or not password:
            return jsonify({"status": "error", "message": "Credenciales ONVIF incompletas."}), 400

        timeout_s = 6.0
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(_detect_ptz_capability, host, int(port), username, password)
                is_ptz = bool(fut.result(timeout=timeout_s))

            # Snapshot RTSP (no bloqueante, no consume recursos).
            snapshot_b64: str | None = None
            warning: str | None = None
            if not rtsp_url:
                warning = "ONVIF OK, pero no se proporciono URL RTSP para snapshot."
            else:
                effective_rtsp = _build_rtsp_url(rtsp_url, rtsp_username, rtsp_password)
                snapshot_timeout_s = 7.0
                try:
                    with ThreadPoolExecutor(max_workers=1) as ex2:
                        fut2 = ex2.submit(_grab_rtsp_snapshot_b64, effective_rtsp)
                        snapshot_b64 = fut2.result(timeout=snapshot_timeout_s)
                except FuturesTimeoutError:
                    warning = "ONVIF OK, pero RTSP fallo (Timeout)."
                except Exception as e_rtsp:
                    warning = f"ONVIF OK, pero RTSP fallo: {str(e_rtsp) or e_rtsp.__class__.__name__}"

            # Resultado del autodescubrimiento (Admin) => persistir en disco.
            try:
                guardar_config_camara(bool(is_ptz))
            except Exception:
                pass

            # Sincronizar con DB para evitar discrepancias (fuente secundaria).
            try:
                cfg = get_or_create_camera_config()
                cfg.camera_type = "ptz" if bool(is_ptz) else "fixed"
                db.session.commit()
            except Exception:
                pass
            payload_ok: dict[str, Any] = {"status": "success", "is_ptz": is_ptz, "snapshot_b64": snapshot_b64}
            if warning:
                payload_ok["warning"] = warning
            return jsonify(payload_ok), 200
        except FuturesTimeoutError:
            return jsonify({"status": "error", "message": "Host inalcanzable (Timeout)."}), 400
        except Exception as e:
            msg = _humanize_onvif_error(e)
            low = (str(e) or "").lower()
            if "no module named" in low and "onvif" in low:
                msg = "Dependencia faltante: instala onvif-zeep para habilitar el test ONVIF."
            return jsonify({"status": "error", "message": msg}), 400
