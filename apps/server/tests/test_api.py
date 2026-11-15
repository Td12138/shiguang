"""API 契约冒烟：路径 / 请求体 / 响应体（不依赖真实 LLM，全部注入 FakeProvider）。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.domain import recipes as recipes_domain
from app.domain import inventory as inv
from app.domain.tools_registry import AppError


@pytest.fixture()
def client(app_db):
    from app.api import capture
    from app.api import inventory as inventory_api
    from app.api import plan as plan_api
    from app.api import recipes as recipes_api
    from app.api import report as report_api
    from app.api import stats as stats_api

    app = FastAPI()
    for module in (capture, inventory_api, recipes_api, stats_api, report_api, plan_api):
        app.include_router(module.router)

    @app.exception_handler(AppError)
    async def _app_error_handler(_request, exc: AppError):  # 与 core 的错误体一致
        return JSONResponse(
            {"code": exc.code, "message": exc.message, "detail": exc.detail},
            status_code=exc.status,
        )

    return TestClient(app)


def test_inventory_crud(client, add_item):
    add_item("西兰花", avg_grams=300.0, carbon_kg_per_kg=2.5, price_per_kg=10.0)

    created = client.post("/api/inventory", json={"items": [{"name": "西兰花", "qty": 2}]})
    assert created.status_code == 200
    body = created.json()
    assert body["added"] == 1 and len(body["ids"]) == 1
    inv_id = body["ids"][0]

    listed = client.get("/api/inventory", params={"status": "active"}).json()
    assert listed[0]["id"] == inv_id
    assert listed[0]["level"] == "fresh"
    assert listed[0]["grams"] == pytest.approx(600.0)
    assert listed[0]["category"] == "蔬菜", "GET /api/inventory 要 JOIN items 带出分类"
    assert {"id", "name", "qty", "unit", "expires_at", "days_left", "level", "category"} <= set(
        listed[0]
    )

    patched = client.patch(f"/api/inventory/{inv_id}", json={"qty": 1})
    assert patched.status_code == 200
    assert patched.json()["grams"] == pytest.approx(300.0)

    consumed = client.post(f"/api/inventory/{inv_id}/consume", json={"grams": 100})
    assert consumed.status_code == 200
    assert consumed.json()["consumed_grams"] == pytest.approx(100.0)

    discarded = client.post(f"/api/inventory/{inv_id}/discard", json={"reason": "forgot"})
    assert discarded.status_code == 200
    assert discarded.json()["status"] == "discarded"

    bad = client.post(f"/api/inventory/{inv_id}/discard", json={"reason": "burned"})
    assert bad.status_code == 422  # pydantic Literal 拦截

    missing = client.patch("/api/inventory/inv_nope", json={"qty": 1})
    assert missing.status_code == 404
    assert missing.json()["code"] == "inventory_not_found"


def test_stats_summary(client, add_item):
    add_item("西兰花", avg_grams=1000.0, carbon_kg_per_kg=2.5)
    inv_id = inv.add_items({"items": [{"name": "西兰花", "qty": 1}]})["ids"][0]
    inv.consume(inv_id, 1000)

    response = client.get("/api/stats/summary", params={"range": "30d"})
    assert response.status_code == 200
    data = response.json()
    assert data["saved_grams"] == pytest.approx(1000.0)
    assert data["carbon_saved_kg"] == pytest.approx(2.5)
    assert data["equivalents"]["car_km"] == 17  # 2.5/0.15 = 16.67
    assert data["trend"][-1]["saved"] == pytest.approx(1000.0)


def test_recipes_suggest_and_run(client, add_item, add_recipe, monkeypatch, fake_provider):
    add_item("西兰花", avg_grams=300.0)
    add_recipe(
        "r_broccoli",
        "蒜蓉西兰花",
        ingredients=[{"name": "西兰花"}, {"name": "大蒜"}],
        steps=["切", "剁蒜", "爆香", "翻炒"],
        minutes=15,
    )
    inv.add_items({"items": [{"name": "西兰花", "qty": 1}]})

    provider = fake_provider(
        compose={
            "recommendations": [
                {
                    "recipe_id": "r_broccoli",
                    "reason": "用掉临期西兰花",
                    "citations": [{"source": "recipe:r_broccoli", "locator": "步骤 1-4"}],
                }
            ]
        }
    )
    monkeypatch.setattr(recipes_domain, "resolve_provider", lambda provider=None, _p=provider: provider or _p)

    response = client.post("/api/recipes/suggest", json={"use": [], "max_minutes": 30, "limit": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"].startswith("run_")
    assert body["recommendations"][0]["recipe_id"] == "r_broccoli"
    assert body["recommendations"][0]["citations"]

    run = client.get(f"/api/agent/runs/{body['run_id']}")
    assert run.status_code == 200
    assert [step["name"] for step in run.json()["steps"]] == [
        "understand",
        "plan",
        "retrieve",
        "compose",
        "verify",
    ]

    missing = client.get("/api/agent/runs/run_nope")
    assert missing.status_code == 404


def test_capture_recognize(client, add_item, monkeypatch, tmp_path, fake_provider):
    from app.api import capture as capture_api

    add_item("西兰花", avg_grams=300.0, shelf_life_days=5)
    provider = fake_provider(
        vision={
            "items": [
                {"name": "西兰花", "qty": 1, "unit": "颗", "confidence": 0.92},
                {"name": "西兰花", "qty": 1, "unit": "颗", "confidence": 0.51},
                {"name": "火星土豆", "qty": 1, "unit": "个", "confidence": 0.88},
            ]
        }
    )
    monkeypatch.setattr(capture_api, "resolve_provider", lambda provider=None, _p=provider: provider or _p)
    monkeypatch.setattr(capture_api, "UPLOAD_DIR", tmp_path / "upload")

    response = client.post(
        "/api/capture/recognize",
        files={"file": ("fridge.jpg", b"\xff\xd8\xff\xe0fakejpeg", "image/jpeg")},
    )
    assert response.status_code == 200
    body = response.json()

    assert body["image_id"].startswith("img_")
    assert len(body["items"]) == 3
    first = body["items"][0]
    assert first["matched"] is True
    assert first["item_id"]
    assert first["expires_at"]
    assert first["shelf_life_days"] == 5

    warnings = body["warnings"]
    assert any("置信度较低" in warning for warning in warnings)
    assert any("未匹配" in warning for warning in warnings)
    assert body["items"][2]["matched"] is False

    # 识别结果不入库
    assert inv.list_inventory("active") == []
    assert list((tmp_path / "upload").glob("*.jpg")), "上传图片应落盘"

    empty = client.post(
        "/api/capture/recognize", files={"file": ("x.jpg", b"", "image/jpeg")}
    )
    assert empty.status_code == 400


def test_weekly_report_stream(client, monkeypatch):
    from app.domain import report as report_domain

    monkeypatch.setattr(report_domain, "resolve_provider", lambda provider=None: None)

    response = client.post("/api/report/weekly")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    payload = response.text
    assert '"type": "delta"' in payload
    assert '"type": "citations"' in payload
    assert '"type": "done"' in payload
    assert "碳当量为估算" in payload

def test_plan_meals_endpoint(client, add_item, add_recipe, monkeypatch):
    from app.domain import plan as plan_domain

    add_item("西兰花", avg_grams=300.0, shelf_life_days=5)
    add_recipe(
        "r_broccoli",
        "蒜蓉西兰花",
        ingredients=[{"name": "西兰花", "qty": 1, "unit": "颗"}, {"name": "大蒜", "qty": 2, "unit": "瓣"}],
        steps=["切", "剁蒜", "爆香", "翻炒"],
        minutes=15,
    )
    inv.add_items({"items": [{"name": "西兰花", "qty": 1}]})
    monkeypatch.setattr(plan_domain, "resolve_provider", lambda provider=None: None)

    response = client.post("/api/plan/meals", json={"days": 2, "servings": 1, "max_minutes": 30})
    assert response.status_code == 200
    body = response.json()

    assert body["plan_id"].startswith("plan_")
    assert body["run_id"].startswith("run_")
    assert len(body["days"]) == 2
    assert body["days"][0]["date"] > inv.today().isoformat()
    meal = body["days"][0]["meals"][0]
    assert meal["recipe_id"] == "r_broccoli"
    assert meal["citations"]
    assert meal["citations"][0].get("text")
    assert {"slot", "recipe_id", "title", "minutes", "uses", "missing", "citations"} <= set(meal)
    assert set(body["coverage"]) == {"used_items", "expiring_used", "unused_expiring"}
    assert any("已降级" in warning for warning in body["warnings"])

    run = client.get(f"/api/agent/runs/{body['run_id']}").json()
    assert run["kind"] == "meal_plan"
    assert [step["name"] for step in run["steps"]] == ["understand", "plan", "allocate", "compose", "verify"]


def test_plan_revise_endpoint(client, add_item, add_recipe, monkeypatch):
    """§6.9 + §6.10：改计划返回 changed/learned，学到的偏好进 /api/preferences。"""
    from app.domain import plan as plan_domain

    add_item("鸡蛋", avg_grams=60.0, unit="个", shelf_life_days=10)
    add_item("西兰花", avg_grams=300.0, shelf_life_days=5)
    add_recipe(
        "r_egg",
        "西兰花炒鸡蛋",
        ingredients=[
            {"name": "西兰花", "qty": 1, "unit": "颗"},
            {"name": "鸡蛋", "qty": 2, "unit": "个"},
        ],
        steps=["切小朵", "打蛋", "爆香", "同炒"],
        minutes=10,
    )
    add_recipe(
        "r_veg",
        "清炒西兰花",
        ingredients=[{"name": "西兰花", "qty": 1, "unit": "颗"}],
        steps=["切小朵", "焯水", "清炒调味"],
        minutes=8,
    )
    inv.add_items(
        {"items": [{"name": "西兰花", "qty": 3}, {"name": "鸡蛋", "qty": 6}]}
    )
    monkeypatch.setattr(plan_domain, "resolve_provider", lambda provider=None: None)

    created = client.post(
        "/api/plan/meals", json={"days": 2, "servings": 1, "max_minutes": 30}
    ).json()
    assert created["days"]

    response = client.post(
        f"/api/plan/meals/{created['plan_id']}/revise",
        json={"instruction": "不要鸡蛋"},
    )
    assert response.status_code == 200
    body = response.json()
    assert {"plan_id", "run_id", "days", "shopping", "coverage", "changed", "learned"} <= set(body)
    used = {row["name"] for day in body["days"] for meal in day["meals"] for row in meal["uses"]}
    assert "鸡蛋" not in used
    assert body["learned"], "改成功后应学到「不吃鸡蛋」"

    prefs = client.get("/api/preferences")
    assert prefs.status_code == 200
    assert any("鸡蛋" in row["text"] for row in prefs.json()["items"])

    missing = client.post(
        "/api/plan/meals/plan_nope/revise", json={"instruction": "清淡点"}
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "plan_not_found"


def test_capture_payload_too_large(client, monkeypatch):
    from app.api import capture as capture_api

    monkeypatch.setattr(capture_api.config, "MAX_UPLOAD_BYTES", 10)
    assert not hasattr(capture_api, "MAX_UPLOAD_BYTES"), "上限只能来自 config，不得本地重复定义"

    response = client.post(
        "/api/capture/recognize",
        files={"file": ("big.jpg", b"x" * 11, "image/jpeg")},
    )
    assert response.status_code == 413
    body = response.json()
    assert body["code"] == "payload_too_large"
    assert "10 字节" in body["message"]
