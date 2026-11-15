"""RAG 索引构建（契约 §8 / §6.10）。

chunk 来源：
- 菜谱：`source=recipe:<id>`，body = 食材 + 步骤，locator = `步骤 1-N`
- 保存技巧：`source=tip:<n>`（按 tips.md 的 `##` 段落顺序），locator = `段落 n`
- 用户偏好：`source=pref:<id>`，body = 偏好原文，locator = `偏好原文`

写入 `chunks`（可回查原文）与 `chunks_fts`（FTS5 unicode61 + tokens 列存 2-gram）。
偏好增删时用 `sync_preference` / `remove_preference` 做增量维护，不必整库重建。
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
PREF_SOURCE_PREFIX = "pref:"
PREF_LOCATOR = "偏好原文"
PREF_TITLE_TEMPLATE = "用户偏好（{label}）"
PREF_KIND_LABELS: dict[str, str] = {
    "avoid": "忌口",
    "like": "喜欢",
    "time": "时间",
    "portion": "分量",
    "health": "健康",
}
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


def _preference_chunk(row: sqlite3.Row) -> dict:
    kind = str(row["kind"] or "")
    return {
        "source": f"{PREF_SOURCE_PREFIX}{row['id']}",
        "locator": PREF_LOCATOR,
        "title": PREF_TITLE_TEMPLATE.format(label=PREF_KIND_LABELS.get(kind, kind or "其它")),
        "body": str(row["text"] or "").strip()[:MAX_BODY_CHARS],
    }


def recipe_chunk(row: sqlite3.Row) -> dict:
    """菜谱 chunk 构造的公开入口（domain 层复用，保证引用原文与索引一致）。"""
    return _recipe_chunk(row)


def _preference_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    try:
        return conn.execute(
            "SELECT id, text, kind FROM preferences ORDER BY created_at, id"
        ).fetchall()
    except sqlite3.OperationalError:  # 老库还没建 preferences 表
        return []


def collect_chunks(conn: sqlite3.Connection) -> list[dict]:
    """从 recipes 表 + tips.md + preferences 表收集全部 chunk（不写库）。"""
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

    for row in _preference_rows(conn):
        chunk = _preference_chunk(row)
        if chunk["body"]:
            chunks.append(chunk)
    return chunks


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))


def _insert_chunk(conn: sqlite3.Connection, chunk: dict, now: str) -> int:
    tokens = tokenized_text(f"{chunk['title']} {chunk['body']}")
    cursor = conn.execute(
        "INSERT INTO chunks(source,locator,title,body,tokens,created_at) VALUES(?,?,?,?,?,?)",
        (chunk["source"], chunk["locator"], chunk["title"], chunk["body"], tokens, now),
    )
    chunk_id = int(cursor.lastrowid or 0)
    conn.execute(
        "INSERT INTO chunks_fts(rowid,title,tokens,body,source,locator) VALUES(?,?,?,?,?,?)",
        (chunk_id, chunk["title"], tokens, chunk["body"], chunk["source"], chunk["locator"]),
    )
    return chunk_id


def _delete_source(conn: sqlite3.Connection, source: str) -> int:
    rows = conn.execute("SELECT id FROM chunks WHERE source = ?", (source,)).fetchall()
    for row in rows:
        conn.execute("DELETE FROM chunks_fts WHERE rowid = ?", (row["id"],))
        conn.execute("DELETE FROM chunk_vectors WHERE chunk_id = ?", (row["id"],))
    conn.execute("DELETE FROM chunks WHERE source = ?", (source,))
    return len(rows)


def rebuild_index(conn: sqlite3.Connection | None = None) -> int:
    """重建全文索引；返回写入的 chunk 数（含偏好）。"""
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
            _insert_chunk(conn, chunk, now)
        conn.commit()
        logger.info("RAG 索引重建完成：%d 个 chunk", len(chunks))
        return len(chunks)
    finally:
        if own_conn:
            conn.close()


def sync_preference(pref_id: str, conn: sqlite3.Connection | None = None) -> bool:
    """把一条偏好写入/刷新 FTS 索引（`source=pref:<id>`），返回是否写成功。"""
    own_conn = conn is None
    if own_conn:
        from app.db.conn import get_conn

        conn = get_conn()
    try:
        _ensure_tables(conn)
        row = conn.execute(
            "SELECT id, text, kind FROM preferences WHERE id = ?", (pref_id,)
        ).fetchone()
        if row is None:
            _delete_source(conn, f"{PREF_SOURCE_PREFIX}{pref_id}")
            conn.commit()
            return False
        chunk = _preference_chunk(row)
        _delete_source(conn, chunk["source"])
        if chunk["body"]:
            _insert_chunk(conn, chunk, _now_iso())
        conn.commit()
        return bool(chunk["body"])
    finally:
        if own_conn:
            conn.close()


def remove_preference(pref_id: str, conn: sqlite3.Connection | None = None) -> int:
    """删除偏好对应的 FTS 索引，返回删除的 chunk 数。"""
    own_conn = conn is None
    if own_conn:
        from app.db.conn import get_conn

        conn = get_conn()
    try:
        _ensure_tables(conn)
        removed = _delete_source(conn, f"{PREF_SOURCE_PREFIX}{pref_id}")
        conn.commit()
        return removed
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
