"""SSE 流式接口（契约 §6.15）：事件顺序、result 与非流式一致、失败不悬挂、断连中止。

三个关注点：
1. 事件严格是 ``step* → result → done``，step 与 agent_runs.steps 同名同顺序
2. ``result.payload`` 与非流式接口的响应体**字段集合一致**（同一份构建函数）
3. 模型不可用 / 流水线抛错时仍以 ``done`` 收尾，连接不悬挂
"""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.domain import inventory as inv
from app.domain import plan as plan_domain
from app.domain import recipes as recipes_domain
from app.domain.tools_registry import AppError

PLAN_STEPS = ["understand", "plan", "allocate", "compose", "verify"]
SUGGEST_STEPS = ["understand", "plan", "retrieve", "compose", "verify"]
STEP_FIELDS = {"type", "name", "status", "ms", "summary"}
MEAL_FIELDS = {"slot", "recipe_id", "title", "minutes", "uses", "missing", "citations", "reason"}
RECOMMENDATION_FIELDS = {
    "recipe_id",
    "title",
    "minutes",
    "reason",
    "missing",
    "citations",
    "score",
    "uses",
}


@pytest.fixture()
def client(app_db):
    from app.api import plan as plan_api
    from app.api import recipes as recipes_api

    app = FastAPI()
    for module in (recipes_api, plan_api):
        app.include_router(module.router)

    @app.exception_handler(AppError)
    async def _app_error_handler(_request, exc: AppError):  # 与 core 的错误体一致
        return JSONResponse(
            {"code": exc.code, "message": exc.message, "detail": exc.detail},
            status_code=exc.status,
        )

    return TestClient(app)


def _seed(add_item, add_recipe) -> None:
    add_item("西兰花", avg_grams=300.0, shelf_life_days=5)
    add_item("鸡蛋", avg_grams=60.0, shelf_life_days=10, unit="个")
    add_recipe(
        "r_broccoli",
        "蒜蓉西兰花",
        ingredients=[
            {"name": "西兰花", "qty": 1, "unit": "颗", "optional": False},
            {"name": "大蒜", "qty": 2, "unit": "瓣", "optional": False},
        ],
        steps=["切小朵", "蒜切末", "爆香", "翻炒调味"],
        minutes=15,
    )
    add_recipe(
        "r_egg",
        "西兰花炒鸡蛋",
        ingredients=[{"name": "西兰花", "qty": 1, "unit": "颗"}, {"name": "鸡蛋", "qty": 2, "unit": "个"}],
        steps=["焯水", "打蛋", "同炒"],
        minutes=10,
    )
    inv.add_items(
        {
            "items": [
                {
                    "name": "西兰花",
                    "qty": 1,
                    "expires_at": (inv.today() + timedelta(days=2)).isoformat(),
                },
                {"name": "鸡蛋", "qty": 6},
            ]
        }
    )


def _parse(raw: str) -> list[dict]:
    """SSE 文本 → 事件列表（只取 data: 行）。"""
    events = []
    for line in raw.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: "):]))
    return events


def _types(events: list[dict]) -> list[str]:
    return [event["type"] for event in events]


def test_plan_stream_events_and_payload(client, add_item, add_recipe, no_llm):
    _seed(add_item, add_recipe)

    with client.stream(
        "POST", "/api/plan/meals/stream", json={"days": 2, "servings": 1, "max_minutes": 30}
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        lines = [line for line in response.iter_lines() if line.startswith("data: ")]

    events = [json.loads(line[len("data: "):]) for line in lines]
    # 顺序：step* → result → done
    assert _types(events)[-2:] == ["result", "done"]
    assert _types(events)[-3] == "step"
    assert {event["type"] for event in events[:-2]} == {"step"}

    steps = [event for event in events if event["type"] == "step"]
    assert [step["name"] for step in steps] == PLAN_STEPS, "step 必须与 agent_runs.steps 同名同顺序"
    for step in steps:
        assert set(step) == STEP_FIELDS
        assert isinstance(step["ms"], int) and step["ms"] >= 0
        assert step["summary"], "每步都要有可读 summary，前端时间线才有内容"

    payload = events[-2]["payload"]
    non_stream = client.post(
        "/api/plan/meals", json={"days": 2, "servings": 1, "max_minutes": 30}
    ).json()
    assert set(payload) == set(non_stream), "result.payload 与非流式响应必须逐字段一致"
    assert set(payload["coverage"]) == set(non_stream["coverage"])
    assert set(payload["days"][0]) == set(non_stream["days"][0])
    assert set(payload["days"][0]["meals"][0]) == MEAL_FIELDS
    # 流式与非流式都真的把计划落了库（同一个构建函数）
    assert client.get(f"/api/agent/runs/{payload['run_id']}").status_code == 200


def test_suggest_stream_matches_nonstream(client, add_item, add_recipe, monkeypatch, fake_provider):
    _seed(add_item, add_recipe)
    provider = fake_provider(
        compose={
            "recommendations": [
                {
                    "recipe_id": "r_broccoli",
                    "reason": "用掉临期的西兰花",
                    "citations": [{"source": "recipe:r_broccoli", "locator": "步骤 1-4"}],
                }
            ]
        }
    )
    monkeypatch.setattr(
        recipes_domain, "resolve_provider", lambda provider=None, _p=provider: _p
    )

    response = client.post("/api/recipes/suggest/stream", json={"max_minutes": 30, "limit": 2})
    assert response.status_code == 200
    events = _parse(response.text)

    assert _types(events)[-2:] == ["result", "done"]
    steps = [event for event in events if event["type"] == "step"]
    assert [step["name"] for step in steps] == SUGGEST_STEPS
    for step in steps:
        assert set(step) == STEP_FIELDS

    payload = events[-2]["payload"]
    non_stream = client.post(
        "/api/recipes/suggest", json={"max_minutes": 30, "limit": 2}
    ).json()
    assert set(payload) == set(non_stream)
    assert set(payload["recommendations"][0]) == RECOMMENDATION_FIELDS
    assert payload["recommendations"][0]["recipe_id"] == "r_broccoli"


def test_stream_degrades_when_model_fails(client, add_item, add_recipe, monkeypatch, fake_provider):
    """模型抛错时必须走降级、仍给 result + done，不悬挂。"""
    _seed(add_item, add_recipe)
    provider = fake_provider(
        compose={"recommendations": []}, fail_compose=True, fail_understand=True
    )
    monkeypatch.setattr(plan_domain, "resolve_provider", lambda provider=None, _p=provider: _p)
    monkeypatch.setattr(
        recipes_domain, "resolve_provider", lambda provider=None, _p=provider: _p
    )

    plan_events = _parse(
        client.post(
            "/api/plan/meals/stream", json={"days": 1, "servings": 1, "max_minutes": 30}
        ).text
    )
    assert _types(plan_events)[-2:] == ["result", "done"]
    assert plan_events[-2]["payload"]["days"], "降级路径仍要有可用的配餐结果"
    assert any("已降级" in warning for warning in plan_events[-2]["payload"]["warnings"])

    suggest_events = _parse(
        client.post("/api/recipes/suggest/stream", json={"max_minutes": 30, "limit": 2}).text
    )
    assert _types(suggest_events)[-2:] == ["result", "done"]
    assert suggest_events[-2]["payload"]["recommendations"], "降级路径仍要有规则版推荐"
    assert any("已降级" in warning for warning in suggest_events[-2]["payload"]["warnings"])


def test_stream_error_event_then_done(client, add_item, add_recipe, monkeypatch, no_llm):
    """流水线抛错 → error（带 code/message）→ done，且不出现 result。"""
    _seed(add_item, add_recipe)

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("库存服务炸了")

    monkeypatch.setattr(plan_domain, "_invoke_tool", _boom)

    events = _parse(
        client.post(
            "/api/plan/meals/stream", json={"days": 1, "servings": 1, "max_minutes": 30}
        ).text
    )
    assert _types(events)[-2:] == ["error", "done"]
    assert "result" not in _types(events)
    error = events[-2]
    assert error["code"] == "plan_failed", "AppError 的 code 要透传给前端"
    assert error["message"]


def test_non_stream_endpoints_never_pass_progress_callback(
    client, add_item, add_recipe, monkeypatch, no_llm
):
    """非流式接口必须走「无回调」的老路径（回调默认 None，行为不变）。"""
    _seed(add_item, add_recipe)
    captured: dict[str, dict | None] = {}

    original_plan = plan_domain.build_plan
    original_suggest = recipes_domain.suggest

    async def _spy_plan(*args, **kwargs):
        captured["plan"] = dict(kwargs)
        return await original_plan(*args, **kwargs)

    async def _spy_suggest(*args, **kwargs):
        captured["suggest"] = dict(kwargs)
        return await original_suggest(*args, **kwargs)

    monkeypatch.setattr(plan_domain, "build_plan", _spy_plan)
    monkeypatch.setattr(recipes_domain, "suggest", _spy_suggest)

    assert client.post("/api/plan/meals", json={"days": 1}).status_code == 200
    assert captured["plan"] is not None and "on_step" not in captured["plan"]
    plain_suggest = client.post("/api/recipes/suggest", json={"limit": 1, "max_minutes": 30})
    assert plain_suggest.status_code == 200
    assert captured["suggest"] is not None and "on_step" not in captured["suggest"]

    assert client.post("/api/plan/meals/stream", json={"days": 1}).status_code == 200
    assert callable(captured["plan"]["on_step"])
    assert client.post(
        "/api/recipes/suggest/stream", json={"limit": 1, "max_minutes": 30}
    ).status_code == 200
    assert callable(captured["suggest"]["on_step"])


def test_on_step_cancel_aborts_later_model_calls(app_db, add_item, add_recipe, fake_provider):
    """断连时回调抛 CancelledError → 后续模型调用不再发起（契约 §6.15 规则 4）。"""
    _seed(add_item, add_recipe)
    provider = fake_provider()
    seen: list[str] = []

    async def _on_step(step: dict) -> None:
        seen.append(step["name"])
        if step["name"] == plan_domain.STEP_PLAN:
            raise asyncio.CancelledError("客户端已断开")

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            plan_domain.build_plan(
                days=1, servings=1, max_minutes=30, provider=provider, on_step=_on_step
            )
        )

    assert seen == ["understand", plan_domain.STEP_PLAN], seen
    assert "compose" not in provider.calls, "断连后不得再发起配餐模型调用"
