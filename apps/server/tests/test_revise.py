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


def _seed(add_item, add_recipe, eggs_qty: float = 8):
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
                {"name": "鸡蛋", "qty": eggs_qty},
            ]
        }
    )


def _build(add_item, add_recipe, fake_provider, eggs_qty: float = 8):
    _seed(add_item, add_recipe, eggs_qty=eggs_qty)
    provider = fake_provider(compose=INITIAL_MEALS)
    return _run(plan.build_plan(days=2, servings=1, max_minutes=30, provider=provider))


def _inventory_id(name: str) -> str:
    return next(row["id"] for row in inv.list_inventory() if row["name"] == name)


class _CapturingProvider:
    """记录 Prompt 的假 provider：回空意图，让 revise 走规则版解析。"""

    name = "capturing"

    def __init__(self) -> None:
        self.messages: list[list[dict]] = []

    async def chat_json(self, messages, *, schema=None, timeout: float = 60):
        self.messages.append(messages)
        return {}


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


# --------------------------------------------------------------------------- #
# 缺陷 1：未涉及的餐次不许漂移（契约 §6.9 规则 1）
# --------------------------------------------------------------------------- #

def test_revise_keeps_untouched_meals_after_inventory_change(
    app_db, add_item, add_recipe, fake_provider
):
    """先吃掉食材，再改另一餐 → 未涉及餐的 uses/missing 一个字都不变。"""
    created = _build(add_item, add_recipe, fake_provider)
    before = _meal_map(created)
    target = (created["days"][0]["date"], "午餐")

    inv.consume(_inventory_id("鸡蛋"), 300)  # 鸡蛋 8 → 3，比原计划用量还少

    revised = _run(
        plan.revise(
            created["plan_id"], "第一天午餐换成清炒西兰花", provider=fake_provider()
        )
    )

    after = _meal_map(revised)
    assert set(before) == set(after)
    for key, meal in before.items():
        if key == target:
            continue
        assert after[key] == meal, f"{key} 未涉及，必须与存档逐字一致（含 uses/missing/citations）"

    assert len(revised["changed"]) == 1
    assert revised["changed"][0]["date"] == target[0]
    assert revised["changed"][0]["slot"] == target[1]
    assert revised["changed"][0]["to"] == "清炒西兰花"
    assert revised["shopping"] == created["shopping"], "未涉及餐次没缺料，购物清单不该变"

    # 库存被动过：计划总量可能超过现库存 → 必须有显式提示，不许静默改用量
    assert any("当前库存" in warning for warning in revised["warnings"])


def test_revise_keeps_shopping_when_revising_other_meal(
    app_db, add_item, add_recipe, fake_provider
):
    """原计划本来就有缺料（购物清单非空），改另一餐后清单逐字不变。"""
    created = _build(add_item, add_recipe, fake_provider, eggs_qty=2)
    assert created["shopping"], "这个用例需要一份本来就有采购项的计划"
    frozen_shopping = created["shopping"]
    before = _meal_map(created)
    target = (created["days"][0]["date"], "午餐")

    inv.consume(_inventory_id("西兰花"), 300)  # 西兰花 3 → 2

    revised = _run(
        plan.revise(created["plan_id"], "第一天午餐想清淡一点", provider=fake_provider())
    )

    assert revised["changed"], "点名的午餐要真的改动"
    after = _meal_map(revised)
    for key, meal in before.items():
        if key == target:
            continue
        assert after[key] == meal
    assert revised["shopping"] == frozen_shopping, "未涉及餐次的缺料清单不能重算"


# --------------------------------------------------------------------------- #
# 缺陷 2：点名菜换不成必须说清楚，不许换错菜还报成功
# --------------------------------------------------------------------------- #

def test_revise_reports_named_dish_not_found(app_db, add_item, add_recipe, fake_provider):
    created = _build(add_item, add_recipe, fake_provider)

    revised = _run(
        plan.revise(created["plan_id"], "第二天午餐换成麻婆豆腐", provider=fake_provider())
    )

    assert revised["changed"] == []
    assert revised["days"] == created["days"]
    assert any("没能换成麻婆豆腐" in warning for warning in revised["warnings"])
    assert any("菜谱库里没有" in warning for warning in revised["warnings"])


def test_revise_reports_named_dish_too_slow(app_db, add_item, add_recipe, fake_provider):
    created = _build(add_item, add_recipe, fake_provider)
    add_recipe(
        "r_slow",
        "慢炖牛腩",
        ingredients=[{"name": "西兰花", "qty": 1, "unit": "颗", "optional": False}],
        steps=["焯水", "下锅", "慢炖 40 分钟"],
        minutes=45,
    )

    revised = _run(
        plan.revise(created["plan_id"], "第二天午餐换成慢炖牛腩", provider=fake_provider())
    )

    assert revised["changed"] == []
    assert revised["days"] == created["days"]
    assert any("没能换成慢炖牛腩" in warning for warning in revised["warnings"])
    assert any("45 分钟" in warning for warning in revised["warnings"])


def test_revise_reports_named_dish_without_stock(
    app_db, add_item, add_recipe, fake_provider
):
    created = _build(add_item, add_recipe, fake_provider)
    add_recipe(
        "r_chicken",
        "麻油鸡",
        ingredients=[{"name": "鸡肉", "qty": 1, "unit": "块", "optional": False}],
        steps=["切块", "煸香", "淋麻油"],
        minutes=12,
    )

    revised = _run(
        plan.revise(created["plan_id"], "第二天午餐换成麻油鸡", provider=fake_provider())
    )

    assert revised["changed"] == [], "库存不够也不许偷偷换别的菜"
    assert revised["days"] == created["days"]
    assert any("没能换成麻油鸡" in warning for warning in revised["warnings"])
    assert any("现有食材做不了" in warning for warning in revised["warnings"])


def test_revise_named_dish_already_on_plan_does_not_lie(
    app_db, add_item, add_recipe, fake_provider
):
    """点名「西兰花」，当前这餐本来就用西兰花 → 明说不用换，不许换成别的菜还报成功。"""
    created = _build(add_item, add_recipe, fake_provider)
    inv.consume(_inventory_id("西兰花"), 300)

    revised = _run(
        plan.revise(created["plan_id"], "第一天午餐换成西兰花", provider=fake_provider())
    )

    assert revised["changed"] == []
    assert revised["days"] == created["days"]
    assert any("不用换" in warning for warning in revised["warnings"])
    assert all("没能换成" not in warning for warning in revised["warnings"])


# --------------------------------------------------------------------------- #
# 缺陷 3：软偏好必须参与改计划
# --------------------------------------------------------------------------- #

def test_revise_applies_soft_preference(app_db, add_item, add_recipe, fake_provider):
    created = _build(add_item, add_recipe, fake_provider)
    preferences.add_preference("口味清淡，少油少盐", "health")
    provider = _CapturingProvider()

    revised = _run(
        plan.revise(created["plan_id"], "第二天午餐想清淡一点", provider=provider)
    )

    assert revised["changed"], "清淡指令要真的改动"
    from app.domain.recipes import get_run

    run = get_run(revised["run_id"])
    plan_step = next(step for step in run["steps"] if step["name"] == "plan")
    assert "已应用 1 条偏好" in plan_step["summary"]
    assert "口味清淡" in plan_step["summary"]

    # 软偏好也进同一份 Prompt（契约 §6.10）
    prompts = [
        str(message.get("content") or "")
        for messages in provider.messages
        for message in messages
        if message.get("role") == "user"
    ]
    assert any("口味清淡" in prompt for prompt in prompts)

