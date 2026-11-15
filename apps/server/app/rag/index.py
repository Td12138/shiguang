"""RAG 索引构建（契约 §8）。

chunk 来源：
- 菜谱：`source=recipe:<id>`，body = 食材 + 步骤，locator = `步骤 1-N`
- 保存技巧：`source=tip:<n>`（按 tips.md 的 `##` 段落顺序），locator = `段落 n`

写入 `chunks`（可回查原文）与 `chunks_fts`（FTS5 unicode61 + tokens 列存 2-gram）。
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from app.rag.tokenize import tokenized_text

logger = logging.getLogger(__name__)

SCHEMA_FILE = Path(__file__).resolve().parents[1] / "db" / "schema.sql"
RECIPE_LOCATOR_PREFIX = "步骤 1-"
TIP_LOCATOR_PREFIX = "段落 "
MAX_BODY_CHARS = 2000


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _loads(value: str | None, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _recipe_chunk(row: sqlite3.Row) -> dict:
    ingredients = _loads(row["ingredients"], [])
    steps = _loads(row["steps"], [])
    names = [str(x.get("name") or "").strip() for x in ingredients if isinstance(x, dict)]
    names = [x for x in names if x]
    step_texts = [str(x).strip() for x in steps if str(x).strip()]
    body = "食材：" + "、".join(names) + "。" if names else ""
    if step_texts:
        body += "步骤：" + " ".join(f"{i}.{text}" for i, text in enumerate(step_texts, start=1))
    return {
        "source": f"recipe:{row['id']}",
        "locator": f"{RECIPE_LOCATOR_PREFIX}{max(len(step_texts), 1)}",
        "title": str(row["title"] or ""),
        "body": body.strip()[:MAX_BODY_CHARS],
    }


def _tip_chunk(index: int, section: dict) -> dict:
    return {
        "source": f"tip:{index}",
        "locator": f"{TIP_LOCATOR_PREFIX}{index}",
        "title": str(section.get("title") or f"技巧 {index}"),
        "body": str(section.get("body") or "").strip()[:MAX_BODY_CHARS],
    }


def collect_chunks(conn: sqlite3.Connection) -> list[dict]:
    """从 recipes 表 + tips.md 收集全部 chunk（不写库）。"""
    from app.db.seed import load_tips_sections  # 延迟导入避免循环

    chunks: list[dict] = []
    for row in conn.execute("SELECT * FROM recipes ORDER BY id").fetchall():
        chunk = _recipe_chunk(row)
        if chunk["body"]:
            chunks.append(chunk)

    for index, section in enumerate(load_tips_sections(), start=1):
        chunk = _tip_chunk(index, section)
        if chunk["body"]:
            chunks.append(chunk)
    return chunks


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))


def rebuild_index(conn: sqlite3.Connection | None = None) -> int:
    """重建全文索引；返回写入的 chunk 数。"""
    own_conn = conn is None
    if own_conn:
        from app.db.conn import get_conn

        conn = get_conn()

    try:
        _ensure_tables(conn)
        chunks = collect_chunks(conn)

        conn.execute("DELETE FROM chunks_fts")
        conn.execute("DELETE FROM chunks")
        conn.execute("DELETE FROM chunk_vectors")

        now = _now_iso()
        for chunk in chunks:
            tokens = tokenized_text(f"{chunk['title']} {chunk['body']}")
            cursor = conn.execute(
                "INSERT INTO chunks(source,locator,title,body,tokens,created_at)"
                " VALUES(?,?,?,?,?,?)",
                (chunk["source"], chunk["locator"], chunk["title"], chunk["body"], tokens, now),
            )
            chunk_id = cursor.lastrowid
            conn.execute(
                "INSERT INTO chunks_fts(rowid,title,tokens,body,source,locator)"
                " VALUES(?,?,?,?,?,?)",
                (
                    chunk_id,
                    chunk["title"],
                    tokens,
                    chunk["body"],
                    chunk["source"],
                    chunk["locator"],
                ),
            )
        conn.commit()
        logger.info("RAG 索引重建完成：%d 个 chunk", len(chunks))
        return len(chunks)
    finally:
        if own_conn:
            conn.close()


def index_size(conn: sqlite3.Connection | None = None) -> int:
    own_conn = conn is None
    if own_conn:
        from app.db.conn import get_conn

        conn = get_conn()
    try:
        return int(conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
    finally:
        if own_conn:
            conn.close()
