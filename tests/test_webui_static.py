"""Tests for built WebUI static assets."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "src" / "superhaojun" / "webui" / "static"


def test_static_index_references_favicon() -> None:
    index_html = (STATIC_DIR / "index.html").read_text()

    assert 'rel="icon"' in index_html
    assert "/favicon.svg" in index_html


def test_static_favicon_asset_exists() -> None:
    assert (STATIC_DIR / "favicon.svg").exists()
