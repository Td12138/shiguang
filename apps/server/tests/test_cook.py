"""备菜流水线（契约 §6.12）：真实步骤、并行关系、引用、规则版兜底、404。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.domain import cook
from app.domain.tools_registry import AppError


class CookProvider:
    """只回 chat_json 的最小 provider（阶段固定是 cook）。"""

    name = "fake-cook"

    def __init__(self, payload=None, *, fail: bool = False) -> None:
        self.payload = payload
        self.fail = fail
        self.calls = 0

    async def chat_json(self, messages, *, schema=None, timeout: float = 60) -> dict:
        self.calls += 1
        if self.fail:
            raise RuntimeError("cook boom")
        if isinstance(self.payload, list):
            return self.payload[min(self.calls - 1, len(self.payload) - 1)]
        return self.payload or {}

    async def chat_text(self, messages, *, timeout: float = 60) -> str:
        return "（fake）"

    async def chat_vision(self, image_b64, mime, prompt, *, timeout: float = 90) -> dict:
        return {"items": []}

    def stream_chat(self, messages):
        async def _gen():  # pragma: no cover - 备菜不用流式
            if False:
                yield ""

        return _gen()


@pytest.fixture()
def client(app_db):
    from app.api import recipes as recipes_api

    app = FastAPI()
    app.include_router(recipes_api.router)

    @app.exception_handler(AppError)
    async def _handler(_request, exc: AppError):
        return JSONResponse(
            {"code": exc.code, "message": exc.message, "detail": exc.detail},
            status_code=exc.status,
        )

    return TestClient(app)


@pytest.fixture()
def two_recipes(add_recipe):
    add_recipe(
        "r_tomato",
        "番茄炒蛋",
        ingredients=[{"name": "番茄"}, {"name": "鸡蛋"}],
        steps=[
            "番茄切块，鸡蛋打散",
            "热锅倒蛋液炒成大块盛出",
            "下番茄炒出汁",
            "倒回鸡蛋翻匀出锅",
        ],
        minutes=10,
    )
    add_recipe(
        "r_soup",
        "紫菜蛋花汤",
        ingredients=[{"name": "紫菜"}, {"name": "鸡蛋"}],
        steps=["紫菜撕小片泡开", "烧一锅水", "淋入蛋液，撒葱花"],
        minutes=8,
    )


def _use(monkeypatch, provider):
    monkeypatch.setattr(cook, "resolve_provider", lambda injected=None, _p=provider: _p)


def test_rule_sequence_covers_both_recipes(client, two_recipes, monkeypatch):
    _use(monkeypatch, None)

    response = client.post(
        "/api/cook/sequence",
        json={"recipe_ids": ["r_tomato", "r_soup"], "start_at": "18:30"},
    )
    assert response.status_code == 200
    body = response.json()

    assert body["total_minutes"] >= 10, "总时长不得小于最长单菜（番茄炒蛋 10 分钟）"
    assert body["steps"], "规则版也要给出时间轴"
    actions = " ".join(step["action"] for step in body["steps"])
    assert "番茄" in actions and "紫菜" in actions, "两道菜的步骤都要在时间轴里"

    sources = {step["source"] for step in body["steps"]}
    assert sources == {"recipe:r_tomato", "recipe:r_soup"}
    for step in body["steps"]:
        assert step["locator"].startswith("步骤 ")
        assert step["at"]
        assert isinstance(step["minutes"], int)
        assert isinstance(step["parallel_with"], list)

    assert [step["order"] for step in body["steps"]] == list(
        range(1, len(body["steps"]) + 1)
    )
    assert body["steps"][0]["at"] == "18:30"
    assert any(step["parallel_with"] for step in body["steps"]), "多道菜要有并行关系"
    assert body["tips"]
    assert any("已降级" in warning for warning in body["warnings"])


def test_llm_sequence_passes_verify(client, two_recipes, monkeypatch):
    payload = {
        "steps": [
            {
                "order": 1,
                "at": "18:30",
                "action": "番茄切块，鸡蛋打散",
                "minutes": 3,
                "parallel_with": [2],
                "source": "recipe:r_tomato",
                "locator": "步骤 1",
            },
            {
                "order": 2,
                "at": "18:30",
                "action": "紫菜撕小片泡开",
                "minutes": 2,
                "parallel_with": [1],
                "source": "recipe:r_soup",
                "locator": "步骤 1",
            },
            {
                "order": 3,
                "at": "18:33",
                "action": "热锅倒蛋液炒成大块盛出",
                "minutes": 4,
                "parallel_with": [4],
                "source": "recipe:r_tomato",
                "locator": "步骤 2",
            },
            {
                "order": 4,
                "at": "18:33",
                "action": "烧一锅水",
                "minutes": 0,
                "parallel_with": [3],
                "source": "recipe:r_soup",
                "locator": "步骤 2",
            },
            {
                "order": 5,
                "at": "18:37",
                "action": "下番茄炒出汁",
                "minutes": 4,
                "parallel_with": [6],
                "source": "recipe:r_tomato",
                "locator": "步骤 3",
            },
            {
                "order": 6,
                "at": "18:37",
                "action": "淋入蛋液，撒葱花",
                "minutes": 3,
                "parallel_with": [5],
                "source": "recipe:r_soup",
                "locator": "步骤 3",
            },
            {
                "order": 7,
                "at": "18:41",
                "action": "倒回鸡蛋翻匀出锅",
                "minutes": 3,
                "parallel_with": [],
                "source": "recipe:r_tomato",
                "locator": "步骤 4",
            },
        ],
        "tips": ["先切好两样再开火"],
        "warnings": [],
    }
    provider = CookProvider(payload)
    _use(monkeypatch, provider)

    response = client.post(
        "/api/cook/sequence",
        json={"recipe_ids": ["r_tomato", "r_soup"], "start_at": "18:30"},
    )
    assert response.status_code == 200
    body = response.json()

    assert len(body["steps"]) == 7
    assert body["total_minutes"] >= 10
    assert body["tips"] == ["先切好两样再开火"]
    assert not any("已降级" in warning for warning in body["warnings"])
    assert body["steps"][0]["source"] == "recipe:r_tomato"
    assert body["steps"][0]["locator"] == "步骤 1"


def test_invalid_llm_output_degrades_to_rule_version(client, two_recipes, monkeypatch):
    bad = {
        "steps": [
            {
                "order": 1,
                "at": "18:30",
                "action": "随便编的步骤",
                "minutes": 5,
                "parallel_with": [],
                "source": "recipe:r_nope",
                "locator": "步骤 9",
            }
        ]
    }
    provider = CookProvider(bad)
    _use(monkeypatch, provider)

    body = client.post(
        "/api/cook/sequence",
        json={"recipe_ids": ["r_tomato", "r_soup"], "start_at": "18:30"},
    ).json()

    assert provider.calls >= 2, "结构不合法应重试一次"
    assert any("已降级" in warning for warning in body["warnings"])
    assert {step["source"] for step in body["steps"]} == {
        "recipe:r_tomato",
        "recipe:r_soup",
    }
    assert body["total_minutes"] >= 10


def test_provider_failure_degrades_to_rule_version(client, two_recipes, monkeypatch):
    _use(monkeypatch, CookProvider(fail=True))

    body = client.post(
        "/api/cook/sequence",
        json={"recipe_ids": ["r_tomato", "r_soup"], "start_at": "18:30"},
    ).json()

    assert body["steps"]
    assert any("已降级" in warning for warning in body["warnings"])
    assert body["total_minutes"] >= 10


def test_unknown_recipe_returns_404(client, two_recipes, monkeypatch):
    _use(monkeypatch, None)

    response = client.post("/api/cook/sequence", json={"recipe_ids": ["r_nope"]})
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "recipe_not_found"
    assert "r_nope" in body["message"]


def test_empty_recipe_ids_rejected(client, monkeypatch):
    _use(monkeypatch, None)
    response = client.post("/api/cook/sequence", json={"recipe_ids": []})
    assert response.status_code == 422


def test_bad_start_at_falls_back_with_warning(client, two_recipes, monkeypatch):
    _use(monkeypatch, None)

    body = client.post(
        "/api/cook/sequence",
        json={"recipe_ids": ["r_tomato"], "start_at": "晚上六点"},
    ).json()

    assert any("18:30" in warning for warning in body["warnings"])
    assert body["steps"][0]["at"] == "18:30"
