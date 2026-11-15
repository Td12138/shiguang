"""库存业务域：days_left 分级 + 计量口径（契约 §6.3）。"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.domain import inventory as inv
from app.domain.tools_registry import AppError


def test_level_boundaries():
    assert inv.level_for(10) == "fresh"
    assert inv.level_for(4) == "fresh"
    assert inv.level_for(3) == "soon"
    assert inv.level_for(2) == "soon"
    assert inv.level_for(1) == "urgent"
    assert inv.level_for(0) == "urgent"
    assert inv.level_for(-1) == "expired"


def test_days_left_uses_date_part():
    anchor = date(2026, 11, 15)
    assert inv.days_left("2026-11-20", today_date=anchor) == 5
    assert inv.days_left("2026-11-20T23:59:59+08:00", today_date=anchor) == 5
    assert inv.days_left("2026-11-10", today_date=anchor) == -5
    assert inv.days_left(None, today_date=anchor) == 0


def test_add_items_meters_grams_and_expiry(app_db, add_item):
    add_item("西兰花", avg_grams=300.0, shelf_life_days=5)
    result = inv.add_items({"items": [{"name": "西兰花", "qty": 2}]})

    assert result["added"] == 1
    items = inv.list_inventory("active")
    assert len(items) == 1
    row = items[0]
    assert row["grams"] == pytest.approx(600.0)
    assert row["qty"] == pytest.approx(2.0)
    assert row["days_left"] == 5
    assert row["level"] == "fresh"
    assert row["expires_at"] == (inv.today() + timedelta(days=5)).isoformat()
    assert result["ids"] == [row["id"]]


def test_find_item_does_not_match_substring(app_db, add_item):
    """「番茄酱」不能命中「番茄」：库外食材应保持未匹配，不能套用番茄的克数/碳因子。"""
    from app.db.conn import get_conn

    add_item("番茄", avg_grams=150.0)
    conn = get_conn()
    try:
        assert inv.find_item(conn, "番茄酱", fuzzy=False) is None
        assert inv.find_item(conn, "番茄", fuzzy=False)["name"] == "番茄"
    finally:
        conn.close()


def test_add_items_ignores_stale_item_id_after_rename(app_db, add_item):
    """用户把识别名从西兰花改成番茄后，旧 item_id 不能继续决定克数/碳因子。"""
    broccoli_id = add_item("西兰花", avg_grams=300.0)
    tomato_id = add_item("番茄", avg_grams=150.0)

    result = inv.add_items(
        {"items": [{"name": "番茄", "item_id": broccoli_id, "qty": 1}]}
    )

    row = inv.list_inventory("active")[0]
    assert result["added"] == 1
    assert row["name"] == "番茄"
    assert row["item_id"] == tomato_id
    assert row["grams"] == pytest.approx(150.0)


def test_consume_then_discard(app_db, add_item):
    add_item("西兰花", avg_grams=300.0, carbon_kg_per_kg=2.5, price_per_kg=10.0)
    inv_id = inv.add_items({"items": [{"name": "西兰花", "qty": 2}]})["ids"][0]

    consumed = inv.consume(inv_id, 200)
    assert consumed["consumed_grams"] == pytest.approx(200.0)
    assert consumed["grams"] == pytest.approx(400.0)
    assert consumed["status"] == "active"

    discarded = inv.discard(inv_id, "forgot", 400)
    assert discarded["discarded_grams"] == pytest.approx(400.0)
    assert discarded["carbon_kg"] == pytest.approx(0.4 * 2.5)
    assert discarded["status"] == "discarded"
    assert discarded["grams"] == pytest.approx(0.0)

    from app.db.conn import get_conn

    conn = get_conn()
    try:
        waste = conn.execute("SELECT * FROM waste_log").fetchall()
        events = conn.execute("SELECT * FROM events WHERE kind='consume'").fetchall()
    finally:
        conn.close()
    assert len(waste) == 1 and waste[0]["grams"] == pytest.approx(400.0)
    assert len(events) == 1


def test_consume_all_marks_consumed(app_db, add_item):
    add_item("鸡蛋", avg_grams=60.0, unit="个")
    inv_id = inv.add_items({"items": [{"name": "鸡蛋", "qty": 3}]})["ids"][0]
    assert inv.list_inventory("active")[0]["grams"] == pytest.approx(180.0)

    result = inv.consume(inv_id)
    assert result["status"] == "consumed"
    assert result["grams"] == pytest.approx(0.0)
    assert inv.list_inventory("active") == []
    assert len(inv.list_inventory("consumed")) == 1


def test_consume_updates_qty_proportionally(app_db, add_item):
    """consume 不能只改 grams：qty 也要按克数比例扣，否则前端数量与克数对不上。"""
    add_item("西兰花", avg_grams=300.0)
    inv_id = inv.add_items({"items": [{"name": "西兰花", "qty": 2}]})["ids"][0]
    assert inv.list_inventory("active")[0]["qty"] == pytest.approx(2.0)

    result = inv.consume(inv_id, 150)  # 600g 吃 150g → 剩 450g / 1.5 颗
    assert result["grams"] == pytest.approx(450.0)
    assert result["qty"] == pytest.approx(1.5)
    assert result["status"] == "active"

    rest = inv.consume(inv_id)  # 全部吃完 → qty 归零
    assert rest["status"] == "consumed"
    assert rest["qty"] == pytest.approx(0.0)


def test_list_inventory_includes_item_category(app_db, add_item):
    add_item("西兰花", category="蔬菜")
    inv_id = inv.add_items({"items": [{"name": "西兰花", "qty": 1}]})["ids"][0]

    row = inv.list_inventory("active")[0]
    assert row["category"] == "蔬菜"
    assert inv.get_inventory(inv_id)["category"] == "蔬菜"


def test_patch_qty_recomputes_grams(app_db, add_item):
    add_item("西兰花", avg_grams=300.0)
    inv_id = inv.add_items({"items": [{"name": "西兰花", "qty": 2}]})["ids"][0]

    updated = inv.update_inventory(inv_id, qty=1, note="只买了半颗")
    assert updated["grams"] == pytest.approx(300.0)
    assert updated["note"] == "只买了半颗"
    assert updated["days_left"] == 5


def test_patch_expires_at_changes_level(app_db, add_item):
    add_item("西兰花", avg_grams=300.0)
    inv_id = inv.add_items({"items": [{"name": "西兰花", "qty": 1}]})["ids"][0]

    updated = inv.update_inventory(inv_id, expires_at=inv.today().isoformat())
    assert updated["days_left"] == 0
    assert updated["level"] == "urgent"

    updated = inv.update_inventory(inv_id, expires_at=(inv.today() - timedelta(days=2)).isoformat())
    assert updated["level"] == "expired"


def test_invalid_inputs(app_db, add_item):
    add_item("西兰花")
    inv_id = inv.add_items({"items": [{"name": "西兰花", "qty": 1}]})["ids"][0]

    with pytest.raises(AppError) as missing:
        inv.consume("inv_not_exist")
    assert missing.value.status == 404

    with pytest.raises(AppError) as bad_reason:
        inv.discard(inv_id, "burned")
    assert bad_reason.value.status == 400

    inv.consume(inv_id)
    with pytest.raises(AppError) as not_active:
        inv.consume(inv_id)
    assert not_active.value.status == 409
