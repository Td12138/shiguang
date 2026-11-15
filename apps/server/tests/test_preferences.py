"""用户偏好（契约 §6.10）：增删查、FTS 索引、avoid 硬约束生效、低置信度不生效。"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from app.api import plan as plan_api
from app.api import preferences as preferences_api
from app.domain import inventory as inv
from app.domain import plan
from app.domain import preferences
from app.rag import retrieve
from app.domain.tools_registry import AppError

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def client(app_db):
    app = FastAPI()
    app.include_router(plan_api.router)

    @app.exception_handler(AppError)
    async def _handler(_request, exc: AppError):
        return JSONResponse(
            {"code": exc.code, "message": exc.message, "detail": exc.detail},
            status_code=exc.status,
        )

    return TestClient(app)


def _seed_meals(add_item, add_recipe):
    add_item("鸡蛋", avg_grams=60.0, unit="个", shelf_life_days=10)
    add_item("西兰花", avg_grams=300.0, shelf_life_days=5)
    add_recipe(
        "r_egg",
        "番茄炒蛋",
        ingredients=[
            {"name": "鸡蛋", "qty": 2, "unit": "个", "optional": False},
            {"name": "西兰花", "qty": 1, "unit": "颗", "optional": False},
        ],
        steps=["打蛋", "切菜", "热油", "同炒"],
        minutes=10,
    )
    add_recipe(
        "r_veg",
        "清炒西兰花",
        ingredients=[{"name": "西兰花", "qty": 1, "unit": "颗", "optional": False}],
        steps=["切小朵", "焯水", "清炒调味"],
        minutes=8,
    )
    inv.add_items(
        {
            "items": [
                {
                    "name": "西兰花",
                    "qty": 2,
                    "expires_at": (inv.today() + timedelta(days=2)).isoformat(),
                },
                {"name": "鸡蛋", "qty": 6},
            ]
        }
    )


def test_add_list_delete_preference(app_db):
    created = preferences.add_preference("不吃香菜", "avoid")

    assert created["id"].startswith("pref_")
    assert created["source"] == "manual"
    assert created["kind"] == "avoid"
    assert created["confidence"] == 1.0
    assert created["active"] is True

    items = preferences.list_preferences()
    assert [row["text"] for row in items] == ["不吃香菜"]

    removed = preferences.delete_preference(created["id"])
    assert removed == {"deleted": True, "id": created["id"]}
    assert preferences.list_preferences() == []

    with pytest.raises(AppError) as excinfo:
        preferences.delete_preference(created["id"])
    assert excinfo.value.status == 404


def test_low_confidence_preference_is_stored_but_inactive(app_db):
    row = preferences.add_preference("少吃辣", "health", source="dialog", confidence=0.4)

    assert row["active"] is False
    assert row["confidence"] == 0.4
    assert preferences.active_preferences() == []
    warnings = preferences.warnings_for_low_confidence()
    assert warnings and "置信度" in warnings[0]


def test_preference_is_searchable_in_fts(app_db):
    row = preferences.add_preference("不吃香菜", "avoid")

    hits = retrieve.search("香菜", limit=5)
    sources = [hit["source"] for hit in hits]
    assert f"pref:{row['id']}" in sources
    chunk = next(hit for hit in hits if hit["source"] == f"pref:{row['id']}")
    assert chunk["body"] == "不吃香菜"


def test_delete_preference_removes_fts_chunk(app_db):
    row = preferences.add_preference("不吃香菜", "avoid")
    preferences.delete_preference(row["id"])

    sources = [hit["source"] for hit in retrieve.search("香菜", limit=5)]
    assert f"pref:{row['id']}" not in sources


def test_rebuild_index_keeps_preference_chunks(app_db):
    from app.rag.index import rebuild_index

    row = preferences.add_preference("不吃香菜", "avoid")
    rebuild_index()

    sources = [hit["source"] for hit in retrieve.search("香菜", limit=5)]
    assert f"pref:{row['id']}" in sources


def test_avoid_preference_blocks_ingredient_in_generated_plan(
    app_db, add_item, add_recipe, no_llm
):
    _seed_meals(add_item, add_recipe)
    preferences.add_preference("不吃鸡蛋", "avoid")

    result = _run(plan.build_plan(days=2, servings=1, provider=None))

    meals = [meal for day in result["days"] for meal in day["meals"]]
    assert meals
    used = {row["name"] for meal in meals for row in meal["uses"]}
    missing = {row["name"] for meal in meals for row in meal["missing"]}
    assert "鸡蛋" not in used
    assert "鸡蛋" not in missing
    assert all(meal["recipe_id"] != "r_egg" for meal in meals)
    assert any("忌口" in warning for warning in result["warnings"])


def test_low_confidence_avoid_does_not_block(app_db, add_item, add_recipe, no_llm):
    _seed_meals(add_item, add_recipe)
    preferences.add_preference("不吃鸡蛋", "avoid", source="dialog", confidence=0.3)

    result = _run(plan.build_plan(days=1, servings=1, provider=None))

    used = {row["name"] for day in result["days"] for meal in day["meals"] for row in meal["uses"]}
    assert "鸡蛋" in used, "低置信度偏好不应生效"
    assert any("置信度" in warning for warning in result["warnings"])


def test_manual_api_crud(client):
    created = client.post("/api/preferences", json={"text": "不吃香菜", "kind": "avoid"})
    assert created.status_code == 200
    body = created.json()
    assert body["id"].startswith("pref_")

    listed = client.get("/api/preferences")
    assert listed.status_code == 200
    assert [row["text"] for row in listed.json()["items"]] == ["不吃香菜"]

    bad = client.post("/api/preferences", json={"text": "不吃香菜", "kind": "nope"})
    assert bad.status_code == 422

    deleted = client.delete(f"/api/preferences/{body['id']}")
    assert deleted.status_code == 200
    assert client.get("/api/preferences").json()["items"] == []

    missing = client.delete(f"/api/preferences/{body['id']}")
    assert missing.status_code == 404
    assert missing.json()["code"] == "preference_not_found"
