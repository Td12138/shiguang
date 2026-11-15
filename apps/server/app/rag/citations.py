"""引用（citation）构造与去重（契约 §8：每个 chunk 带 source + locator + text）。

`text` 是原文摘录（截断 `SNIPPET_CHARS` 字），前端点角标直接弹这段原文，
不用再单独查一次接口。没有原文时（例如 `stats:30d` 这类合成来源）不带该字段。
"""

from __future__ import annotations

SNIPPET_CHARS = 120
ELLIPSIS = "…"


def excerpt(text: object, limit: int = SNIPPET_CHARS) -> str:
    """把原文压成一句话摘录：去多余空白 + 截断。"""
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[:limit] + ELLIPSIS


def make(source: str, locator: str, text: object | None = None) -> dict:
    """构造一条引用：`{"source": "recipe:r_012", "locator": "步骤 1-3", "text": "…"}`。"""
    citation: dict = {"source": str(source), "locator": str(locator)}
    snippet = excerpt(text)
    if snippet:
        citation["text"] = snippet
    return citation


def from_chunk(chunk: dict) -> dict:
    return make(chunk.get("source", ""), chunk.get("locator", ""), chunk.get("body"))


def collect(chunks: list[dict], limit: int | None = None) -> list[dict]:
    """按 (source, locator) 去重，保持原顺序。"""
    seen: set[tuple[str, str]] = set()
    items: list[dict] = []
    for chunk in chunks:
        citation = from_chunk(chunk)
        if not citation["source"]:
            continue
        key = (citation["source"], citation["locator"])
        if key in seen:
            continue
        seen.add(key)
        items.append(citation)
        if limit is not None and len(items) >= limit:
            break
    return items


def label(citation: dict) -> str:
    """人类可读的引用标签，用于周报/前端角标。"""
    return f"{citation.get('source', '')} · {citation.get('locator', '')}"


def render(chunks: list[dict], limit: int | None = 3) -> str:
    """给 LLM Prompt 用的引用清单文本（编号从 1 开始）。"""
    items = collect(chunks, limit)
    return "\n".join(f"[{i}] {label(item)}" for i, item in enumerate(items, start=1))
