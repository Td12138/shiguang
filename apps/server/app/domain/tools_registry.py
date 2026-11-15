"""业务域与 app/core 的唯一接缝：AppError 转发、Provider 解析、工具注册表。

`app/core/` 由另一代理并行开发，这里只 import 不修改：
- `app.core.errors.AppError` 缺失时用本地等价类兜底（保证并行阶段可测）
- `app.core.provider.get_provider` 缺失时返回 None，业务层据此降级
- `app.core.tools.register` 缺失时只记录警告

工具（Function Calling schema 在 core 侧）：list_inventory / find_recipes /
get_shelf_life / estimate_carbon / log_consumption。
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_LIST_LIMIT = 10
DEFAULT_RECIPE_LIMIT = 6
RECIPE_CANDIDATE_MULTIPLIER = 2

try:  # 契约 §7.1：core 提供，B 只调用
    from app.core.errors import AppError  # type: ignore[assignment]
except ImportError:  # 并行开发阶段 core 可能还没落盘
    class AppError(Exception):  # type: ignore[no-redef]
        """core 未就绪时的兜底错误类型，字段与契约一致。"""

        def __init__(
            self,
            code: str,
            message: str,
            status: int = 400,
            detail: str | None = None,
        ) -> None:
            super().__init__(message)
            self.code = code
            self.message = message
            self.status = status
            self.detail = detail


def resolve_provider(provider: Any = None):
    """优先用注入的 provider（测试用 FakeProvider），否则取 core 的全局 provider。"""
    if provider is not None:
        return provider
    try:
        from app.core.provider import get_provider
    except ImportError:
        logger.warning("app.core.provider 尚不可用，本次走降级路径")
        return None
    try:
        return get_provider()
    except Exception:  # provider 初始化失败也要能降级
        logger.exception("获取 provider 失败，本次走降级路径")
        return None


def _loads(value: str | None, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def list_inventory(sort: str = "expiry", limit: int = DEFAULT_LIST_LIMIT) -> dict:
    """临期优先的库存列表（Agent `plan` 步调用）。"""
    from app.domain import inventory as inventory_domain

    items = inventory_domain.list_inventory("active")
    if sort == "added":
        items.sort(key=lambda item: item.get("added_at") or "", reverse=True)
    else:
        items.sort(key=lambda item: item.get("days_left", 0))
    return {"items": items[: max(limit, 1)], "count": len(items), "sort": sort}


def get_shelf_life(name: str) -> dict:
    """查食材保质期与保存建议。"""
    from app.db.conn import get_conn
    from app.domain.inventory import find_item

    conn = get_conn()
    try:
        row = find_item(conn, str(name or "").strip())
    finally:
        conn.close()

    if row is None:
        return {
            "name": name,
            "matched": False,
            "message": "食材库里没有这个食材，无法给出保质期（不编造数据）",
        }
    return {
        "name": row["name"],
        "matched": True,
        "item_id": row["id"],
        "category": row["category"],
        "shelf_life_days": row["shelf_life_days"],
        "storage_tip": row["storage_tip"],
        "unit": row["unit"],
        "avg_grams": row["avg_grams"],
        "carbon_kg_per_kg": row["carbon_kg_per_kg"],
        "price_per_kg": row["price_per_kg"],
    }


def estimate_carbon(name: str, grams: float) -> dict:
    """按食材碳因子估算碳当量与金额（碳账唯一口径）。"""
    from app.domain.inventory import DEFAULT_CARBON_KG_PER_KG, DEFAULT_PRICE_PER_KG

    detail = get_shelf_life(name)
    if not detail.get("matched"):
        return {"name": name, "matched": False, "carbon_kg": 0.0, "money": 0.0, "grams": grams}

    grams = float(grams or 0)
    carbon_factor = float(detail.get("carbon_kg_per_kg") or DEFAULT_CARBON_KG_PER_KG)
    price = float(detail.get("price_per_kg") or DEFAULT_PRICE_PER_KG)
    return {
        "name": detail["name"],
        "matched": True,
        "grams": grams,
        "carbon_kg": round(grams / 1000.0 * carbon_factor, 4),
        "money": round(grams / 1000.0 * price, 2),
    }


def find_recipes(
    ingredients: list[str] | None = None, max_minutes: int | None = None, limit: int = DEFAULT_RECIPE_LIMIT
) -> dict:
    """按食材 + 时间上限检索菜谱（RAG 混合检索，返回带引用的 chunk）。"""
    from app.db.conn import get_conn
    from app.rag import retrieve

    names = [str(name).strip() for name in (ingredients or []) if str(name).strip()]
    query = " ".join(names) if names else "家常菜"

    conn = get_conn()
    try:
        hits = retrieve.search(query, limit=max(limit, 1) * RECIPE_CANDIDATE_MULTIPLIER, conn=conn)
        items: list[dict] = []
        for hit in hits:
            source = hit.get("source") or ""
            if not source.startswith("recipe:"):
                continue
            recipe_id = source.split(":", 1)[1]
            row = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
            if row is None:
                continue
            minutes = int(row["minutes"] or 0)
            if max_minutes and minutes > int(max_minutes):
                continue
            recipe_ingredients = _loads(row["ingredients"], [])
            steps = _loads(row["steps"], [])
            missing = _missing_ingredients(recipe_ingredients, names)
            items.append(
                {
                    "recipe_id": recipe_id,
                    "title": row["title"],
                    "minutes": minutes,
                    "servings": row["servings"],
                    "difficulty": row["difficulty"],
                    "tags": row["tags"],
                    "ingredients": recipe_ingredients,
                    "steps_count": len(steps),
                    "missing": missing,
                    "score": hit.get("score", 0.0),
                    "rel": hit.get("rel", 0.0),
                    "source": source,
                    "locator": hit.get("locator"),
                    "body": hit.get("body"),
                    "matched_by": hit.get("matched_by", []),
                }
            )
            if len(items) >= max(limit, 1):
                break
    finally:
        conn.close()

    return {"items": items, "count": len(items), "query": query}


def _missing_ingredients(recipe_ingredients: list[dict], stocks: list[str]) -> list[dict]:
    missing: list[dict] = []
    for ingredient in recipe_ingredients:
        name = str(ingredient.get("name") or "").strip()
        if not name:
            continue
        if any(name in stock or stock in name for stock in stocks):
            continue
        missing.append({"name": name, "optional": bool(ingredient.get("optional", False))})
    return missing


def log_consumption(inventory_id: str, grams: float | None = None) -> dict:
    """消耗库存并记账（Agent 确认「我做了这道菜」时调用）。"""
    from app.domain import inventory as inventory_domain

    data = inventory_domain.consume(inventory_id, grams)
    return {
        "inventory_id": inventory_id,
        "consumed_grams": data.get("consumed_grams", 0.0),
        "status": data.get("status"),
        "level": data.get("level"),
    }


TOOL_FUNCTIONS = {
    "list_inventory": list_inventory,
    "find_recipes": find_recipes,
    "get_shelf_life": get_shelf_life,
    "estimate_carbon": estimate_carbon,
    "log_consumption": log_consumption,
}

_registered = False


def register_all() -> list[str]:
    """把工具注册进 core 的注册表（幂等；core 缺失时静默跳过）。"""
    global _registered
    if _registered:
        return list(TOOL_FUNCTIONS)
    try:
        from app.core.tools import register
    except ImportError:
        logger.warning("app.core.tools 尚不可用，跳过工具注册")
        return []

    for name, fn in TOOL_FUNCTIONS.items():
        try:
            register(name, fn)
        except Exception:
            logger.exception("注册工具失败：%s", name)
    _registered = True
    return list(TOOL_FUNCTIONS)
