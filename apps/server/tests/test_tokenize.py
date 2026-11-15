"""2-gram 分词（契约 §8）。"""

from __future__ import annotations

from app.rag.tokenize import fts_query, tokenize, tokenized_text


def test_cjk_bigrams():
    assert tokenize("西兰花炒鸡蛋") == ["西兰", "兰花", "花炒", "炒鸡", "鸡蛋"]


def test_single_cjk_char_kept():
    assert tokenize("蒜") == ["蒜"]


def test_english_and_number_kept_lowercase():
    tokens = tokenize("BGE-M3 模型 2026 年")
    assert "bge" in tokens
    assert "m3" in tokens
    assert "2026" in tokens
    assert "模型" in tokens


def test_empty_input():
    assert tokenize("") == []
    assert tokenize(None) == []
    assert tokenized_text(None) == ""


def test_tokenized_text_join_and_query():
    assert tokenized_text("西兰花") == "西兰 兰花"
    query = fts_query("西兰花")
    assert query == '"西兰" OR "兰花"'


def test_query_dedupes():
    assert fts_query("西兰花 西兰花") == '"西兰" OR "兰花"'
