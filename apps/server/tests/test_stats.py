"""统计公式（契约 §6.5）：waste_rate / 克数 / 碳 / 金额 / 等效换算 / 趋势。"""

from __future__ import annotations

import pytest

from app.domain import inventory as inv
from app.domain import stats


def test_parse_range():
    assert stats.parse_range("7d") == (7, "7d")
    assert stats.parse_range("30d") == (30, "30d")
    assert stats.parse_range("all") == (None, "all")
    assert stats.parse_range("垃圾参数") == (30, "30d")
    assert stats.parse_range(None) == (30, "30d")
    assert stats.parse_range("99999d")[0] == stats.MAX_RANGE_DAYS


def test_summary_formulas(app_db, add_item):
    add_item("西兰花", avg_grams=1000.0, carbon_kg_per_kg=2.5, price_per_kg=10.0)
    inv_id = inv.add_items({"items": [{"name": "西兰花", "qty": 2}]})["ids"][0]  # 2000g

    inv.consume(inv_id, 1200)
    inv.discard(inv_id, "spoiled", 800)

    data = stats.summary("30d")

    assert data["saved_grams"] == pytest.approx(1200.0)
    assert data["thrown_grams"] == pytest.approx(800.0)
    assert data["waste_rate"] == pytest.approx(0.4, abs=1e-3)
    assert data["carbon_saved_kg"] == pytest.approx(3.0)  # 1.2kg × 2.5
    assert data["money_saved"] == pytest.approx(12.0)  # 1.2kg × 10
    assert data["equivalents"]["car_km"] == 20  # 3.0 / 0.15
    assert data["equivalents"]["trees_days"] == 50  # 3.0 / 0.06

    assert len(data["trend"]) == 30
    today_row = data["trend"][-1]
    assert today_row["date"] == inv.today().isoformat()
    assert today_row["saved"] == pytest.approx(1200.0)
    assert today_row["thrown"] == pytest.approx(800.0)


def test_summary_empty_db(app_db):
    data = stats.summary("7d")

    assert data["waste_rate"] == 0.0
    assert data["saved_grams"] == 0.0
    assert data["thrown_grams"] == 0.0
    assert data["carbon_saved_kg"] == 0.0
    assert data["equivalents"] == {"car_km": 0, "trees_days": 0}
    assert len(data["trend"]) == 7


def test_top_waste(app_db, add_item):
    add_item("西兰花", avg_grams=500.0, carbon_kg_per_kg=2.0)
    add_item("菠菜", avg_grams=200.0, carbon_kg_per_kg=1.0)

    first = inv.add_items({"items": [{"name": "西兰花", "qty": 1}]})["ids"][0]
    second = inv.add_items({"items": [{"name": "菠菜", "qty": 1}]})["ids"][0]
    inv.discard(first, "forgot")
    inv.discard(second, "spoiled")

    top = stats.top_waste(2)
    assert [row["name"] for row in top] == ["西兰花", "菠菜"]
    assert top[0]["grams"] == pytest.approx(500.0)
    assert top[0]["carbon_kg"] == pytest.approx(1.0)
