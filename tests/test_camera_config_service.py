from __future__ import annotations

from dataclasses import dataclass

from src.services.camera_config_service import CameraConfigService


class _Session:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1


class _DB:
    def __init__(self):
        self.session = _Session()


class _Query:
    def __init__(self, first_obj):
        self._first = first_obj

    def order_by(self, _arg):
        return self

    def first(self):
        return self._first


class _Id:
    @staticmethod
    def asc():
        return 1


@dataclass
class _Cfg:
    id: int | None = None
    camera_type: str | None = None
    rtsp_url: str | None = None
    rtsp_username: str | None = None
    rtsp_password: str | None = None
    onvif_host: str | None = None
    onvif_port: int | None = None
    onvif_username: str | None = None
    onvif_password: str | None = None


class _CameraConfig:
    id = _Id()
    query = _Query(None)

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_normalized_onvif_port():
    svc = CameraConfigService(db=_DB(), CameraConfig=_CameraConfig, rtsp_config={}, onvif_config={})
    assert svc.normalized_onvif_port(None) == 80
    assert svc.normalized_onvif_port(554) == 80
    assert svc.normalized_onvif_port(8000) == 8000


def test_sync_onvif_config_from_env_does_not_override_existing():
    db = _DB()
    svc = CameraConfigService(
        db=db,
        CameraConfig=_CameraConfig,
        rtsp_config={},
        onvif_config={"host": "h", "port": 80, "username": "u", "password": "p"},
    )
    cfg = _Cfg(onvif_host="persisted", onvif_port=8000, onvif_username="x", onvif_password="y")
    out = svc.sync_onvif_config_from_env(cfg)
    assert out.onvif_host == "persisted"
    assert out.onvif_port == 8000
    assert out.onvif_username == "x"
    assert out.onvif_password == "y"
    assert db.session.commits == 0


def test_sync_onvif_config_from_env_fills_missing_and_commits():
    db = _DB()
    svc = CameraConfigService(
        db=db,
        CameraConfig=_CameraConfig,
        rtsp_config={},
        onvif_config={"host": "h", "port": 80, "username": "u", "password": "p"},
    )
    cfg = _Cfg(onvif_host=None, onvif_port=None, onvif_username=None, onvif_password=None)
    out = svc.sync_onvif_config_from_env(cfg)
    assert out.onvif_host == "h"
    assert out.onvif_port == 80
    assert out.onvif_username == "u"
    assert out.onvif_password == "p"
    assert db.session.commits == 1


def test_get_or_create_camera_config_creates_defaults_when_missing():
    db = _DB()
    cam_cls = _CameraConfig
    cam_cls.query = _Query(None)
    svc = CameraConfigService(
        db=db,
        CameraConfig=cam_cls,
        rtsp_config={"url": "rtsp://x", "username": "ru", "password": "rp"},
        onvif_config={"host": "h", "port": 80, "username": "u", "password": "p"},
    )
    cfg = svc.get_or_create_camera_config()
    assert getattr(cfg, "camera_type") == "fixed"
    assert getattr(cfg, "rtsp_url") == "rtsp://x"
    assert getattr(cfg, "onvif_host") == "h"
    assert db.session.commits == 1
    assert db.session.added


def test_get_or_create_camera_config_returns_existing():
    existing = _Cfg(onvif_host=None, onvif_port=None, onvif_username=None, onvif_password=None)
    db = _DB()
    cam_cls = _CameraConfig
    cam_cls.query = _Query(existing)
    svc = CameraConfigService(
        db=db,
        CameraConfig=cam_cls,
        rtsp_config={},
        onvif_config={"host": "h", "port": 80, "username": "u", "password": "p"},
    )
    out = svc.get_or_create_camera_config()
    # debe completar y commitear por changed=True
    assert out.onvif_host == "h"
    assert db.session.commits == 1

