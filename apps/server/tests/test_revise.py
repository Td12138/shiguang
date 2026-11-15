"""对话改计划（契约 §6.9）：局部重排、diff 对齐、忌口生效、改不动给原因。"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

from app.domain import inventory as inv
from app.domain import plan
from app.domain import preferences
from app.domain.tools_registry import AppError

INITIAL_MEALS = {
    "meals": [
        {"day": 1, "slot": "午餐", "recipe_id": "r_egg", "reason": "快手"},
        {"day": 1, "slot": "晚餐", "recipe_id": "r_veg", "reason": "清淡"},
        {"day": 2, "slot": "午餐", "recipe_id": "r_egg", "reason": "快手"},
        {"day": 2, "slot": "晚餐", "recipe_id": "r_soup", "reason": "喝汤"},
    ]
}


def _run(coro):
    return asyncio.run(coro)


def _seed(add_item, add_recipe):
    add_item("鸡蛋", avg_grams=60.0, unit="个", shelf_life_days=10)
    add_item("西兰花", avg_grams=300.0, shelf_life_days=5)
    add_recipe(
        "r_egg",
        "西兰花炒鸡蛋",
        ingredients=[
            {"name": "西兰花", "qty": 1, "unit": "颗", "optional": False},
            {"name": "鸡蛋", "qty": 2, "unit": "个", "optional": False},
        ],
        steps=["切小朵", "打蛋", "爆香", "同炒"],
        minutes=10,
    )
    add_recipe(
        "r_veg",
        "清炒西兰花",
        ingredients=[{"name": "西兰花", "qty": 1, "unit": "颗", "optional": False}],
        steps=["切小朵", "焯水", "清炒调味"],
        minutes=8,
    )
    add_recipe(
        "r_soup",
        "蛋花汤",
        ingredients=[{"name": "鸡蛋", "qty": 2, "unit": "个", "optional": False}],
        steps=["烧水", "打蛋", "淋入汤中"],
        minutes=6,
    )
    inv.add_items(
        {
            "items": [
                {
                    "name": "西兰花",
                    "qty": 3,
                    "expires_at": (inv.today() + timedelta(days=2)).isoformat(),
                },
                {"name": "鸡蛋", "qty": 8},
            ]
        }
    )


def _build(add_item, add_recipe, fake_provider):
    _seed(add_item, add_recipe)
    provider = fake_provider(compose=INITIAL_MEALS)
    return _run(plan.build_plan(days=2, servings=1, max_minutes=30, provider=provider))


def _meal_map(plan_dict):
    return {(day["date"], meal["slot"]): meal for day in plan_dict["days"] for meal in day["meals"]}


def test_plan_is_persisted(app_db, add_item, add_recipe, fake_provider):
    created = _build(add_item, add_recipe, fake_provider)

    stored = plan.load_plan(created["plan_id"])
    assert stored["plan_id"] == created["plan_id"]
    assert stored["params"]["servings"] == 1
    assert len(stored["days"]) == 2


def test_revise_changes_only_targeted_meal(app_db, add_item, add_recipe, fake_provider):
    created = _build(add_item, add_recipe, fake_provider)
    target_date = created["days"][1]["date"]

    revised = _run(
        plan.revise(
            created["plan_id"], "第二天午餐想清淡一点", provider=fake_provider()
        )
    )

    assert revised["plan_id"] == created["plan_id"]
    assert revised["run_id"].startswith("run_")
    assert len(revised["changed"]) == 1

    change = revised["changed"][0]
    assert change["date"] == target_date
    assert change["slot"] == "午餐"
    assert change["from"] == "西兰花炒鸡蛋"
    assert change["to"] in {"清炒西兰花", "蛋花汤"}, "换成的菜必须来自候选池"
    assert change["reason"]
    change_recipe_id = "r_veg" if change["to"] == "清炒西兰花" else "r_soup"

    before = _meal_map(created)
    after = _meal_map(revised)
    assert set(before) == set(after)
    # diff 与前后计划对得上：只有被点名那一餐变了
    for key, meal in before.items():
        if key == (target_date, "午餐"):
            assert after[key]["recipe_id"] == change_recipe_id
        else:
            assert after[key]["recipe_id"] == meal["recipe_id"]

    # 改动落库，下次还能继续改
    stored = plan.load_plan(created["plan_id"])
    assert _meal_map(stored)[(target_date, "午餐")]["recipe_id"] == change_recipe_id

    from app.domain.recipes import get_run

    run = get_run(revised["run_id"])
    assert run["kind"] == "meal_plan"
    assert [step["name"] for step in run["steps"]] == [
        "understand",
        "plan",
        "allocate",
        "compose",
        "verify",
    ]


def test_revise_avoids_ingredient_everywhere(app_db, add_item, add_recipe, fake_provider):
    created = _build(add_item, add_recipe, fake_provider)

    revised = _run(
        plan.revise(created["plan_id"], "不要鸡蛋", provider=fake_provider())
    )

    meals = [meal for day in revised["days"] for meal in day["meals"]]
    assert meals
    used = {row["name"] for meal in meals for row in meal["uses"]}
    missing = {row["name"] for meal in meals for row in meal["missing"]}
    assert "鸡蛋" not in used
    assert "鸡蛋" not in missing
    assert all(meal["recipe_id"] not in {"r_egg", "r_soup"} for meal in meals)
    assert revised["changed"], "去掉鸡蛋必须产生改动"
    assert all(change["to"] != "西兰花炒鸡蛋" for change in revised["changed"])

    # 学到的偏好：不吃鸡蛋
    assert any(row["kind"] == "avoid" and "鸡蛋" in row["text"] for row in revised["learned"])
    stored = {row["text"] for row in preferences.list_preferences()}
    assert any("鸡蛋" in text for text in stored)
    # 再生成计划时忌口继续生效
    again = _run(plan.build_plan(days=1, servings=1, provider=None))
    used_again = {
        row["name"] for day in again["days"] for meal in day["meals"] for row in meal["uses"]
    }
    assert "鸡蛋" not in used_again


def test_revise_reports_readable_reason_when_nothing_matches(
    app_db, add_item, add_recipe, fake_provider
):
    created = _build(add_item, add_recipe, fake_provider)

    revised = _run(
        plan.revise(created["plan_id"], "不要鸡蛋，也不要西兰花", provider=fake_provider())
    )

    assert revised["changed"] == []
    assert any("没有符合条件的菜谱" in warning for warning in revised["warnings"])
    assert revised["days"] == created["days"], "改不动时必须原样返回，且说明原因"


def test_revise_rejects_out_of_range_day(app_db, add_item, add_recipe, fake_provider):
    created = _build(add_item, add_recipe, fake_provider)

    revised = _run(
        plan.revise(created["plan_id"], "第三天想清淡一点", provider=fake_provider())
    )

    assert revised["changed"] == []
    assert any("只有 2 天" in warning for warning in revised["warnings"])


def test_revise_conflict_with_remembered_preference(app_db, add_item, add_recipe, fake_provider):
    created = _build(add_item, add_recipe, fake_provider)
    preferences.add_preference("不吃鸡蛋", "avoid")

    revised = _run(
        plan.revise(created["plan_id"], "第一天晚餐想吃鸡蛋", provider=fake_provider())
    )

    assert any("冲突" in warning for warning in revised["warnings"])
    assert revised["changed"], "指令优先，应该按用户这次的要求改"
    new_meal = _meal_map(revised)[(created["days"][0]["date"], "晚餐")]
    assert new_meal["recipe_id"] == "r_egg", "本次指令优先，鸡蛋允许进计划"


def test_revise_missing_plan(app_db):
    with pytest.raises(AppError) as excinfo:
        _run(plan.revise("plan_nope", "第二天清淡点"))
    assert excinfo.value.status == 404
    assert excinfo.value.code == "plan_not_found"
