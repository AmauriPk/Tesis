from __future__ import annotations

import os

import pytest

from src.routes.media import _safe_join as safe_join, _safe_rel_path as safe_rel_path


def test_safe_rel_path_normalizes_and_strips():
    assert safe_rel_path("static/evidence/a.jpg") == "static/evidence/a.jpg"
    assert safe_rel_path("/static/evidence/a.jpg") == "static/evidence/a.jpg"
    assert safe_rel_path("static\\evidence\\a.jpg") == "static/evidence/a.jpg"


def test_safe_rel_path_blocks_traversal():
    with pytest.raises(ValueError):
        safe_rel_path("../.env")
    with pytest.raises(ValueError):
        safe_rel_path("static/evidence/../../.env")


def test_safe_join_inside_base(tmp_path):
    base = str(tmp_path)
    full = safe_join(base, "static/evidence/a.jpg")
    assert os.path.abspath(full).startswith(os.path.abspath(base) + os.sep)


def test_safe_join_blocks_escape(tmp_path):
    base = str(tmp_path)
    with pytest.raises(ValueError):
        safe_join(base, "../.env")

