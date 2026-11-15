"""种子数据（契约 §5 / §7.1）。

数据文件由数据代理维护（app/data/）：`items.json` / `recipes.json` / `tips.md`。
文件缺失时只打警告并跳过，绝不让服务起不来。

命令行：`python -m app.db.seed --force`
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.db.conn import SCHEMA_FILE, get_conn

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
ITEMS_FILE = DATA_DIR / "items.json"
RECIPES_FILE = DATA_DIR / "recipes.json"
TIPS_FILE = DATA_DIR / "tips.md"

ITEM_DEFAULTS: dict[str, Any] = {
    "category": "其他",
    "shelf_life_days": 5,
    "carbon_kg_per_kg": 1.0,
    "price_per_kg": 5.0,
    "avg_grams": 200.0,
    "storage_tip": "",
    "unit": "份",
}
RECIPE_DEFAULTS: dict[str, Any] = {
    "minutes": 20,
    "servings": 1,
    "difficulty": "简单",
    "tags": "",
}


def _stable_id(prefix: str, name: str) -> str:
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}{digest}"


def _read_json(path: Path) -> Any:
    if not path.exists():
        logger.warning("种子文件缺失，跳过：%s", path)
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        logger.warning("种子文件不是合法 JSON，跳过：%s（%s）", path, exc)
        return None


def _as_list(data: Any, key: str) -> list[dict]:
    if data is None:
        return []
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        for candidate in (key, "items", "data", "recipes", "list"):
            value = data.get(candidate)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    logger.warning("种子数据结构无法识别，已忽略")
    return []


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def normalize_item(raw: dict, index: int) -> dict:
    name = str(raw.get("name") or raw.get("食材") or "").strip()
    if not name:
        name = f"未知食材{index}"
    item_id = str(raw.get("id") or raw.get("item_id") or "").strip() or _stable_id("i_", name)
    return {
        "id": item_id,
        "name": name,
        "category": str(raw.get("category") or ITEM_DEFAULTS["category"]),
        "shelf_life_days": _as_int(raw.get("shelf_life_days"), ITEM_DEFAULTS["shelf_life_days"]),
        "carbon_kg_per_kg": _as_float(
            raw.get("carbon_kg_per_kg"), ITEM_DEFAULTS["carbon_kg_per_kg"]
        ),
        "price_per_kg": _as_float(raw.get("price_per_kg"), ITEM_DEFAULTS["price_per_kg"]),
        "avg_grams": _as_float(raw.get("avg_grams"), ITEM_DEFAULTS["avg_grams"]),
        "storage_tip": str(raw.get("storage_tip") or ""),
        "unit": str(raw.get("unit") or ITEM_DEFAULTS["unit"]),
    }


def _normalize_ingredient(raw: Any) -> dict:
    if isinstance(raw, str):
        return {"name": raw.strip(), "qty": 1, "unit": "", "optional": False}
    if isinstance(raw, dict):
        return {
            "name": str(raw.get("name") or "").strip(),
            "qty": _as_float(raw.get("qty"), 1.0),
            "unit": str(raw.get("unit") or ""),
            "optional": bool(raw.get("optional", False)),
        }
    return {"name": str(raw).strip(), "qty": 1, "unit": "", "optional": False}


def _normalize_step(raw: Any) -> str:
    if isinstance(raw, dict):
        return str(raw.get("text") or raw.get("step") or raw.get("content") or "").strip()
    return str(raw).strip()


def normalize_recipe(raw: dict, index: int) -> dict:
    title = str(raw.get("title") or raw.get("name") or "").strip()
    if not title:
        title = f"未命名菜谱{index}"
    recipe_id = str(raw.get("id") or raw.get("recipe_id") or "").strip() or _stable_id("r_", title)
    ingredients = [_normalize_ingredient(x) for x in (raw.get("ingredients") or [])]
    ingredients = [x for x in ingredients if x["name"]]
    steps = [_normalize_step(x) for x in (raw.get("steps") or [])]
    steps = [x for x in steps if x]
    tags = raw.get("tags") or ""
    if isinstance(tags, list):
        tags = ",".join(str(t) for t in tags)
    return {
        "id": recipe_id,
        "title": title,
        "ingredients": json.dumps(ingredients, ensure_ascii=False),
        "steps": json.dumps(steps, ensure_ascii=False),
        "minutes": _as_int(raw.get("minutes"), RECIPE_DEFAULTS["minutes"]),
        "servings": _as_int(raw.get("servings"), RECIPE_DEFAULTS["servings"]),
        "tags": str(tags),
        "difficulty": str(raw.get("difficulty") or RECIPE_DEFAULTS["difficulty"]),
    }


def load_items() -> list[dict]:
    data = _read_json(ITEMS_FILE)
    return [normalize_item(raw, i) for i, raw in enumerate(_as_list(data, "items"), start=1)]


def load_recipes() -> list[dict]:
    data = _read_json(RECIPES_FILE)
    return [normalize_recipe(raw, i) for i, raw in enumerate(_as_list(data, "recipes"), start=1)]


def load_tips_sections() -> list[dict]:
    """把 tips.md 按 `## ` 标题切成段落，返回 [{title, body}]（顺序即编号）。"""
    if not TIPS_FILE.exists():
        logger.warning("种子文件缺失，跳过：%s", TIPS_FILE)
        return []

    sections: list[dict] = []
    current_title: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        if current_title is None:
            return
        body = "\n".join(line for line in buffer).strip()
        if body:
            sections.append({"title": current_title, "body": body})

    for line in TIPS_FILE.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            flush()
            current_title = stripped[3:].strip()
            buffer = []
        elif stripped.startswith("# ") and current_title is None:
            continue
        elif current_title is not None:
            buffer.append(line.rstrip())
    flush()
    return sections


def _insert_items(conn, items: list[dict]) -> int:
    sql = (
        "INSERT OR REPLACE INTO items(id,name,category,shelf_life_days,carbon_kg_per_kg,"
        "price_per_kg,avg_grams,storage_tip,unit) VALUES(?,?,?,?,?,?,?,?,?)"
    )
    conn.executemany(
        sql,
        [
            (
                row["id"],
                row["name"],
                row["category"],
                row["shelf_life_days"],
                row["carbon_kg_per_kg"],
                row["price_per_kg"],
                row["avg_grams"],
                row["storage_tip"],
                row["unit"],
            )
            for row in items
        ],
    )
    return len(items)


def _insert_recipes(conn, recipes: list[dict]) -> int:
    sql = (
        "INSERT OR REPLACE INTO recipes(id,title,ingredients,steps,minutes,servings,tags,difficulty)"
        " VALUES(?,?,?,?,?,?,?,?)"
    )
    conn.executemany(
        sql,
        [
            (
                row["id"],
                row["title"],
                row["ingredients"],
                row["steps"],
                row["minutes"],
                row["servings"],
                row["tags"],
                row["difficulty"],
            )
            for row in recipes
        ],
    )
    return len(recipes)


def _ensure_tables() -> None:
    """只建表，不触发种子（避免 init_db <-> seed_all 递归）。"""
    conn = get_conn()
    try:
        conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()


def seed_all(force: bool = False) -> dict:
    """灌种子 + 重建 RAG 索引。force=True 先清空参考数据（不动用户库存）。"""
    _ensure_tables()
    items = load_items()
    recipes = load_recipes()
    tips = load_tips_sections()

    conn = get_conn()
    try:
        if force:
            conn.execute("DELETE FROM recipes")
            conn.execute("DELETE FROM items")
        if items:
            _insert_items(conn, items)
        if recipes:
            _insert_recipes(conn, recipes)
        conn.commit()
    finally:
        conn.close()

    chunk_count = 0
    try:
        from app.rag.index import rebuild_index

        chunk_count = rebuild_index()
    except Exception:
        logger.exception("重建 RAG 索引失败（不影响种子数据）")

    summary = {
        "items": len(items),
        "recipes": len(recipes),
        "tips": len(tips),
        "chunks": chunk_count,
    }
    logger.info("种子完成：%s", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="灌入食光种子数据并重建 RAG 索引")
    parser.add_argument("--force", action="store_true", help="清空参考数据后重建")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    summary = seed_all(force=args.force)
    # CLI 场景用 stdout 给操作者看（库内代码只用 logging）
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
