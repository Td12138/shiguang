"""演示站防护中间件（契约 §10）：限流顺序、静态资源豁免、畸形 Basic 凭据。

三个回归点：
1. 先限流后认证：匿名连错也必须被 429 挡住，否则限流对爆破无效
2. 首页 / index.html / assets 不计限流：一次刷新首页 20+ 请求不能把自己打成 429
3. 非 ASCII / 畸形 Basic 头一律 401，不能因 ``compare_digest`` 抛 TypeError 变 500
"""

from __future__ import annotations

import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import config
from app.core.security import SecurityMiddleware

USER = "demo"
PASSWORD = "secret"


def _basic(user: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


@pytest.fixture()
def make_client(monkeypatch):
    """按需构造带 SecurityMiddleware 的最小应用（限流/认证参数在构造前生效）。"""

    def _build(*, auth: bool = True, limit: int = 0) -> TestClient:
        monkeypatch.setattr(config, "BASIC_AUTH_SPEC", f"{USER}:{PASSWORD}" if auth else "")
        monkeypatch.setattr(config, "RATE_LIMIT_PER_MIN", limit)

        app = FastAPI()
        app.add_middleware(SecurityMiddleware)

        @app.get("/api/health")
        def health() -> dict:
            return {"ok": True}

        @app.get("/api/data")
        def data() -> dict:
            return {"ok": True}

        @app.get("/")
        def root() -> dict:
            return {"page": "index"}

        @app.get("/index.html")
        def index() -> dict:
            return {"page": "index"}

        @app.get("/assets/{name}")
        def asset(name: str) -> dict:
            return {"asset": name}

        return TestClient(app)

    return _build


def test_rate_limit_runs_before_auth(make_client):
    """5 次错误认证后第 6 次是 429（不是无限 401）。"""
    client = make_client(auth=True, limit=5)
    bad = _basic(USER, "wrong")

    for _ in range(5):
        response = client.get("/api/data", headers=bad)
        assert response.status_code == 401, "前 5 次应正常返回认证失败"

    blocked = client.get("/api/data", headers=bad)
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "rate_limited"


def test_unicode_and_malformed_credentials_are_401_not_500(make_client):
    """非 ASCII / 非法 base64 / 非 UTF-8 凭据都只能 401，不能 500。"""
    client = make_client(auth=True, limit=0)

    unicode_header = _basic("演示用户", "口令")
    strange = base64.b64encode(b"\xff\xfe\x00bad").decode("ascii")
    for header in (
        unicode_header,
        {"Authorization": "Basic !!!not-base64!!!"},
        {"Authorization": f"Basic {strange}"},
        {"Authorization": "Bearer token"},
        {},
    ):
        response = client.get("/api/data", headers=header)
        assert response.status_code == 401, header
        assert response.json()["code"] == "unauthorized"


def test_static_assets_do_not_consume_rate_limit(make_client):
    """首页 / index.html / assets 不计入限流；API 仍按额度计数。"""
    client = make_client(auth=True, limit=2)
    good = _basic(USER, PASSWORD)

    for path in ("/", "/index.html", "/assets/app.js", "/assets/index.css"):
        for _ in range(5):
            assert client.get(path, headers=good).status_code == 200

    assert client.get("/api/data", headers=good).status_code == 200
    assert client.get("/api/data", headers=good).status_code == 200
    assert client.get("/api/data", headers=good).status_code == 429


def test_health_is_exempt_from_rate_limit(make_client):
    """健康检查永远可用（线上探活不能被限流打掉）。"""
    client = make_client(auth=False, limit=1)

    for _ in range(10):
        assert client.get("/api/health").status_code == 200

    assert client.get("/api/data").status_code == 200
    assert client.get("/api/data").status_code == 429
