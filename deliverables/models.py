from __future__ import annotations

"""Modelos SQLAlchemy del prototipo RPAS Micro."""

from datetime import datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


class User(db.Model, UserMixin):
    """Usuario del sistema (admin/operator) para acceso al dashboard."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="operator")  # admin | operator
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def set_password(self, password: str) -> None:
        """Genera y asigna hash seguro de contraseña."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Verifica una contraseña contra el hash almacenado."""
        return check_password_hash(self.password_hash, password)


class CameraConfig(db.Model):
    """Configuración persistida de cámara (RTSP + ONVIF)."""

    __tablename__ = "camera_config"

    id = db.Column(db.Integer, primary_key=True)

    # fixed | ptz
    camera_type = db.Column(db.String(10), nullable=False, default="fixed")

    # RTSP
    rtsp_url = db.Column(db.String(500), nullable=True)
    rtsp_username = db.Column(db.String(120), nullable=True)
    rtsp_password = db.Column(db.String(120), nullable=True)

    # ONVIF
    onvif_host = db.Column(db.String(120), nullable=True)
    onvif_port = db.Column(db.Integer, nullable=False, default=80)
    onvif_username = db.Column(db.String(120), nullable=True)
    onvif_password = db.Column(db.String(120), nullable=True)

    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def effective_rtsp_url(self) -> str | None:
        """
        Devuelve una URL RTSP usable.

        - Si `rtsp_url` ya incluye credenciales, se respeta.
        - Si no incluye, se inyectan `rtsp_username`/`rtsp_password` cuando existan.
        """
        if not self.rtsp_url:
            return None
        if "://" not in self.rtsp_url:
            return self.rtsp_url

        # Si ya incluye @, asumimos que ya trae credenciales.
        if "@" in self.rtsp_url:
            return self.rtsp_url

        if self.rtsp_username and self.rtsp_password:
            scheme, rest = self.rtsp_url.split("://", 1)
            return f"{scheme}://{self.rtsp_username}:{self.rtsp_password}@{rest}"

        return self.rtsp_url
