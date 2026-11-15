"""Function Calling 工具（契约 §7.1）：schema 参数必须都能被真实函数接受。"""

from __future__ import annotations

import asyncio
import inspect

import pytest

from app.core import tools
from app.domain import inventory as inv
from app.domain import tools_registry


@pytest.fixture()
def registry(app_db):
    """把 domain 的 5 个实现注册进 core 注册表（生产由 register_all 做）。"""
    tools.unregister_all()
    for name, fn in tools_registry.TOOL_FUNCTIONS.items():
        tools.register(name, fn)
    # 结束时保持注册状态，与生产启动后一致（不给后续测试留空注册表）
    yield tools


def _call(name: str, args: dict) -> dict:
    return asyncio.run(tools.call(name, args))


def test_schema_properties_match_function_signatures():
    """每个 schema 的 properties 都必须是函数可接受的参数名，否则合法调用会 tool_bad_args。"""
    for schema in tools.TOOL_SCHEMAS:
        function = schema["function"]
        name = function["name"]
        fn = tools_registry.TOOL_FUNCTIONS[name]
        signature = inspect.signature(fn)
        params = set(signature.parameters)

        properties = set(function["parameters"].get("properties", {}))
        required = set(function["parameters"].get("required", []))

        assert properties <= params, f"{name} schema 参数不在签名里：{properties - params}"
        assert required <= params, f"{name} 必填参数不在签名里：{required - params}"


def test_call_list_inventory_with_status(registry, add_item):
    add_item("西兰花", avg_grams=300.0)
    inv.add_items({"items": [{"name": "西兰花", "qty": 2}]})

    result = _call(
        "list_inventory", {"sort": "expiry", "status": "active", "limit": 5}
    )

    assert "error" not in result, result
    assert result["count"] == 1
    assert result["items"][0]["name"] == "西兰花"

    consumed = _call("list_inventory", {"status": "consumed", "limit": 5})
    assert "error" not in consumed, consumed
    assert consumed["items"] == []


def test_call_get_shelf_life_with_storage(registry, add_item):
    add_item("西兰花", shelf_life_days=5, storage_tip="冷藏别洗")

    result = _call("get_shelf_life", {"name": "西兰花", "storage": "freezer"})

    assert "error" not in result, result
    assert result["matched"] is True
    assert result["storage"] == "freezer"
    assert result["shelf_life_days"] == 5
    assert "storage_note" in result, "非冷藏口径要明确说明，不能假装是冷冻实测天数"


def test_call_estimate_carbon_without_name(registry, add_item):
    """schema 里 name 可选：只给 grams 也必须能调用。"""
    add_item("西兰花", carbon_kg_per_kg=2.5, price_per_kg=10.0)

    result = _call("estimate_carbon", {"grams": 100})

    assert "error" not in result, result
    assert result["grams"] == 100
    assert result["matched"] is False
    assert result["carbon_kg"] == 0.0

    named = _call("estimate_carbon", {"name": "西兰花", "grams": 100})
    assert "error" not in named, named
    assert named["carbon_kg"] == pytest.approx(0.25)


def test_call_log_consumption_consume(registry, add_item):
    add_item("鸡蛋", avg_grams=60.0, unit="个")
    inv_id = inv.add_items({"items": [{"name": "鸡蛋", "qty": 3}]})["ids"][0]

    result = _call(
        "log_consumption",
        {"inventory_id": inv_id, "action": "consume", "grams": 120},
    )

    assert "error" not in result, result
    assert result["consumed_grams"] == pytest.approx(120.0)
    assert inv.get_inventory(inv_id)["grams"] == pytest.approx(60.0)


def test_call_log_consumption_discard(registry, add_item):
    add_item("生菜", avg_grams=300.0, unit="颗", carbon_kg_per_kg=1.8)
    inv_id = inv.add_items({"items": [{"name": "生菜", "qty": 2}]})["ids"][0]

    result = _call(
        "log_consumption",
        {
            "inventory_id": inv_id,
            "action": "discard",
            "grams": 150,
            "reason": "spoiled",
        },
    )

    assert "error" not in result, result
    assert result["action"] == "discard"
    assert result["discarded_grams"] == pytest.approx(150.0)
    assert result["carbon_kg"] == pytest.approx(0.27)
    assert inv.get_inventory(inv_id)["grams"] == pytest.approx(450.0)


def test_call_find_recipes_with_schema_args(registry, add_item, add_recipe):
    add_item("西兰花", avg_grams=300.0)
    add_recipe("r_broccoli", "蒜蓉西兰花", minutes=15)

    result = _call(
        "find_recipes",
        {"ingredients": ["西兰花"], "max_minutes": 30, "limit": 3},
    )

    assert "error" not in result, result
    assert result["count"] >= 1
    assert result["items"][0]["recipe_id"] == "r_broccoli"
