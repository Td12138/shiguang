"""RAG：BM25 检索、chunk 引用、RRF 融合。"""

from __future__ import annotations

import pytest

from app.rag import citations, retrieve


def test_bm25_hits_recipe_chunk(app_db, add_recipe):
    add_recipe(
        "r_1",
        "蒜蓉西兰花",
        ingredients=[{"name": "西兰花", "qty": 1, "unit": "颗", "optional": False}],
        steps=["切小朵", "蒜切末", "爆香", "翻炒"],
        minutes=15,
    )
    add_recipe(
        "r_2",
        "番茄鸡蛋面",
        ingredients=[{"name": "番茄"}, {"name": "鸡蛋"}],
        steps=["切番茄", "打蛋", "煮面"],
        minutes=20,
    )

    hits = retrieve.search("西兰花", limit=3)
    assert hits, "FTS 应该命中菜谱"
    top = hits[0]
    assert top["source"] == "recipe:r_1"
    assert top["locator"] == "步骤 1-4"
    assert top["score"] > 0
    assert 0 <= top["rel"] <= 1


def test_tip_chunks_indexed(app_db, tmp_path, monkeypatch, add_recipe):
    tips = tmp_path / "tips.md"
    tips.write_text(
        "# 保存技巧\n\n## 西兰花怎么存\n\n冷藏别洗，套袋扎孔，5 天内吃完。\n\n"
        "## 绿叶菜救急\n\n发蔫了先泡冰水十分钟再炒。\n",
        encoding="utf-8",
    )
    from app.db import seed

    monkeypatch.setattr(seed, "TIPS_FILE", tips)
    add_recipe("r_1", "蒜蓉西兰花")

    hits = retrieve.search("绿叶菜 救急", limit=5)
    sources = [hit["source"] for hit in hits]
    assert any(source.startswith("tip:") for source in sources), sources

    tip_hits = [hit for hit in hits if hit["source"].startswith("tip:")]
    for hit in tip_hits:
        assert hit["locator"].startswith("段落 ")


def test_search_without_hits_returns_empty(app_db):
    assert retrieve.search("完全不存在的食材组合", limit=3) == []
    assert retrieve.search("", limit=3) == []


def test_citation_helpers():
    chunks = [
        {"source": "recipe:r_1", "locator": "步骤 1-3"},
        {"source": "recipe:r_1", "locator": "步骤 1-3"},
        {"source": "tip:2", "locator": "段落 2"},
        {"source": "", "locator": "空来源应被丢弃"},
    ]
    items = citations.collect(chunks)
    assert items == [
        {"source": "recipe:r_1", "locator": "步骤 1-3"},
        {"source": "tip:2", "locator": "段落 2"},
    ]
    assert citations.collect(chunks, 1) == [{"source": "recipe:r_1", "locator": "步骤 1-3"}]
    assert citations.label(items[0]) == "recipe:r_1 · 步骤 1-3"
    assert citations.render(chunks, 2).count("\n") == 1


def test_citation_includes_text_excerpt():
    """引用要带原文摘录（≤120 字），前端角标直接弹原文。"""
    body = "食材：西兰花。步骤：" + "洗菜切小朵" * 60
    chunk = {"source": "recipe:r_1", "locator": "步骤 1-4", "body": body}

    citation = citations.from_chunk(chunk)
    assert citation["source"] == "recipe:r_1"
    assert citation["locator"] == "步骤 1-4"
    assert citation["text"].endswith(citations.ELLIPSIS)
    assert len(citation["text"]) == citations.SNIPPET_CHARS + 1

    short = citations.make("tip:1", "段落 1", "冷藏别洗")
    assert short["text"] == "冷藏别洗"
    # 无原文来源（如 stats:30d）不带 text 字段，避免前端弹空框
    assert "text" not in citations.make("stats:30d", "区间汇总")


def test_rrf_fusion_prefers_both_channels():
    keyword = [{"source": "recipe:1", "locator": "a", "title": "A"}]
    vector = [
        {"source": "recipe:1", "locator": "a", "title": "A"},
        {"source": "recipe:2", "locator": "b", "title": "B"},
    ]
    fused = retrieve.rrf_fuse([keyword, vector], 5)

    assert fused[0]["source"] == "recipe:1"
    assert fused[0]["score"] == pytest.approx(1 / 61 + 1 / 61, abs=1e-5)
    assert fused[0]["rel"] == 1.0
    assert fused[1]["rel"] == 0.0
    assert fused[0]["matched_by"] == ["bm25", "vector"]
