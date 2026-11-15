"""中文 2-gram 分词（契约 §8）。

FTS5 的 unicode61 不切中文，所以写入 `tokens` 列与查询时统一用本模块：
- 连续中文（CJK）按 2 字滑窗切分，单字成词时保留单字
- 英文/数字整段保留并转小写（`BGE-M3` -> `bge`, `m3`）
"""

from __future__ import annotations

import re

CJK = r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
TOKEN_PATTERN = re.compile(f"[{CJK}]+|[A-Za-z0-9]+")
CJK_PATTERN = re.compile(f"^[{CJK}]+$")
NGRAM_SIZE = 2
SEPARATOR = " "


def _cjk_grams(run: str) -> list[str]:
    if len(run) < NGRAM_SIZE:
        return [run]
    return [run[i : i + NGRAM_SIZE] for i in range(len(run) - NGRAM_SIZE + 1)]


def tokenize(text: str | None) -> list[str]:
    """返回 token 列表（小写英文/数字 + 中文 2-gram）。"""
    if not text:
        return []

    tokens: list[str] = []
    for match in TOKEN_PATTERN.finditer(str(text)):
        piece = match.group(0)
        if CJK_PATTERN.match(piece):
            tokens.extend(_cjk_grams(piece))
        else:
            tokens.append(piece.lower())
    return tokens


def tokenized_text(text: str | None) -> str:
    """写入 FTS `tokens` 列的形式：空格分隔。"""
    return SEPARATOR.join(tokenize(text))


def fts_query(text: str) -> str:
    """把用户查询转成 FTS5 MATCH 表达式（每个 token 加引号，OR 连接）。"""
    tokens = list(dict.fromkeys(tokenize(text)))
    if not tokens:
        return ""
    return " OR ".join(f'"{token}"' for token in tokens)
