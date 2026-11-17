"""前端产物托管回归：public 根级资源必须回真文件，不能被 SPA 回退吞成 HTML。

三个回归点：
1. `/logo.svg`、`/hero-kitchen.jpg` 回真实文件与正确 Content-Type（否则侧栏碎图、首页 hero 丢图）
2. SPA 深链（/stats）仍回 index.html，且 index.html 不缓存、hash 产物长缓存
3. 目录穿越拿不到 dist 外的文件；根级静态资源不计限流
"""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from app import config
from app.core import webdist

INDEX_HTML = "<!doctype html><title>食光</title>"
LOGO_SVG = '<svg xmlns="http://www.w3.org/2000/svg"></svg>'


@pytest.fixture()
def web_dist(tmp_path, monkeypatch):
    """伪造一份 Vite 产物：根级 public 文件 + assets/ + index.html。"""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (dist / "logo.svg").write_text(LOGO_SVG, encoding="utf-8")
    (dist / "hero-kitchen.jpg").write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")
    (dist / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    monkeypatch.setattr(config, "WEB_DIST_DIR", dist)
    return dist


@pytest.fixture()
def client(web_dist, app_db, monkeypatch):
    monkeypatch.setattr(config, "BASIC_AUTH_SPEC", "")
    monkeypatch.setattr(config, "RATE_LIMIT_PER_MIN", 0)
    from app.main import create_app

    return TestClient(create_app())


def test_public_root_files_are_served_as_files(client):
    """public 根级资源回真文件 + 正确 MIME，不是 index.html。"""
    logo = client.get("/logo.svg")
    assert logo.status_code == 200
    assert logo.headers["content-type"].startswith("image/svg+xml")
    assert logo.text == LOGO_SVG

    hero = client.get("/hero-kitchen.jpg")
    assert hero.status_code == 200
    assert hero.headers["content-type"] == "image/jpeg"
    assert hero.content.startswith(b"\xff\xd8")


def test_spa_deep_link_still_returns_index(client):
    """前端路由深链仍回 index.html，且不缓存（发新版要立刻生效）。"""
    response = client.get("/stats")
    assert response.status_code == 200
    assert response.text == INDEX_HTML
    assert response.headers["cache-control"] == "no-cache"


def test_cache_headers_split_hash_assets_and_public_files(client):
    """hash 产物 immutable；根级公共文件短缓存。"""
    asset = client.get("/assets/index-abc123.js")
    assert asset.status_code == 200
    assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"

    logo = client.get("/logo.svg")
    assert logo.headers["cache-control"] == "public, max-age=3600"


def test_missing_file_falls_back_to_index(client):
    """不存在的路径不 404，交给前端路由。"""
    response = client.get("/no-such-file.png")
    assert response.status_code == 200
    assert response.text == INDEX_HTML


def test_static_file_rejects_traversal(web_dist):
    """dist 外的文件一律解析不到（防目录穿越读源码/配置）。"""
    outside = web_dist.parent / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    assert webdist.static_file("../secret.txt") is None
    assert webdist.static_file("/../secret.txt") is None
    assert webdist.static_file("assets/../../secret.txt") is None
    assert webdist.static_file("") is None
    assert webdist.static_file("/api/health") is None
    assert webdist.static_file("assets") is None  # 目录不是文件
    assert webdist.static_file("logo.svg") == web_dist / "logo.svg"


def test_public_files_do_not_consume_rate_limit(web_dist, app_db, monkeypatch):
    """首页一次加载会带 logo/hero，这些静态请求不能把 API 额度吃掉。"""
    monkeypatch.setattr(config, "BASIC_AUTH_SPEC", "demo:secret")
    monkeypatch.setattr(config, "RATE_LIMIT_PER_MIN", 2)
    from app.main import create_app

    token = base64.b64encode(b"demo:secret").decode("ascii")
    headers = {"Authorization": f"Basic {token}"}
    with TestClient(create_app()) as limited:
        for _ in range(5):
            assert limited.get("/logo.svg", headers=headers).status_code == 200
            assert limited.get("/hero-kitchen.jpg", headers=headers).status_code == 200

        assert limited.get("/api/inventory?status=active", headers=headers).status_code == 200
        assert limited.get("/api/inventory?status=active", headers=headers).status_code == 200
        assert limited.get("/api/inventory?status=active", headers=headers).status_code == 429
