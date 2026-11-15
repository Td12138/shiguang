"""饮食计划（契约 §6.8）：过期排除、库存上限收敛、真实引用、降级、空库存。"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from app.db.conn import get_conn
from app.domain import inventory as inv
from app.domain import plan

STAGES = ["understand", "plan", "allocate", "compose", "verify"]


def _run(coro):
    return asyncio.run(coro)


def _seed(add_item, add_recipe):
    add_item("西兰花", avg_grams=300.0, shelf_life_days=5)
    add_item("鸡蛋", avg_grams=60.0, shelf_life_days=10, unit="个")
    add_recipe(
        "r_broccoli",
        "蒜蓉西兰花",
        ingredients=[
            {"name": "西兰花", "qty": 1, "unit": "颗", "optional": False},
            {"name": "大蒜", "qty": 2, "unit": "瓣", "optional": False},
        ],
        steps=["切小朵", "蒜切末", "爆香", "翻炒"],
        minutes=15,
    )
    add_recipe(
        "r_egg",
        "西兰花炒鸡蛋",
        ingredients=[
            {"name": "西兰花", "qty": 1, "unit": "颗", "optional": False},
            {"name": "鸡蛋", "qty": 2, "unit": "个", "optional": False},
        ],
        steps=["焯水", "打蛋", "同炒"],
        minutes=10,
    )
    inv.add_items(
        {
            "items": [
                {"name": "西兰花", "qty": 1, "expires_at": (inv.today() + timedelta(days=2)).isoformat()},
                {"name": "鸡蛋", "qty": 6},
            ]
        }
    )


def test_expired_item_excluded_with_warning(app_db, add_item, add_recipe, no_llm):
    add_item("菠菜", avg_grams=200.0, shelf_life_days=2, unit="把")
    add_recipe(
        "r_mix",
        "菠菜西兰花",
        ingredients=[{"name": "菠菜", "qty": 1, "unit": "把"}, {"name": "西兰花", "qty": 1, "unit": "颗"}],
        steps=["洗菜", "焯水", "翻炒"],
        minutes=12,
    )
    add_item("西兰花", avg_grams=300.0, shelf_life_days=5)
    inv.add_items(
        {
            "items": [
                {"name": "菠菜", "qty": 1, "expires_at": (inv.today() - timedelta(days=1)).isoformat()},
                {"name": "西兰花", "qty": 2, "expires_at": (inv.today() + timedelta(days=2)).isoformat()},
            ]
        }
    )

    result = _run(plan.build_plan(days=1, servings=1, max_minutes=30, provider=None))

    used_names = {row["name"] for day in result["days"] for meal in day["meals"] for row in meal["uses"]}
    assert "菠菜" not in used_names
    assert any("过期" in warning for warning in result["warnings"])


def test_verify_rejects_plan_that_uses_expired_item(app_db, add_item, add_recipe):
    add_item("菠菜", avg_grams=200.0, shelf_life_days=2, unit="把")
    add_recipe("r_mix", "菠菜汤", ingredients=[{"name": "菠菜"}], steps=["洗", "煮", "调味"], minutes=8)
    inv.add_items(
        {"items": [{"name": "菠菜", "qty": 1, "expires_at": (inv.today() - timedelta(days=2)).isoformat()}]}
    )

    snapshot = plan._split_inventory(inv.list_inventory("active"))
    assert snapshot["expired"], "过期库存应被识别"
    forged_days = [
        {
            "date": inv.today().isoformat(),
            "meals": [
                {
                    "slot": "午餐",
                    "recipe_id": "r_mix",
                    "title": "菠菜汤",
                    "minutes": 8,
                    "uses": [{"name": "菠菜", "qty": 1, "unit": "把"}],
                    "missing": [],
                    "citations": [{"source": "recipe:r_mix", "locator": "步骤 1-3"}],
                }
            ],
        }
    ]
    _coverage, problems = plan.verify(forged_days, [], snapshot)
    assert any("过期" in problem for problem in problems)


def test_same_item_usage_stays_within_stock(app_db, add_item, add_recipe, no_llm):
    _seed(add_item, add_recipe)

    result = _run(plan.build_plan(days=2, servings=1, max_minutes=30, provider=None))

    used: dict[str, float] = {}
    for day in result["days"]:
        for meal in day["meals"]:
            assert meal["recipe_id"] in {"r_broccoli", "r_egg"}
            for row in meal["uses"]:
                used[row["name"]] = used.get(row["name"], 0.0) + float(row["qty"])

    assert used.get("西兰花", 0.0) <= 1.0 + 1e-6, used
    assert sum(len(day["meals"]) for day in result["days"]) >= 2
    # 用量收敛后，超出部分应进购物清单
    assert any(row["name"] == "西兰花" for row in result["shopping"])
    assert not any("校验仍有" in warning for warning in result["warnings"])


def test_meals_have_real_recipe_and_citations(app_db, add_item, add_recipe, no_llm):
    _seed(add_item, add_recipe)

    result = _run(plan.build_plan(days=1, servings=1, max_minutes=30, provider=None))

    conn = get_conn()
    try:
        known = {row["id"] for row in conn.execute("SELECT id FROM recipes").fetchall()}
    finally:
        conn.close()

    meals = [meal for day in result["days"] for meal in day["meals"]]
    assert meals
    for meal in meals:
        assert meal["recipe_id"] in known
        assert meal["citations"]
        assert meal["citations"][0]["source"].startswith("recipe:")
        assert meal["reason"]

    coverage = result["coverage"]
    assert coverage["used_items"] >= 1
    assert coverage["expiring_used"] >= 1  # 西兰花 2 天后到期，应优先用掉
    assert result["run_id"].startswith("run_")
    assert result["plan_id"].startswith("plan_")

    from app.domain.recipes import get_run as read_run

    run = read_run(result["run_id"])
    assert run["kind"] == "meal_plan"
    assert [step["name"] for step in run["steps"]] == STAGES


def test_shopping_list_has_no_duplicates(app_db, add_item, add_recipe, no_llm):
    _seed(add_item, add_recipe)

    result = _run(plan.build_plan(days=2, servings=2, max_minutes=30, provider=None))

    names = [row["name"] for row in result["shopping"]]
    assert len(names) == len(set(names))
    assert all(row["reason"] for row in result["shopping"])


def test_degraded_path_still_valid(app_db, add_item, add_recipe, monkeypatch):
    _seed(add_item, add_recipe)
    monkeypatch.setattr(plan, "resolve_provider", lambda provider=None: None)

    result = _run(plan.build_plan(days=2, servings=1, max_minutes=30))

    assert any("已降级" in warning for warning in result["warnings"])
    meals = [meal for day in result["days"] for meal in day["meals"]]
    assert meals, "降级也要产出计划"
    assert all(meal["citations"] for meal in meals)
    assert not any("校验仍有" in warning for warning in result["warnings"])


def test_empty_inventory_returns_empty_plan(app_db, no_llm):
    result = _run(plan.build_plan(days=3, servings=1, max_minutes=30, provider=None))

    assert result["days"] == []
    assert result["shopping"] == []
    assert result["coverage"] == {"used_items": 0, "expiring_used": 0, "unused_expiring": 0}
    assert any("库存为空" in warning for warning in result["warnings"])
    assert result["plan_id"].startswith("plan_")
