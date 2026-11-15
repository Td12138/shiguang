"""菜谱 Agent 流水线：五步 trace、引用非空、校验重试、无模型降级（契约 §9）。"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.domain import inventory as inv
from app.domain import recipes
from app.db.conn import get_conn

STAGES = ["understand", "plan", "retrieve", "compose", "verify"]


def _run(coro):
    return asyncio.run(coro)


def _seed(app_db, add_item, add_recipe):
    add_item("西兰花", avg_grams=300.0, shelf_life_days=5)
    add_item("鸡蛋", avg_grams=60.0, unit="个", shelf_life_days=10)
    add_recipe(
        "r_broccoli",
        "蒜蓉西兰花",
        ingredients=[
            {"name": "西兰花", "qty": 1, "unit": "颗", "optional": False},
            {"name": "大蒜", "qty": 2, "unit": "瓣", "optional": False},
        ],
        steps=["切小朵", "蒜切末", "爆香", "翻炒调味"],
        minutes=15,
    )
    add_recipe(
        "r_egg",
        "西兰花炒鸡蛋",
        ingredients=[{"name": "西兰花"}, {"name": "鸡蛋"}],
        steps=["焯水", "打蛋", "同炒"],
        minutes=10,
    )
    inv_id = inv.add_items({"items": [{"name": "西兰花", "qty": 1}]})["ids"][0]
    return inv_id


def _compose_ok():
    return {
        "recommendations": [
            {
                "recipe_id": "r_broccoli",
                "reason": "用掉你 5 天后到期的西兰花，15 分钟搞定",
                "citations": [{"source": "recipe:r_broccoli", "locator": "步骤 1-4"}],
            }
        ]
    }


def test_pipeline_with_fake_provider(app_db, add_item, add_recipe, fake_provider):
    _seed(app_db, add_item, add_recipe)
    provider = fake_provider(compose=_compose_ok())

    result = _run(recipes.suggest(max_minutes=30, limit=2, provider=provider))

    assert result["run_id"].startswith("run_")
    assert result["warnings"] == []
    assert len(result["recommendations"]) == 1

    rec = result["recommendations"][0]
    assert rec["recipe_id"] == "r_broccoli"
    assert rec["title"] == "蒜蓉西兰花"
    assert rec["minutes"] == 15
    assert rec["reason"]
    citation = rec["citations"][0]
    assert citation["source"] == "recipe:r_broccoli"
    assert citation["locator"] == "步骤 1-4"
    assert "西兰花" in citation["text"], "引用要带原文摘录（前端角标弹原文）"
    assert len(citation["text"]) <= 121
    # uses 供前端直接扣库存
    assert len(rec["uses"]) == 1
    use = rec["uses"][0]
    assert use["name"] == "西兰花"
    assert use["qty"] == 1
    assert use["unit"] == "颗"
    assert use["inventory_id"].startswith("inv_")
    assert 0 <= rec["score"] <= 1
    assert [item["name"] for item in rec["missing"]] == ["大蒜"]

    run = recipes.get_run(result["run_id"])
    assert run["state"] == "ok"
    assert [step["name"] for step in run["steps"]] == STAGES
    for step in run["steps"]:
        assert step["status"] in {"ok", "degraded"}
        assert isinstance(step["ms"], int)
        assert step["summary"]
        assert step["started_at"]

    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT state, steps FROM agent_runs WHERE id = ?", (result["run_id"],)
        ).fetchone()
    finally:
        conn.close()
    assert row["state"] == "ok"
    assert len(json.loads(row["steps"])) == 5


def test_pipeline_degrades_when_llm_fails(app_db, add_item, add_recipe, fake_provider):
    _seed(app_db, add_item, add_recipe)
    provider = fake_provider(fail_compose=True)

    result = _run(recipes.suggest(max_minutes=30, limit=2, provider=provider))

    assert any("已降级" in warning for warning in result["warnings"])
    assert result["recommendations"], "降级也要给出规则版结果"
    assert result["recommendations"][0]["citations"], "规则版也必须带引用"
    assert result["recommendations"][0]["reason"]
    assert recipes.get_run(result["run_id"])["state"] == "degraded"


def test_pipeline_without_any_provider(app_db, add_item, add_recipe, no_llm):
    _seed(app_db, add_item, add_recipe)

    result = _run(recipes.suggest(max_minutes=30, limit=2, provider=None))

    assert result["recommendations"]
    assert any("已降级" in warning for warning in result["warnings"])
    assert all(rec["citations"] for rec in result["recommendations"])


def test_verify_retries_with_hint_then_passes(app_db, add_item, add_recipe, fake_provider):
    _seed(app_db, add_item, add_recipe)
    invalid = {"recommendations": [{"recipe_id": "r_not_exist", "reason": "编的", "citations": []}]}
    provider = fake_provider(compose=[invalid, _compose_ok()])

    result = _run(recipes.suggest(max_minutes=30, limit=2, provider=provider))

    assert result["recommendations"][0]["recipe_id"] == "r_broccoli"
    compose_calls = [stage for stage in provider.calls if stage == "compose"]
    assert len(compose_calls) >= 2, "校验失败应重试一次 compose"


def test_verify_drops_entry_with_too_few_steps(app_db, add_item, add_recipe, fake_provider):
    add_item("鸡蛋", avg_grams=60.0)
    add_recipe(
        "r_short",
        "白煮蛋",
        ingredients=[{"name": "鸡蛋"}],
        steps=["煮", "剥"],  # 只有 2 步，应被 verify 剔除
        minutes=8,
    )
    inv.add_items({"items": [{"name": "鸡蛋", "qty": 3}]})

    payload = {
        "recommendations": [
            {"recipe_id": "r_short", "reason": "快速", "citations": [{"source": "recipe:r_short", "locator": "步骤 1-2"}]}
        ]
    }
    provider = fake_provider(compose=payload)
    result = _run(recipes.suggest(max_minutes=30, limit=2, provider=provider))

    kept_ids = [rec["recipe_id"] for rec in result["recommendations"]]
    assert "r_short" not in kept_ids


def test_empty_inventory_and_no_recipes(app_db, no_llm):
    result = _run(recipes.suggest(max_minutes=30, limit=2, provider=None))

    assert result["recommendations"] == []
    assert any("库存里没有匹配菜谱" in warning for warning in result["warnings"])
    run = recipes.get_run(result["run_id"])
    assert [step["name"] for step in run["steps"]] == STAGES
    assert run["steps"][2]["status"] == "empty"


def test_get_run_missing(app_db):
    from app.domain.tools_registry import AppError

    with pytest.raises(AppError) as excinfo:
        recipes.get_run("run_missing")
    assert excinfo.value.status == 404
