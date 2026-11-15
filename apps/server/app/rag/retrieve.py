"""混合检索：BM25 + 可选向量召回，RRF 融合（契约 §8）。

- 关键词：SQLite FTS5 `bm25()`，对 title/tokens/body 三列加权
- 向量：`SHIGUANG_EMBEDDING_PROVIDER=api|local` 时调 OpenAI 兼容 `/embeddings`
  （local 默认 `http://127.0.0.1:8848/v1`），向量缓存在 `chunk_vectors`
- 融合：Reciprocal Rank Fusion，k=60

返回的每个 chunk 都带 `source` / `locator` / `score`，API 可原样透传。
"""

from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
import urllib.error
import urllib.request

from app.rag.tokenize import fts_query

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 5
CANDIDATE_MULTIPLIER = 3
RRF_K = 60
BM25_WEIGHT_TITLE = 10.0
BM25_WEIGHT_TOKENS = 8.0
BM25_WEIGHT_BODY = 1.0
MIN_RELEVANCE = 0.0

EMBEDDING_PROVIDER_ENV = "SHIGUANG_EMBEDDING_PROVIDER"
EMBEDDING_BASE_ENV = "SHIGUANG_EMBEDDING_BASE_URL"
EMBEDDING_MODEL_ENV = "SHIGUANG_EMBEDDING_MODEL"
EMBEDDING_KEY_ENV = "SHIGUANG_EMBEDDING_API_KEY"
LLM_BASE_ENV = "SHIGUANG_LLM_BASE_URL"
LLM_KEY_ENV = "SHIGUANG_LLM_API_KEY"

LOCAL_EMBEDDING_BASE = "http://127.0.0.1:8848/v1"
LOCAL_EMBEDDING_MODEL = "bge-m3"
API_EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_TIMEOUT_SECONDS = 30
EMBEDDING_BATCH_SIZE = 16
EMBEDDING_TEXT_LIMIT = 800
VECTOR_ENABLED_VALUES = {"api", "local"}


def embedding_config() -> dict | None:
    """读取向量召回配置；未开启返回 None。"""
    provider = (os.getenv(EMBEDDING_PROVIDER_ENV) or "none").strip().lower()
    if provider not in VECTOR_ENABLED_VALUES:
        return None

    if provider == "local":
        default_base = LOCAL_EMBEDDING_BASE
        default_model = LOCAL_EMBEDDING_MODEL
    else:
        default_base = (os.getenv(LLM_BASE_ENV) or "").strip()
        default_model = API_EMBEDDING_MODEL

    base = (os.getenv(EMBEDDING_BASE_ENV) or default_base).rstrip("/")
    if not base:
        logger.warning("向量召回已开启但缺少 base url，回退为纯 BM25")
        return None

    return {
        "provider": provider,
        "base": base,
        "model": (os.getenv(EMBEDDING_MODEL_ENV) or default_model).strip(),
        "api_key": (os.getenv(EMBEDDING_KEY_ENV) or os.getenv(LLM_KEY_ENV) or "").strip(),
    }


def _post_json(url: str, payload: dict, api_key: str, timeout: int) -> dict:
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def embed_texts(texts: list[str], config: dict) -> list[list[float]]:
    """调用 /embeddings；失败返回空列表（调用方回退 BM25）。"""
    if not texts:
        return []
    try:
        data = _post_json(
            f"{config['base']}/embeddings",
            {"model": config["model"], "input": texts},
            config.get("api_key", ""),
            EMBEDDING_TIMEOUT_SECONDS,
        )
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        logger.warning("向量服务不可用，本次回退纯 BM25：%s", exc)
        return []

    rows = data.get("data") or []
    vectors: list[list[float]] = []
    for row in rows:
        vector = row.get("embedding") if isinstance(row, dict) else None
        if isinstance(vector, list) and vector:
            vectors.append([float(x) for x in vector])
    if len(vectors) != len(texts):
        logger.warning("向量条数与请求不符（%d/%d），忽略", len(vectors), len(texts))
        return []
    return vectors


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _row_to_chunk(row: sqlite3.Row) -> dict:
    return {
        "chunk_id": row["id"],
        "source": row["source"],
        "locator": row["locator"],
        "title": row["title"],
        "body": row["body"],
    }


def bm25_search(
    conn: sqlite3.Connection, query: str, limit: int = DEFAULT_LIMIT
) -> list[dict]:
    """FTS5 BM25 召回，按相关性降序。"""
    match_expr = fts_query(query)
    if not match_expr:
        return []

    sql = (
        "SELECT c.id, c.source, c.locator, c.title, c.body,"
        f" bm25(chunks_fts, {BM25_WEIGHT_TITLE}, {BM25_WEIGHT_TOKENS}, {BM25_WEIGHT_BODY}) AS bm25"
        " FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid"
        " WHERE chunks_fts MATCH ?"
        " ORDER BY bm25 LIMIT ?"
    )
    try:
        rows = conn.execute(sql, (match_expr, limit)).fetchall()
    except sqlite3.OperationalError as exc:
        logger.warning("FTS 查询失败（%s），回退 LIKE", exc)
        return _like_search(conn, query, limit)

    results = []
    for row in rows:
        chunk = _row_to_chunk(row)
        chunk["score"] = abs(float(row["bm25"]))
        results.append(chunk)
    return results


def _like_search(conn: sqlite3.Connection, query: str, limit: int) -> list[dict]:
    terms = [term for term in str(query).split() if term][:5] or [str(query)]
    conditions = " OR ".join(["title LIKE ?"] * len(terms) + ["body LIKE ?"] * len(terms))
    params = [f"%{term}%" for term in terms] * 2
    sql = f"SELECT id, source, locator, title, body FROM chunks WHERE {conditions} LIMIT ?"
    rows = conn.execute(sql, (*params, limit)).fetchall()
    return [_row_to_chunk(row) | {"score": len(rows) - i} for i, row in enumerate(rows)]


def _ensure_vectors(conn: sqlite3.Connection, config: dict) -> list[sqlite3.Row]:
    """保证当前模型的向量齐全（缺失才补），返回该模型的全部向量行。"""
    model = config["model"]
    existing = conn.execute(
        "SELECT chunk_id, vec FROM chunk_vectors WHERE model = ?", (model,)
    ).fetchall()
    indexed = {row["chunk_id"] for row in existing}

    missing = conn.execute(
        "SELECT id, title, body FROM chunks ORDER BY id"
    ).fetchall()
    todo = [row for row in missing if row["id"] not in indexed]
    for start in range(0, len(todo), EMBEDDING_BATCH_SIZE):
        batch = todo[start : start + EMBEDDING_BATCH_SIZE]
        texts = [f"{row['title']} {row['body']}"[:EMBEDDING_TEXT_LIMIT] for row in batch]
        vectors = embed_texts(texts, config)
        if not vectors:
            break
        conn.executemany(
            "INSERT OR REPLACE INTO chunk_vectors(chunk_id,model,dim,vec,created_at)"
            " VALUES(?,?,?,?,datetime('now'))",
            [
                (row["id"], model, len(vector), json.dumps(vector))
                for row, vector in zip(batch, vectors)
            ],
        )
        conn.commit()

    return conn.execute(
        "SELECT chunk_id, vec FROM chunk_vectors WHERE model = ?", (model,)
    ).fetchall()


def vector_search(
    conn: sqlite3.Connection, query: str, limit: int = DEFAULT_LIMIT, config: dict | None = None
) -> list[dict]:
    config = config or embedding_config()
    if not config:
        return []

    rows = _ensure_vectors(conn, config)
    if not rows:
        return []

    query_vectors = embed_texts([query], config)
    if not query_vectors:
        return []
    query_vector = query_vectors[0]

    scored: list[tuple[float, int]] = []
    for row in rows:
        try:
            vector = json.loads(row["vec"])
        except (json.JSONDecodeError, TypeError):
            continue
        scored.append((_cosine(query_vector, vector), row["chunk_id"]))
    scored.sort(reverse=True)

    results: list[dict] = []
    for score, chunk_id in scored[:limit]:
        if score <= MIN_RELEVANCE:
            continue
        row = conn.execute(
            "SELECT id, source, locator, title, body FROM chunks WHERE id = ?", (chunk_id,)
        ).fetchone()
        if not row:
            continue
        results.append(_row_to_chunk(row) | {"score": round(score, 6)})
    return results


def rrf_fuse(result_lists: list[list[dict]], limit: int = DEFAULT_LIMIT) -> list[dict]:
    """Reciprocal Rank Fusion，返回带 score / rel 的融合结果。"""
    fused: dict[tuple[str, str], dict] = {}
    contributions: dict[tuple[str, str], dict] = {}

    for channel, results in zip(("bm25", "vector"), result_lists):
        for rank, item in enumerate(results, start=1):
            key = (item["source"], item["locator"])
            fused.setdefault(key, dict(item))
            contributions.setdefault(key, {})[channel] = rank
            fused[key]["score"] = fused[key].get("score", 0.0) + 1.0 / (RRF_K + rank)

    ordered = sorted(fused.values(), key=lambda item: item["score"], reverse=True)[:limit]
    if not ordered:
        return []

    high = max(item["score"] for item in ordered)
    low = min(item["score"] for item in ordered)
    span = high - low
    for item in ordered:
        key = (item["source"], item["locator"])
        item["rel"] = 1.0 if span <= 0 else round((item["score"] - low) / span, 4)
        item["score"] = round(item["score"], 6)
        item["matched_by"] = sorted(contributions.get(key, {}))
    return ordered


def search(
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    conn: sqlite3.Connection | None = None,
    use_vector: bool | None = None,
) -> list[dict]:
    """混合检索入口。检索为空返回 []（由调用方给出「没有匹配」的空态）。"""
    own_conn = conn is None
    if own_conn:
        from app.db.conn import get_conn

        conn = get_conn()

    try:
        config = embedding_config() if use_vector is not False else None
        candidate_limit = max(limit * CANDIDATE_MULTIPLIER, limit)
        keyword_hits = bm25_search(conn, query, candidate_limit)
        vector_hits = vector_search(conn, query, candidate_limit, config) if config else []
        if not keyword_hits and not vector_hits:
            logger.info("检索无命中：%s", query)
            return []
        return rrf_fuse([keyword_hits, vector_hits], limit)
    finally:
        if own_conn:
            conn.close()
