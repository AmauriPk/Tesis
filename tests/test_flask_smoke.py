from __future__ import annotations

import os
from dataclasses import dataclass

import pytest


def _make_role_required():
    def role_required(*roles: str):
        def decorator(fn):
            def wrapper(*args, **kwargs):
                # En smoke tests no validamos RBAC real; solo permitimos ejecutar la ruta.
                return fn(*args, **kwargs)

            wrapper.__name__ = fn.__name__
            return wrapper

        return decorator

    return role_required


class _FakeQuery:
    def filter_by(self, **kwargs):
        return self

    def first(self):
        return None


@dataclass
class _FakeUser:
    id: str
    username: str
    role: str

    # Flask-Login expects these.
    is_authenticated: bool = True
    is_active: bool = True
    is_anonymous: bool = False

    def get_id(self):
        return str(self.id)

    def check_password(self, _password: str) -> bool:
        return False


class _UserModel:
    query = _FakeQuery()


@pytest.fixture(scope="session")
def flask_app():
    from flask import Flask
    from flask_login import LoginManager

    # Asegurar que Flask no intente resolver templates desde ubicaciones extrañas.
    app = Flask("siran_test", root_path=os.getcwd(), template_folder="templates", static_folder="static")
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id: str):
        if user_id == "admin":
            return _FakeUser(id="admin", username="admin", role="admin")
        if user_id == "operator":
            return _FakeUser(id="operator", username="operator", role="operator")
        return None

    role_required = _make_role_required()

    # Blueprints "ligeros" (sin cv2/ultralytics).
    from src.routes.auth import auth_bp, init_auth_routes
    from src.routes.dashboard import dashboard_bp, init_dashboard_routes
    from src.routes.events import events_bp, init_events_routes
    from src.routes.dataset import dataset_bp, init_dataset_routes
    from src.routes.model_params import model_params_bp, init_model_params_routes
    from src.routes.ptz_manual import ptz_manual_bp, init_ptz_manual_routes
    from src.routes.automation import automation_bp, init_automation_routes
    from src.routes.media import media_bp, init_media_routes

    # ===== deps stubs =====
    class _DummyLiveReader:
        def get_status(self):
            return {"last_frame_age_s": 999.0}

    class _DummyLiveProcessor:
        def mjpeg_generator(self):
            # No ejecutar streaming real en tests.
            yield b""

    class _DummyPTZWorker:
        def enqueue_move(self, *args, **kwargs):
            return None

        def enqueue_direction(self, *args, **kwargs):
            return None

        def enqueue_stop(self, *args, **kwargs):
            return None

    def _get_metrics_db_path_abs() -> str:
        # DB inexistente => endpoints deben responder controlado (200 con ok/empty) o redirigir por login.
        return os.path.abspath("nonexistent_detections.db")

    def _ensure_detection_events_schema(_con):
        return None

    def _parse_iso_ts_to_epoch(_s: str):
        return None

    def _safe_join(_base_dir: str, rel_path: str) -> str:
        # Dataset endpoints no se ejercen en profundidad; solo se registran.
        return os.path.abspath(os.path.join(os.getcwd(), rel_path))

    def _get_or_create_camera_config():
        return object()

    def _leer_config_camara():
        return False

    def _get_configured_camera_type():
        return "fixed"

    def _update_model_params(**_kwargs):
        return {"confidence_threshold": 0.6, "persistence_frames": 3, "iou_threshold": 0.45}

    def _get_model_params():
        return {"confidence_threshold": 0.6, "persistence_frames": 3, "iou_threshold": 0.45}

    def _is_camera_configured_ptz():
        return False

    def _ptz_discovered_capable():
        return False

    def _is_ptz_ready_for_manual():
        return False

    def _normalized_onvif_port(p):
        return int(p or 80)

    def _clamp(v, lo, hi):
        return float(max(lo, min(hi, float(v))))

    def _get_auto_tracking_enabled():
        return False

    def _set_auto_tracking_enabled(_v: bool):
        return None

    def _get_inspection_mode_enabled():
        return False

    def _set_inspection_mode_enabled(_v: bool):
        return None

    def _is_ptz_ready_for_automation():
        return False

    # ===== init + register =====
    init_dashboard_routes(
        role_required=role_required,
        state_lock=_FakeLock(),
        current_detection_state={"status": "ok"},
        get_live_processor=lambda: _DummyLiveProcessor(),
        get_live_reader=lambda: _DummyLiveReader(),
        get_or_create_camera_config=_get_or_create_camera_config,
        leer_config_camara=_leer_config_camara,
        get_configured_camera_type=_get_configured_camera_type,
    )
    app.register_blueprint(dashboard_bp)

    init_auth_routes(User=_UserModel, FLASK_CONFIG={"debug": True})
    app.register_blueprint(auth_bp)

    init_events_routes(
        app_root_path=os.getcwd(),
        storage_config={},
        evidence_dir=os.path.join("static", "evidence"),
        role_required=role_required,
        get_metrics_db_path_abs=_get_metrics_db_path_abs,
        ensure_detection_events_schema=_ensure_detection_events_schema,
        parse_iso_ts_to_epoch=_parse_iso_ts_to_epoch,
    )
    app.register_blueprint(events_bp)

    init_dataset_routes(
        role_required=role_required,
        safe_join=_safe_join,
        dataset_recoleccion_folder=os.path.join(os.getcwd(), "dataset_recoleccion"),
        dataset_training_root=os.path.join(os.getcwd(), "dataset_entrenamiento"),
        dataset_negative_dir=os.path.join(os.getcwd(), "dataset_entrenamiento", "train", "images"),
        dataset_positive_pending_dir=os.path.join(os.getcwd(), "dataset_entrenamiento", "pending", "images"),
        dataset_limpias_inbox_dir=os.path.join(os.getcwd(), "dataset_recoleccion", "limpias"),
    )
    app.register_blueprint(dataset_bp)

    init_model_params_routes(role_required=role_required, update_model_params=_update_model_params)
    app.register_blueprint(model_params_bp)

    init_media_routes(role_required=role_required)
    app.register_blueprint(media_bp)

    init_ptz_manual_routes(
        app=app,
        role_required=role_required,
        ptz_worker=_DummyPTZWorker(),
        state_lock=_FakeLock(),
        tracking_target_state={"has_target": False, "bbox": None, "updated_at": 0.0},
        tracking_target_lock=_FakeLock(),
        is_camera_configured_ptz=_is_camera_configured_ptz,
        ptz_discovered_capable=_ptz_discovered_capable,
        is_ptz_ready_for_manual=_is_ptz_ready_for_manual,
        get_or_create_camera_config=_get_or_create_camera_config,
        normalized_onvif_port=_normalized_onvif_port,
        clamp=_clamp,
        get_auto_tracking_enabled=_get_auto_tracking_enabled,
        set_auto_tracking_enabled=_set_auto_tracking_enabled,
    )
    app.register_blueprint(ptz_manual_bp)

    init_automation_routes(
        role_required=role_required,
        state_lock=_FakeLock(),
        tracking_target_state={"has_target": False, "bbox": None, "updated_at": 0.0},
        tracking_target_lock=_FakeLock(),
        ptz_worker=_DummyPTZWorker(),
        is_camera_configured_ptz=_is_camera_configured_ptz,
        is_ptz_ready_for_automation=_is_ptz_ready_for_automation,
        get_auto_tracking_enabled=_get_auto_tracking_enabled,
        set_auto_tracking_enabled=_set_auto_tracking_enabled,
        get_inspection_mode_enabled=_get_inspection_mode_enabled,
        set_inspection_mode_enabled=_set_inspection_mode_enabled,
        current_detection_state={"status": "ok"},
    )
    app.register_blueprint(automation_bp)

    # Nota: No registramos `admin_camera` ni `analysis` aquí porque importan dependencias pesadas (cv2/ultralytics).
    return app


class _FakeLock:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.fixture()
def client(flask_app):
    return flask_app.test_client()


def _login_as(client, user_id: str):
    with client.session_transaction() as sess:
        sess["_user_id"] = user_id
        sess["_fresh"] = True


def test_get_login_200(client):
    r = client.get("/login")
    assert r.status_code == 200


def test_post_login_invalid_user_does_not_crash(client):
    r = client.post("/login", data={"username": "nope", "password": "bad"})
    assert r.status_code == 200


def test_logout_without_login_is_controlled(client):
    r = client.get("/logout", follow_redirects=False)
    assert r.status_code in {302, 401, 403}


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/"),
        ("GET", "/api/camera_status"),
        ("GET", "/detection_status"),
        ("GET", "/api/recent_alerts?limit=1"),
        ("GET", "/api/recent_detection_events?limit=1"),
        ("GET", "/api/detection_summary"),
        ("POST", "/api/update_model_params"),
        ("POST", "/ptz_move"),
        ("POST", "/api/ptz_stop"),
        ("GET", "/api/auto_tracking"),
        ("GET", "/api/inspection_mode"),
        ("GET", "/media/static/evidence/a.jpg"),
    ],
)
def test_protected_routes_redirect_without_login(client, method, path):
    r = client.open(path, method=method, follow_redirects=False)
    # login_required suele redirigir al login.
    assert r.status_code in {302, 401, 403}


def test_media_traversal_never_returns_200_even_when_logged_in(client):
    _login_as(client, "operator")
    r = client.get("/media/../.env", follow_redirects=False)
    assert r.status_code != 200


def test_url_map_contains_expected_rules(flask_app):
    rules = {r.rule for r in flask_app.url_map.iter_rules()}
    expected = {
        "/login",
        "/logout",
        "/",
        "/api/camera_status",
        "/detection_status",
        "/api/recent_alerts",
        "/api/recent_detection_events",
        "/api/detection_summary",
        "/api/update_model_params",
        "/ptz_move",
        "/api/ptz_stop",
        "/api/auto_tracking",
        "/api/inspection_mode",
        "/media/<path:rel_path>",
    }
    missing = expected - rules
    assert not missing
