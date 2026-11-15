"""工具注册表 + OpenAI function calling schema（契约 §7.1 / §9）。

A 只提供 schema 与注册表；**具体实现由 B 在 domain 层启动时 ``register``**。
未注册时 ``call`` 返回 ``{"error": "tool_not_registered"}``，不抛异常、不中断 Agent 流水线。
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.errors import AppError

LOGGER = logging.getLogger(__name__)

TOOL_LIST_INVENTORY = "list_inventory"
TOOL_FIND_RECIPES = "find_recipes"
TOOL_GET_SHELF_LIFE = "get_shelf_life"
TOOL_ESTIMATE_CARBON = "estimate_carbon"
TOOL_LOG_CONSUMPTION = "log_consumption"

TOOL_NAMES: tuple[str, ...] = (
    TOOL_LIST_INVENTORY,
    TOOL_FIND_RECIPES,
    TOOL_GET_SHELF_LIFE,
    TOOL_ESTIMATE_CARBON,
    TOOL_LOG_CONSUMPTION,
)

_SCHEMA_LIST_INVENTORY: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": TOOL_LIST_INVENTORY,
        "description": "列出冰箱库存，默认按临期程度排序，用于找出最该先吃掉的食材。",
        "parameters": {
            "type": "object",
            "properties": {
                "sort": {
                    "type": "string",
                    "enum": ["expiry", "added", "qty"],
                    "description": "排序口径：expiry=按到期日升序（默认），added=按入库时间，qty=按数量",
                },
                "status": {
                    "type": "string",
                    "enum": ["active", "consumed", "discarded"],
                    "description": "库存状态，默认 active",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 50,
                    "description": "最多返回几条，默认 10",
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    },
}

_SCHEMA_FIND_RECIPES: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": TOOL_FIND_RECIPES,
        "description": "按可用食材与时间约束混合检索菜谱（FTS5 + 可选向量），返回带引用来源的候选列表。",
        "parameters": {
            "type": "object",
            "properties": {
                "ingredients": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "手头可用食材名称列表（来自库存）",
                },
                "max_minutes": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 240,
                    "description": "最长可接受烹饪时间（分钟）",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "description": "候选数量，默认 5",
                },
            },
            "required": ["ingredients"],
            "additionalProperties": False,
        },
    },
}

_SCHEMA_GET_SHELF_LIFE: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": TOOL_GET_SHELF_LIFE,
        "description": "查询某食材在指定储存方式下的建议保质期（天）与保存技巧。",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "食材名称，如「西兰花」"},
                "storage": {
                    "type": "string",
                    "enum": ["fridge", "freezer", "room"],
                    "description": "储存方式：fridge=冷藏（默认），freezer=冷冻，room=常温",
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
}

_SCHEMA_ESTIMATE_CARBON: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": TOOL_ESTIMATE_CARBON,
        "description": "按公开因子表估算食材碳当量（kgCO2e），用于统计页碳账。",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "食材名称；缺省时按通用蔬菜因子估算"},
                "grams": {"type": "number", "minimum": 0, "description": "重量（克）"},
            },
            "required": ["grams"],
            "additionalProperties": False,
        },
    },
}

_SCHEMA_LOG_CONSUMPTION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": TOOL_LOG_CONSUMPTION,
        "description": "记录一次消耗或丢弃，扣减库存（丢弃同时写 waste_log 与碳账）。",
        "parameters": {
            "type": "object",
            "properties": {
                "inventory_id": {"type": "string", "description": "库存记录 id，如 inv_xxx"},
                "action": {
                    "type": "string",
                    "enum": ["consume", "discard"],
                    "description": "consume=吃掉，discard=丢弃",
                },
                "grams": {"type": "number", "minimum": 0, "description": "本次重量（克）；缺省按整份扣减"},
                "reason": {
                    "type": "string",
                    "enum": ["forgot", "spoiled", "too_much"],
                    "description": "丢弃原因，仅 action=discard 时必填",
                },
            },
            "required": ["inventory_id", "action"],
            "additionalProperties": False,
        },
    },
}

# 契约 §7.1：5 个工具的 OpenAI function calling schema
TOOL_SCHEMAS: list[dict[str, Any]] = [
    _SCHEMA_LIST_INVENTORY,
    _SCHEMA_FIND_RECIPES,
    _SCHEMA_GET_SHELF_LIFE,
    _SCHEMA_ESTIMATE_CARBON,
    _SCHEMA_LOG_CONSUMPTION,
]

ToolFn = Callable[..., Any] | Callable[..., Awaitable[Any]]
_REGISTRY: dict[str, ToolFn] = {}


def register(name: str, fn: ToolFn) -> None:
    """B 在 domain 层启动时注册实现；同名重复注册以最后一次为准（便于测试覆盖）。"""
    if name not in TOOL_NAMES:
        LOGGER.warning("注册了契约外的工具 %s（不参与 function calling 曝光）", name)
    if name in _REGISTRY:
        LOGGER.info("工具 %s 被重新注册", name)
    _REGISTRY[name] = fn
    LOGGER.info("工具已注册：%s", name)


def is_registered(name: str) -> bool:
    return name in _REGISTRY


def registered_names() -> list[str]:
    return sorted(_REGISTRY)


def unregister_all() -> None:
    """测试用：清空注册表。"""
    _REGISTRY.clear()


async def call(name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """调用工具。未注册 → ``{"error": "tool_not_registered"}``；实现异常 → 结构化错误。"""
    fn = _REGISTRY.get(name)
    if fn is None:
        LOGGER.warning("工具 %s 未注册，返回 tool_not_registered", name)
        return {"error": "tool_not_registered", "tool": name, "registered": registered_names()}

    kwargs = args or {}
    try:
        result = fn(**kwargs)
        if inspect.isawaitable(result):
            result = await result
    except AppError as exc:
        LOGGER.warning("工具 %s 业务错误：%s", name, exc)
        return {"error": exc.code, "tool": name, "message": exc.message}
    except TypeError as exc:
        LOGGER.warning("工具 %s 参数不匹配：%s", name, exc)
        return {"error": "tool_bad_args", "tool": name, "message": str(exc)}
    except Exception as exc:  # 工具失败不炸整条流水线
        LOGGER.exception("工具 %s 执行失败", name)
        return {"error": "tool_failed", "tool": name, "message": type(exc).__name__}

    if isinstance(result, dict):
        return result
    return {"result": result}
