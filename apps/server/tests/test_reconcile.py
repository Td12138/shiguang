"""库存对账（契约 §6.13）与数据新鲜度（§6.14）。

覆盖：missing/suspect 判定、reduced 按比例、apply 幂等、discard 走 waste_log、
新鲜度 stale_days 与 warnings、空识别不误删。
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.db.conn import get_conn
from app.domain import inventory as inv
from app.domain.tools_registry import AppError

FAKE_JPEG = b"\xff\xd8\xff\xe0reconcile-jpeg"


@pytest.fixture()
def client(app_db):
    """只挂 inventory router（对账就是它的子 router，顺带验证 include_router 生效）。"""
    from app.api import inventory as inventory_api
    from app.api import plan as plan_api
    from app.api import recipes as recipes_api

    app = FastAPI()
    for module in (inventory_api, recipes_api, plan_api):
        app.include_router(module.router)

    @app.exception_handler(AppError)
    async def _handler(_request, exc: AppError):
        return JSONResponse(
            {"code": exc.code, "message": exc.message, "detail": exc.detail},
            status_code=exc.status,
        )

    return TestClient(app)


@pytest.fixture()
def reconcile_env(monkeypatch, tmp_path):
    """上传目录指向临时目录，并把 provider 换成本次注入的 FakeProvider。"""
    from app.api import reconcile as reconcile_api

    monkeypatch.setattr(reconcile_api, "UPLOAD_DIR", tmp_path / "upload")

    def _setup(provider):
        monkeypatch.setattr(
            reconcile_api, "resolve_provider", lambda provider=None, _p=provider: provider or _p
        )
        return reconcile_api

    return _setup


def _post(client):
    return client.post(
        "/api/inventory/reconcile",
        files={"file": ("fridge.jpg", FAKE_JPEG, "image/jpeg")},
    )


def _apply(client, payload):
    return client.post("/api/inventory/reconcile/apply", json=payload)


def _events(kind: str) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT payload FROM events WHERE kind = ? ORDER BY created_at", (kind,)
        ).fetchall()
    finally:
        conn.close()
    return [json.loads(row["payload"]) for row in rows]


def test_reconcile_missing_and_low_confidence_suspect(
    client, add_item, fake_provider, reconcile_env
):
    """库里 3 样、识别出 2 样 → missing 1；低置信度进 suspect，不判 missing。"""
    add_item("生菜", avg_grams=300.0, unit="颗", shelf_life_days=5)
    add_item("鸡蛋", avg_grams=60.0, unit="个", shelf_life_days=10)
    add_item("菠菜", avg_grams=200.0, unit="把", shelf_life_days=3)
    lettuce, eggs, spinach = inv.add_items(
        {
            "items": [
                {"name": "生菜", "qty": 1},
                {"name": "鸡蛋", "qty": 6},
                {"name": "菠菜", "qty": 1},
            ]
        }
    )["ids"]

    reconcile_env(
        fake_provider(
            vision={
                "items": [
                    {"name": "鸡蛋", "qty": 6, "unit": "个", "confidence": 0.95},
                    {"name": "菠菜", "qty": 1, "unit": "把", "confidence": 0.5},
                ]
            }
        )
    )

    body = _post(client).json()

    assert body["image_id"].startswith("img_")
    assert body["checked_at"]
    assert [row["inventory_id"] for row in body["missing"]] == [lettuce]
    missing = body["missing"][0]
    assert missing["name"] == "生菜"
    assert missing["qty"] == 1
    assert missing["unit"] == "颗"
    assert "days_left" in missing

    assert [row["inventory_id"] for row in body["suspect"]] == [spinach]
    assert "置信度" in body["suspect"][0]["reason"]
    assert eggs not in {row["inventory_id"] for row in body["missing"]}

    assert body["reduced"] == [] and body["added"] == []
    assert any("置信度较低" in warning for warning in body["warnings"])

    # 规则 2：对账只读，不擅自改库存
    assert len(inv.list_inventory("active")) == 3
    assert inv.get_inventory(lettuce)["status"] == "active"


def test_reconcile_reduced_then_apply_scales_grams(
    client, add_item, fake_provider, reconcile_env
):
    """数量 6→2：先出 reduced，apply 后 qty=2、grams 按比例缩。"""
    add_item("鸡蛋", avg_grams=60.0, unit="个", carbon_kg_per_kg=4.0, shelf_life_days=10)
    inv_id = inv.add_items({"items": [{"name": "鸡蛋", "qty": 6}]})["ids"][0]
    assert inv.get_inventory(inv_id)["grams"] == pytest.approx(360.0)

    reconcile_env(
        fake_provider(
            vision={"items": [{"name": "鸡蛋", "qty": 2, "unit": "个", "confidence": 0.9}]}
        )
    )

    body = _post(client).json()
    assert body["missing"] == []
    reduced = body["reduced"][0]
    assert reduced["inventory_id"] == inv_id
    assert reduced["from_qty"] == 6
    assert reduced["to_qty"] == 2
    assert reduced["unit"] == "个"

    applied = _apply(
        client,
        {"image_id": body["image_id"], "reduced": [{"inventory_id": inv_id, "qty": 2}]},
    ).json()
    assert applied["applied"] == {"discarded": 0, "consumed": 0, "updated": 1, "added": 0}

    row = inv.get_inventory(inv_id)
    assert row["qty"] == pytest.approx(2.0)
    assert row["grams"] == pytest.approx(120.0), "360g × 2/6 = 120g（按比例，不重算 avg_grams）"
    assert row["stale_days"] == 0, "对账 apply 要刷新 verified_at"

    # 留痕：events(kind=reconcile) 记清改了什么
    payloads = _events("reconcile")
    assert len(payloads) == 1
    action = payloads[0]["actions"][0]
    assert action["inventory_id"] == inv_id
    assert action["action"] == "reduced"
    assert action["from_qty"] == 6 and action["to_qty"] == 2
    assert payloads[0]["image_id"] == body["image_id"]


def test_apply_is_idempotent(client, add_item):
    """同一 inventory_id 重复 apply 只生效一次（第二次 applied 全 0）。"""
    add_item("鸡蛋", avg_grams=60.0, unit="个", shelf_life_days=10)
    inv_id = inv.add_items({"items": [{"name": "鸡蛋", "qty": 6}]})["ids"][0]
    payload = {"reduced": [{"inventory_id": inv_id, "qty": 2}]}

    first = _apply(client, payload).json()
    second = _apply(client, payload).json()

    assert first["applied"]["updated"] == 1
    assert second["applied"] == {"discarded": 0, "consumed": 0, "updated": 0, "added": 0}
    assert second["skipped"] >= 1
    assert inv.get_inventory(inv_id)["qty"] == pytest.approx(2.0)
    assert len(_events("reconcile")) == 1, "幂等跳过不应再写一条对账事件"


def test_apply_idempotent_for_added_and_discard(client, add_item):
    """added / discarded 同样幂等：重复提交不会重复入库或重复计浪费。"""
    add_item("酸奶", avg_grams=100.0, unit="杯", shelf_life_days=7)
    add_item("生菜", avg_grams=300.0, unit="颗", carbon_kg_per_kg=1.8)
    lettuce = inv.add_items({"items": [{"name": "生菜", "qty": 2}]})["ids"][0]

    payload = {
        "missing": [{"inventory_id": lettuce, "action": "discarded", "reason": "spoiled"}],
        "added": [{"name": "酸奶", "qty": 2, "unit": "杯"}],
    }
    first = _apply(client, payload).json()
    second = _apply(client, payload).json()

    assert first["applied"] == {"discarded": 1, "consumed": 0, "updated": 0, "added": 1}
    assert second["applied"] == {"discarded": 0, "consumed": 0, "updated": 0, "added": 0}

    conn = get_conn()
    try:
        waste = conn.execute("SELECT COUNT(*) FROM waste_log").fetchone()[0]
    finally:
        conn.close()
    assert waste == 1, "第二次不能重复写 waste_log"
    assert len(inv.list_inventory("active")) == 1, "酸奶只入库一次"
    assert inv.get_inventory(lettuce)["status"] == "discarded"


def test_apply_missing_discarded_writes_waste_log(client, add_item):
    """discarded 走 waste_log，碳排口径与 /discard 完全一致（grams/1000 × 碳因子）。"""
    add_item("生菜", avg_grams=300.0, unit="颗", carbon_kg_per_kg=1.8)
    inv_id = inv.add_items({"items": [{"name": "生菜", "qty": 2}]})["ids"][0]  # 600g

    body = _apply(
        client,
        {
            "missing": [
                {"inventory_id": inv_id, "action": "discarded", "reason": "spoiled"}
            ]
        },
    ).json()
    assert body["applied"]["discarded"] == 1

    row = inv.get_inventory(inv_id)
    assert row["status"] == "discarded"
    assert row["grams"] == pytest.approx(0.0)
    assert row["stale_days"] == 0

    conn = get_conn()
    try:
        waste = conn.execute("SELECT * FROM waste_log").fetchall()
    finally:
        conn.close()
    assert len(waste) == 1
    assert waste[0]["inventory_id"] == inv_id
    assert waste[0]["grams"] == pytest.approx(600.0)
    assert waste[0]["reason"] == "spoiled"
    assert waste[0]["carbon_kg"] == pytest.approx(0.6 * 1.8), "与 §6.3 碳排口径一致"


def test_apply_consumed_reuses_consume(client, add_item):
    """missing 判 consumed 时复用 consume 逻辑（写 events.kind=consume）。"""
    add_item("鸡蛋", avg_grams=60.0, unit="个", carbon_kg_per_kg=4.0, price_per_kg=12.0)
    inv_id = inv.add_items({"items": [{"name": "鸡蛋", "qty": 3}]})["ids"][0]

    body = _apply(
        client, {"missing": [{"inventory_id": inv_id, "action": "consumed"}]}
    ).json()
    assert body["applied"]["consumed"] == 1

    assert inv.get_inventory(inv_id)["status"] == "consumed"
    consume_events = _events("consume")
    assert len(consume_events) == 1
    assert consume_events[0]["grams"] == pytest.approx(180.0)
    assert consume_events[0]["carbon_saved_kg"] == pytest.approx(0.18 * 4.0)


def test_apply_rejects_increase_and_zero(client, add_item):
    """对账只能减不能增：目标数量大于当前/为 0 都不改数据，只给 warning。"""
    add_item("鸡蛋", avg_grams=60.0, unit="个")
    inv_id = inv.add_items({"items": [{"name": "鸡蛋", "qty": 6}]})["ids"][0]

    body = _apply(client, {"reduced": [{"inventory_id": inv_id, "qty": 8}]}).json()
    assert body["applied"]["updated"] == 0
    assert any("只能减不能增" in warning for warning in body["warnings"])
    assert inv.get_inventory(inv_id)["qty"] == pytest.approx(6.0)


def test_reconcile_empty_recognition_keeps_everything(
    client, add_item, fake_provider, reconcile_env
):
    """识别为空 → 不误删：missing/reduced/added/suspect 全空，全部保留 + warnings。"""
    add_item("生菜", avg_grams=300.0, unit="颗")
    add_item("牛奶", avg_grams=1000.0, unit="盒")
    inv.add_items({"items": [{"name": "生菜", "qty": 1}, {"name": "牛奶", "qty": 1}]})

    reconcile_env(fake_provider(vision={"items": []}))

    body = _post(client).json()

    assert body["missing"] == []
    assert body["reduced"] == []
    assert body["added"] == []
    assert body["suspect"] == []
    assert any("全部保留" in warning for warning in body["warnings"])
    assert len(inv.list_inventory("active")) == 2


def test_reconcile_alias_name_matches_inventory(client, add_item, fake_provider, reconcile_env):
    """别名表生效：「西红柿」要匹配到库存里的「番茄」，不能误判成 missing + added。"""
    add_item("番茄", avg_grams=180.0, unit="个")
    inv_id = inv.add_items({"items": [{"name": "番茄", "qty": 3}]})["ids"][0]

    reconcile_env(
        fake_provider(
            vision={"items": [{"name": "西红柿", "qty": 3, "unit": "个", "confidence": 0.9}]}
        )
    )

    body = _post(client).json()
    assert body["missing"] == []
    assert body["added"] == []
    assert body["reduced"] == []
    assert inv.get_inventory(inv_id)["qty"] == pytest.approx(3.0)


def test_stale_days_and_plan_warnings(client, add_item, add_recipe, no_llm):
    """verified_at 改成 5 天前 → stale_days>3，plan/meals 与 recipes/suggest 必须提示。"""
    add_item("西兰花", avg_grams=300.0, shelf_life_days=5)
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
    inv_id = inv.add_items({"items": [{"name": "西兰花", "qty": 1}]})["ids"][0]

    stale_iso = (inv.today() - timedelta(days=5)).isoformat() + "T10:00:00+08:00"
    conn = get_conn()
    try:
        conn.execute("UPDATE inventory SET verified_at = ? WHERE id = ?", (stale_iso, inv_id))
        conn.commit()
    finally:
        conn.close()

    listed = client.get("/api/inventory", params={"status": "active"}).json()
    assert listed[0]["stale_days"] == 5
    assert listed[0]["stale_days"] > 3

    suggest = client.post(
        "/api/recipes/suggest", json={"use": [], "max_minutes": 30, "limit": 2}
    ).json()
    assert any("超过 3 天未核验" in warning for warning in suggest["warnings"])

    plan_body = client.post(
        "/api/plan/meals", json={"days": 1, "servings": 1, "max_minutes": 30}
    ).json()
    assert plan_body["plan_id"].startswith("plan_"), "提示但不阻断生成"
    assert any("超过 3 天未核验" in warning for warning in plan_body["warnings"])


def test_fresh_inventory_has_no_stale_warning(client, add_item, add_recipe, no_llm):
    """刚入库（verified_at=now）不该出现新鲜度提示。"""
    add_item("西兰花", avg_grams=300.0, shelf_life_days=5)
    add_recipe(
        "r_broccoli",
        "蒜蓉西兰花",
        ingredients=[{"name": "西兰花", "qty": 1, "unit": "颗", "optional": False}],
        steps=["切小朵", "爆香", "翻炒调味"],
        minutes=15,
    )
    inv.add_items({"items": [{"name": "西兰花", "qty": 1}]})

    listed = client.get("/api/inventory", params={"status": "active"}).json()
    assert listed[0]["stale_days"] == 0

    suggest = client.post(
        "/api/recipes/suggest", json={"use": [], "max_minutes": 30, "limit": 2}
    ).json()
    assert not any("未核验" in warning for warning in suggest["warnings"])


def test_consume_and_discard_refresh_verified_at(client, add_item):
    """consume / discard 都要刷新 verified_at（否则刚动过的库存会被误判为陈旧）。"""
    add_item("鸡蛋", avg_grams=60.0, unit="个")
    first = inv.add_items({"items": [{"name": "鸡蛋", "qty": 6}]})["ids"][0]
    second = inv.add_items({"items": [{"name": "鸡蛋", "qty": 6}]})["ids"][0]

    stale_iso = (inv.today() - timedelta(days=9)).isoformat() + "T10:00:00+08:00"
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE inventory SET verified_at = ? WHERE id IN (?,?)", (stale_iso, first, second)
        )
        conn.commit()
    finally:
        conn.close()

    client.post(f"/api/inventory/{first}/consume", json={"grams": 60})
    client.post(f"/api/inventory/{second}/discard", json={"reason": "forgot"})

    assert inv.get_inventory(first)["stale_days"] == 0
    assert inv.get_inventory(second)["stale_days"] == 0


def test_reconcile_apply_keeps_data_when_all_keep(client, add_item):
    """默认动作 keep：apply 传 keep 什么都不改，只提示。"""
    add_item("生菜", avg_grams=300.0, unit="颗")
    inv_id = inv.add_items({"items": [{"name": "生菜", "qty": 1}]})["ids"][0]

    body = _apply(
        client, {"missing": [{"inventory_id": inv_id, "action": "keep"}]}
    ).json()

    assert body["applied"] == {"discarded": 0, "consumed": 0, "updated": 0, "added": 0}
    assert body["skipped"] == 1
    assert inv.get_inventory(inv_id)["status"] == "active"
    assert _events("reconcile") == []


def test_apply_clears_stale_warning(client, add_item):
    """拍完对账并 apply（即使全是 keep）后 stale_days 归零，提示不再出现。"""
    add_item("生菜", avg_grams=300.0, unit="颗")
    first = inv.add_items({"items": [{"name": "生菜", "qty": 1}]})["ids"][0]
    second = inv.add_items({"items": [{"name": "生菜", "qty": 2}]})["ids"][0]

    stale_iso = (inv.today() - timedelta(days=6)).isoformat() + "T10:00:00+08:00"
    conn = get_conn()
    try:
        conn.execute("UPDATE inventory SET verified_at = ?", (stale_iso,))
        conn.commit()
    finally:
        conn.close()
    assert inv.get_inventory(first)["stale_days"] == 6

    body = _apply(client, {"missing": [{"inventory_id": first, "action": "keep"}]}).json()

    assert body["verified"] == 2, "apply 是一次核验：全部 active 行都要盖时间戳"
    assert inv.get_inventory(first)["stale_days"] == 0
    assert inv.get_inventory(second)["stale_days"] == 0
    assert all(row["stale_days"] == 0 for row in client.get("/api/inventory").json())

