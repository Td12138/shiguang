"""周报流式文本（契约 §6.6）：mock 不得编一套与统计页对不上的死数字。"""

from __future__ import annotations

import asyncio

import pytest

from app.core.mock import MockProvider
from app.domain import report as report_domain

# 故意与旧 mock 文案的 3.4 / 0.8 / 19% / 5.2 / 35 全部错开
CONTEXT = {
    "summary": {
        "range": "30d",
        "waste_rate": 0.163,
        "thrown_grams": 8470,
        "saved_grams": 1650,
        "carbon_saved_kg": 48.05,
        "money_saved": 99.5,
        "equivalents": {"car_km": 351, "trees_days": 1234},
    },
    "top": [{"name": "番茄", "grams": 500}],
    "citations": [],
    "messages": [],
}

HARDCODED = ("3.4", "0.8", "19%", "5.2", "35 公里")


def _collect(provider=None) -> list[dict]:
    async def _run():
        return [event async for event in report_domain.stream_weekly(provider)]

    return asyncio.run(_run())


@pytest.fixture()
def fixed_context(monkeypatch):
    monkeypatch.setattr(report_domain, "_build_context", lambda: CONTEXT)
    return CONTEXT


def test_mock_report_uses_current_context_numbers(fixed_context):
    """mock 提供方走模板文本，所有数字来自当前 context。"""
    events = _collect(MockProvider())
    text = "".join(event["text"] for event in events if event["type"] == "delta")

    assert text == report_domain._template_text(CONTEXT)
    for expected in ("16%", "1650", "8470", "48.05", "351", "99.5"):
        assert expected in text
    for stale in HARDCODED:
        assert stale not in text


def test_no_provider_report_also_matches_context(fixed_context, monkeypatch):
    """无模型降级路径与 mock 路径同一份模板，数字口径一致。"""
    monkeypatch.setattr(report_domain, "resolve_provider", lambda provider=None: None)
    text = "".join(
        event["text"] for event in _collect(None) if event["type"] == "delta"
    )
    assert text == report_domain._template_text(CONTEXT)
    for stale in HARDCODED:
        assert stale not in text
