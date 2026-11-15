"""mock 提供方：没有任何 API key 也能跑通全链路（契约 §2 P0-7 / §7）。

数据来源：``app/data/fixtures/``（D 层生成，可能暂时不存在）→ 缺失时回退内置最小样例。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel, ValidationError

from app import config
from app.core.errors import AppError
from app.core.safety import DISCLAIMER_CARBON

LOGGER = logging.getLogger(__name__)

PROVIDER_NAME = "mock"
FIXTURE_RECOGNIZE = "recognize_fridge.json"
FIXTURE_SUGGEST = "suggest.json"
FIXTURE_PLAN = "plan.json"

# 内置视觉样例：模拟真实 VLM 的原始输出（只有名称/数量/单位/置信度），
# item_id / shelf_life_days / expires_at / matched 由 B 层对照食材库补齐（契约 §6.2）。
# 第 3 条故意低置信度且不在食材库，用于演示低置信度黄标与碳账过滤（§10.3 / §10.4）。
_MOCK_VISION_ITEMS: tuple[dict[str, Any], ...] = (
    {"name": "西兰花", "qty": 1, "unit": "颗", "confidence": 0.94},
    {"name": "鸡胸肉", "qty": 1, "unit": "块", "confidence": 0.86},
    {"name": "不知名野菜", "qty": 1, "unit": "把", "confidence": 0.41},
)

_MOCK_VISION_WARNING = "当前为 mock 回放数据（未调用真实视觉模型），识别结果请人工确认"

# 内置菜谱样例：id / title / minutes 必须与 app/data/recipes.json 完全一致，
# 否则 verify 步骤会把它们全部剔除（审查缺陷 §mock-1）
_MOCK_SUGGEST: dict[str, Any] = {
    "recommendations": [
        {
            "recipe_id": "r_002",
            "title": "蒜蓉西兰花",
            "minutes": 12,
            "reason": "用掉冰箱里剩 2 天到期的西兰花，只需再加蒜和蚝油。",
            "missing": [{"name": "大蒜", "optional": True}, {"name": "蚝油", "optional": True}],
            "citations": [{"source": "recipe:r_002", "locator": "步骤 1-4"}],
            "score": 0.83,
        },
        {
            "recipe_id": "r_001",
            "title": "番茄炒蛋",
            "minutes": 10,
            "reason": "番茄明天到期，鸡蛋库存够，十分钟出锅。",
            "missing": [],
            "citations": [{"source": "recipe:r_001", "locator": "步骤 1-3"}],
            "score": 0.76,
        },
        {
            "recipe_id": "r_003",
            "title": "菠菜蛋花汤",
            "minutes": 10,
            "reason": "菠菜已过期请先处理；若换成小白菜，这道汤最适合清掉叶菜。",
            "missing": [],
            "citations": [{"source": "recipe:r_003", "locator": "步骤 1-3"}],
            "score": 0.68,
        },
    ],
    "warnings": ["mock 提供方未调用真实模型，结果为内置样例"],
}

_MOCK_REPORT_TEXT = (
    "（mock 回放：未调用真实大模型，以下不是真实统计，数字请以页面统计卡片为准。）"
    "周报由规则模板生成，不会再编一套与统计页对不上的数字。"
    f"（{DISCLAIMER_CARBON}。）"
)

_MOCK_TEXT = "（mock）当前使用内置回放数据，未调用真实大模型。"


def _load_fixture(filename: str) -> Any | None:
    """读 D 层 fixture；文件缺失或格式坏掉一律返回 None（绝不抛异常）。"""
    path = config.FIXTURES_DIR / filename
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        LOGGER.info("mock fixture 缺失：%s，使用内置样例", path)
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.warning("mock fixture 读取失败：%s（%s），使用内置样例", path, type(exc).__name__)
    return None


def _as_items(data: Any) -> list[dict[str, Any]] | None:
    """兼容 fixture 的两种形态：``[...]`` 或 ``{"items": [...]}``。"""
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        rows = data.get("items")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return None


def _fallback_vision() -> dict[str, Any]:
    """内置样例（3 条）：字段与真实 VLM 原始输出一致，便于 B 层统一补齐。"""
    items = [dict(row) for row in _MOCK_VISION_ITEMS]
    return {"items": items, "warnings": [_MOCK_VISION_WARNING]}


def _fallback_suggest() -> dict[str, Any]:
    return json.loads(json.dumps(_MOCK_SUGGEST))  # 深拷贝，防止调用方改坏常量


def _message_text(message: Any) -> str:
    """把 message 的 content（str 或分段列表）压成纯文本，供 mock 关键词判断。"""
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            str(part.get("text", "")) for part in content if isinstance(part, dict)
        )
    return ""


def _wants(messages: list[dict], words: tuple[str, ...]) -> bool:
    haystack = " ".join(_message_text(message) for message in messages).lower()
    return any(word in haystack for word in words)


def _wants_recipes(messages: list[dict], schema: type[BaseModel] | None) -> bool:
    keywords = ("菜谱", "推荐", "recipe", "suggest", "排序", "compose", "recommend")
    haystack = (schema.__name__ if schema is not None else "") + " ".join(
        _message_text(message) for message in messages
    )
    lowered = haystack.lower()
    return any(word in lowered for word in keywords)


CONSTRAINT_KEYWORDS = ("意图", "servings", "人数", "口味", "constraint")
PLAN_KEYWORDS = ("配餐", "饮食计划", "meal plan", "mealplan", "几天吃")


def _defaults_for(schema: type[BaseModel]) -> dict[str, Any] | None:
    """schema 全字段有默认值时，直接给默认值（用于 understand 等轻量步骤）。"""
    try:
        return schema().model_dump()
    except ValidationError:
        return None


def _validate(schema: type[BaseModel] | None, data: Any) -> dict[str, Any] | None:
    if schema is None:
        return data if isinstance(data, dict) else None
    try:
        return schema.model_validate(data).model_dump()
    except ValidationError as exc:
        LOGGER.warning("mock 数据不符合 %s：%s 处字段缺失", schema.__name__, len(exc.errors()))
        return None


class MockProvider:
    """契约 §7.1 的 mock 实现：确定性、零网络、零密钥。"""

    name = PROVIDER_NAME

    async def chat_json(
        self,
        messages: list[dict],
        *,
        schema: type[BaseModel] | None = None,
        timeout: float = config.LLM_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        """与真实 provider 同一套语义：校验 → 重试 1 次 → 仍不合法就明确报错。

        审查缺陷 §mock-2：旧实现在 schema 校验失败时直接返回候选数据，
        且无 schema 时一律返回菜谱推荐（understand 步骤会拿到错的 JSON）。
        """
        candidate = self._pick_payload(messages, schema)
        for _attempt in range(config.LLM_RETRY_TIMES + 1):
            validated = _validate(schema, candidate)
            if validated is not None:
                return validated
            if schema is not None:
                defaults = _defaults_for(schema)
                if defaults is not None:
                    return defaults
        raise AppError(
            "llm_invalid_json",
            "mock 回放数据与 schema 不匹配（请检查 app/data/fixtures）",
            502,
        )

    def _pick_payload(
        self, messages: list[dict], schema: type[BaseModel] | None
    ) -> dict[str, Any]:
        """按提示词意图挑一份回放数据，顺序不能乱：约束 > 计划 > 菜谱。"""
        if schema is not None and _defaults_for(schema) is not None and not _wants_recipes(
            messages, schema
        ):
            defaults = _defaults_for(schema)
            if defaults is not None:
                return defaults
        if _wants(messages, CONSTRAINT_KEYWORDS):
            return {"max_minutes": 30, "servings": 1, "taste": None, "note": "mock：按输入参数执行"}
        if _wants(messages, PLAN_KEYWORDS):
            fixture = _load_fixture(FIXTURE_PLAN)
            if isinstance(fixture, dict):
                return fixture
            return {"days": [], "shopping": [], "warnings": ["mock 未配置 plan.json"]}
        fixture = _load_fixture(FIXTURE_SUGGEST)
        return fixture if isinstance(fixture, dict) else _fallback_suggest()

    async def chat_text(
        self,
        messages: list[dict],
        *,
        timeout: float = config.LLM_TIMEOUT_SECONDS,
    ) -> str:
        return _MOCK_TEXT

    async def chat_vision(
        self,
        image_b64: str,
        mime: str,
        prompt: str,
        *,
        timeout: float = config.LLM_VISION_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        fixture = _load_fixture(FIXTURE_RECOGNIZE)
        items = _as_items(fixture)
        if items:
            result = dict(fixture) if isinstance(fixture, dict) else {"items": items}
            result["items"] = items
            result.setdefault("warnings", [])
            if _MOCK_VISION_WARNING not in result["warnings"]:
                result["warnings"] = [*result["warnings"], _MOCK_VISION_WARNING]
            return result
        return _fallback_vision()

    async def stream_chat(self, messages: list[dict]) -> AsyncIterator[str]:
        sizes = config.MOCK_STREAM_CHUNK_SIZES
        text = _MOCK_REPORT_TEXT
        index, step = 0, 0
        while index < len(text):
            size = sizes[step % len(sizes)]
            yield text[index : index + size]
            index += size
            step += 1
            await asyncio.sleep(config.MOCK_STREAM_DELAY_SECONDS)


__all__ = [
    "FIXTURE_RECOGNIZE",
    "FIXTURE_SUGGEST",
    "MockProvider",
    "PROVIDER_NAME",
]
