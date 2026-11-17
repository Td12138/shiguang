"""周报生成（契约 §6.6，SSE 事件流）。

优先走 `provider.stream_chat` 流式输出；模型不可用/中断时用确定性模板文本，
最后统一发 `{"type":"citations"}` 与 `{"type":"done"}`。
"""

from __future__ import annotations

import inspect
import json
import logging
from typing import AsyncIterator

from app.domain import stats
from app.domain.tools_registry import resolve_provider
from app.rag import citations as citation_utils
from app.rag import retrieve

logger = logging.getLogger(__name__)

REPORT_RANGE = "30d"
TIP_QUERY_LIMIT = 2
TEMPLATE_CHUNK_SIZE = 40
DISCLAIMER = "碳当量为估算，基于公开因子表。"
MOCK_PROVIDER_NAME = "mock"
# 区间代码 → 人话（周报正文不该出现 "30d" 这种内部口径）
RANGE_LABELS = {"7d": "近 7 天", "30d": "近 30 天", "all": "全部记录"}
GRAMS_PER_KG = 1000

SYSTEM_PROMPT = (
    "阶段：report\n你是「食光」的剩食管家，用中文写一段轻松的周报，"
    "只使用给定数字，不要编造；引用写在句末的 [1][2] 编号。"
)


def _pct(value: float) -> str:
    return f"{round(float(value) * 100)}%"


def _range_label(value: str) -> str:
    return RANGE_LABELS.get(str(value), str(value))


def _grams(value: float) -> str:
    """与前端 formatGrams 同口径：≥1 kg 用 kg 一位小数，否则整数克。"""
    grams = float(value)
    if grams >= GRAMS_PER_KG:
        return f"{grams / GRAMS_PER_KG:.1f} kg"
    return f"{round(grams)} 克"


def _money(value: float) -> str:
    return f"{float(value):.2f}"


def _build_context() -> dict:
    summary = stats.summary(REPORT_RANGE)
    top = stats.top_waste(3)

    query = " ".join(item["name"] for item in top) or "食材保存"
    tip_chunks: list[dict] = []
    try:
        for chunk in retrieve.search(query, limit=TIP_QUERY_LIMIT * 2):
            if str(chunk.get("source", "")).startswith("tip:"):
                tip_chunks.append(chunk)
    except Exception:
        logger.exception("周报检索技巧失败，忽略引用来源")

    citations = [{"source": f"stats:{REPORT_RANGE}", "locator": "区间汇总"}]
    citations += citation_utils.collect(tip_chunks, TIP_QUERY_LIMIT)

    citation_lines = "\n".join(
        f"[{i}] {citation_utils.label(item)}" for i, item in enumerate(citations, start=1)
    )
    top_lines = (
        "\n".join(f"- {item['name']}：{_grams(item['grams'])}" for item in top) or "- 本周没有丢弃记录"
    )
    user = (
        f"统计区间 {_range_label(summary['range'])}：浪费率 {_pct(summary['waste_rate'])}，"
        f"丢掉 {_grams(summary['thrown_grams'])}，吃掉 {_grams(summary['saved_grams'])}，"
        f"少排 {summary['carbon_saved_kg']} kg 碳，约等于少开 "
        f"{summary['equivalents']['car_km']} 公里车。\n"
        f"丢弃最多的食材：\n{top_lines}\n\n引用清单：\n{citation_lines}\n\n"
        "请写 150~250 字的周报，先肯定成绩，再给 1~2 条具体建议，末尾加一句免责声明。"
    )
    return {
        "summary": summary,
        "top": top,
        "citations": citations,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
    }


def _template_text(context: dict) -> str:
    summary = context["summary"]
    equivalents = summary["equivalents"]
    top = context["top"]
    lines = [
        f"{_range_label(summary['range'])}的冰箱成绩单：浪费率 {_pct(summary['waste_rate'])}，"
        f"吃掉 {_grams(summary['saved_grams'])}，扔掉 {_grams(summary['thrown_grams'])}。",
        f"少排碳 {summary['carbon_saved_kg']} kg，约等于少开 {equivalents['car_km']} 公里车，"
        f"或 {equivalents['trees_days']} 棵树一天的吸收量。",
        f"省下约 {_money(summary['money_saved'])} 元。",
    ]
    if top:
        lines.append(
            "最容易被忘掉的是"
            + "、".join(item["name"] for item in top[:2])
            + "，下次买回来就先切好分装，放到视线高度的那层。"
        )
    else:
        lines.append("本周没有丢弃记录，保持这个节奏就行。")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def _template_deltas(context: dict) -> list[str]:
    text = _template_text(context)
    return [
        text[i : i + TEMPLATE_CHUNK_SIZE] for i in range(0, len(text), TEMPLATE_CHUNK_SIZE)
    ]


async def _iter_stream(provider, messages: list[dict]) -> AsyncIterator[str]:
    """兼容 stream_chat 返回异步迭代器或协程两种写法。"""
    stream = provider.stream_chat(messages)
    if inspect.isawaitable(stream):
        stream = await stream
    if hasattr(stream, "__aiter__"):
        async for chunk in stream:
            yield chunk
        return
    for chunk in stream:  # 同步迭代器兜底
        yield chunk


async def stream_weekly(provider=None) -> AsyncIterator[dict]:
    """产出 SSE 事件 dict：delta / citations / done。"""
    context = _build_context()
    llm = resolve_provider(provider)

    if llm is None or getattr(llm, "name", "") == MOCK_PROVIDER_NAME:
        # mock 的固定文案会和统计页数字对不上：周报统一用当前 context 的模板文本
        logger.info("无可用模型或 mock 提供方，周报走模板文本")
        for piece in _template_deltas(context):
            yield {"type": "delta", "text": piece}
    else:
        produced = False
        try:
            async for delta in _iter_stream(llm, context["messages"]):
                if not delta:
                    continue
                produced = True
                yield {"type": "delta", "text": delta}
        except Exception as exc:
            logger.warning("周报流式生成失败：%s", exc)
            prefix = "\n\n（生成中断，以下为规则版摘要）\n" if produced else ""
            for piece in _template_deltas(context):
                yield {"type": "delta", "text": prefix + piece}
                prefix = ""
        if not produced:
            for piece in _template_deltas(context):
                yield {"type": "delta", "text": piece}

    yield {"type": "citations", "items": context["citations"]}
    yield {"type": "done"}


def event_stream_line(event: dict) -> str:
    """SSE 单帧编码（api 层与测试共用）。"""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
