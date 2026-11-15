"""库存业务域（契约 §5 计量口径 / §6.3 API）。

计量口径（唯一实现处，其它模块只调用）：
- `grams = qty × items.avg_grams`
- `carbon_kg = grams/1000 × items.carbon_kg_per_kg`
- `money_saved = consumed_grams/1000 × items.price_per_kg`
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Any

from app.db.conn import get_conn
from app.domain.tools_registry import AppError

logger = logging.getLogger(__name__)

DEFAULT_QTY = 1.0
DEFAULT_AVG_GRAMS = 200.0
DEFAULT_CARBON_KG_PER_KG = 1.0
DEFAULT_PRICE_PER_KG = 5.0
DEFAULT_SHELF_LIFE_DAYS = 5
DEFAULT_UNIT = "份"

STATUS_ACTIVE = "active"
STATUS_CONSUMED = "consumed"
STATUS_DISCARDED = "discarded"
VALID_STATUSES = (STATUS_ACTIVE, STATUS_CONSUMED, STATUS_DISCARDED)

LEVEL_FRESH = "fresh"
LEVEL_SOON = "soon"
LEVEL_URGENT = "urgent"
LEVEL_EXPIRED = "expired"
FRESH_MIN_DAYS = 4  # days_left > 3
SOON_MIN_DAYS = 2  # 2-3 天
URGENT_MIN_DAYS = 0  # 0-1 天

EVENT_CONSUME = "consume"
DISCARD_REASONS = ("forgot", "spoiled", "too_much")
EPSILON = 1e-6

# 库存查询统一带上食材分类（前端「冰箱全景」分组用）：item_id 命不中时退回按名字匹配
INVENTORY_SELECT = (
    "SELECT i.*, COALESCE("
    " (SELECT it.category FROM items it WHERE it.id = i.item_id),"
    " (SELECT it2.category FROM items it2 WHERE it2.name = i.name LIMIT 1)"
    ") AS category FROM inventory i"
)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def today() -> date:
    return datetime.now().astimezone().date()


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def days_left(expires_at: str | None, *, today_date: date | None = None) -> int:
    """expires_at - today，整数，可为负。无法解析时按 0 处理。"""
    target = parse_date(expires_at)
    if target is None:
        return 0
    return (target - (today_date or today())).days


def level_for(days: int) -> str:
    """分级：>3 fresh，2–3 soon，0–1 urgent，<0 expired。"""
    if days < URGENT_MIN_DAYS:
        return LEVEL_EXPIRED
    if days <= 1:
        return LEVEL_URGENT
    if days <= 3:
        return LEVEL_SOON
    return LEVEL_FRESH


def _new_id(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def find_item(conn, name: str, item_id: str | None = None):
    """按 id / 精确名 / 互相包含匹配食材库，找不到返回 None。"""
    if item_id:
        row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if row:
            return row
    if not name:
        return None
    row = conn.execute("SELECT * FROM items WHERE name = ?", (name,)).fetchone()
    if row:
        return row
    return conn.execute(
        "SELECT * FROM items WHERE ? LIKE '%' || name || '%' OR name LIKE '%' || ? || '%'"
        " ORDER BY LENGTH(name) DESC LIMIT 1",
        (name, name),
    ).fetchone()


def _item_metric(item, column: str, default: float) -> float:
    if item is None:
        return default
    try:
        value = item[column]
    except (KeyError, IndexError):
        return default
    return float(value) if value is not None else default


def _row_to_dict(row) -> dict[str, Any]:
    data = dict(row)
    days = days_left(data.get("expires_at"))
    data["days_left"] = days
    data["level"] = level_for(days)
    return data


def _fetch(conn, inv_id: str):
    row = conn.execute(
        f"{INVENTORY_SELECT} WHERE i.id = ?", (inv_id,)
    ).fetchone()
    if row is None:
        raise AppError("inventory_not_found", f"库存记录不存在：{inv_id}", 404)
    return row


def _added_at(value: str | None) -> str | None:
    """契约 §6.11：小票确认入库时 `added_at` 用购物日期（只给 YYYY-MM-DD 也接受）。"""
    parsed = parse_date(value)
    if parsed is None:
        return None
    return datetime.combine(parsed, datetime.min.time()).astimezone().isoformat(timespec="seconds")


def add_items(payload: dict) -> dict:
    """入库（识别结果需人工确认后走这里）。返回 {"added": n, "ids": [...]}。"""
    raw_items = payload.get("items") or []
    image_id = payload.get("image_id")
    ids: list[str] = []
    # 缺省现在是入库时间；只有显式传了有效日期才用购物日期
    timestamp = _added_at(payload.get("added_at")) or now_iso()
    conn = get_conn()
    try:
        for raw in raw_items:
            name = str(raw.get("name") or "").strip()
            if not name:
                continue
            item = find_item(conn, name, raw.get("item_id"))
            qty = float(raw.get("qty") or DEFAULT_QTY)
            avg_grams = _item_metric(item, "avg_grams", DEFAULT_AVG_GRAMS)
            grams = qty * avg_grams
            unit = raw.get("unit") or (item["unit"] if item and item["unit"] else DEFAULT_UNIT)
            shelf = int(_item_metric(item, "shelf_life_days", DEFAULT_SHELF_LIFE_DAYS))
            expires = parse_date(raw.get("expires_at")) or (today() + timedelta(days=shelf))
            inv_id = _new_id("inv_")
            conn.execute(
                "INSERT INTO inventory(id,item_id,name,qty,unit,grams,added_at,expires_at,"
                "status,image_id,confidence,note) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    inv_id,
                    item["id"] if item else raw.get("item_id"),
                    name,
                    qty,
                    unit,
                    grams,
                    timestamp,
                    expires.isoformat(),
                    STATUS_ACTIVE,
                    image_id,
                    raw.get("confidence"),
                    str(raw.get("note") or ""),
                ),
            )
            ids.append(inv_id)
        conn.commit()
    finally:
        conn.close()

    logger.info("入库 %d 条（image_id=%s）", len(ids), image_id)
    return {"added": len(ids), "ids": ids}


def list_inventory(status: str = STATUS_ACTIVE) -> list[dict]:
    conn = get_conn()
    try:
        if status and status != "all":
            rows = conn.execute(
                f"{INVENTORY_SELECT} WHERE i.status = ?", (status,)
            ).fetchall()
        else:
            rows = conn.execute(INVENTORY_SELECT).fetchall()
    finally:
        conn.close()

    items = [_row_to_dict(row) for row in rows]
    items.sort(key=lambda item: (item["days_left"], item["name"]))
    return items


def get_inventory(inv_id: str) -> dict:
    conn = get_conn()
    try:
        return _row_to_dict(_fetch(conn, inv_id))
    finally:
        conn.close()


def update_inventory(
    inv_id: str,
    *,
    qty: float | None = None,
    expires_at: str | None = None,
    note: str | None = None,
) -> dict:
    """改数量 / 到期日 / 备注；改数量时按 avg_grams 重算克数。"""
    conn = get_conn()
    try:
        row = _fetch(conn, inv_id)
        new_qty = float(row["qty"]) if row["qty"] is not None else DEFAULT_QTY
        new_expires = row["expires_at"]
        new_note = row["note"]
        new_grams = float(row["grams"]) if row["grams"] is not None else 0.0

        if qty is not None:
            if qty <= 0:
                raise AppError("invalid_qty", "数量必须大于 0", 400)
            item = find_item(conn, row["name"], row["item_id"])
            avg_grams = _item_metric(item, "avg_grams", DEFAULT_AVG_GRAMS)
            new_qty = float(qty)
            new_grams = new_qty * avg_grams
        if expires_at is not None:
            parsed = parse_date(expires_at)
            if parsed is None:
                raise AppError("invalid_expires_at", "到期日格式应为 YYYY-MM-DD", 400)
            new_expires = parsed.isoformat()
        if note is not None:
            new_note = str(note)

        conn.execute(
            "UPDATE inventory SET qty = ?, grams = ?, expires_at = ?, note = ? WHERE id = ?",
            (new_qty, new_grams, new_expires, new_note, inv_id),
        )
        conn.commit()
        row = _fetch(conn, inv_id)
    finally:
        conn.close()
    return _row_to_dict(row)


def _consume_query(conn, row, grams: float | None) -> tuple[float, float, float, float]:
    """计算本次扣减量及对应碳/金额（基于食材库因子）。"""
    remaining = float(row["grams"]) if row["grams"] is not None else 0.0
    take = remaining if grams is None else min(max(float(grams), 0.0), remaining)
    item = find_item(conn, row["name"], row["item_id"])
    carbon_factor = _item_metric(item, "carbon_kg_per_kg", DEFAULT_CARBON_KG_PER_KG)
    price = _item_metric(item, "price_per_kg", DEFAULT_PRICE_PER_KG)
    carbon_kg = take / 1000.0 * carbon_factor
    money = take / 1000.0 * price
    return take, remaining - take, carbon_kg, money


def _qty_after(row, left_grams: float) -> float:
    """按克数比例折算剩余数量（consume 只改 grams 会让 qty 与库存脱节）。"""
    total_grams = float(row["grams"]) if row["grams"] is not None else 0.0
    qty = float(row["qty"]) if row["qty"] is not None else 0.0
    if left_grams <= EPSILON:
        return 0.0
    if total_grams <= EPSILON or qty <= EPSILON:
        return qty
    ratio = max(0.0, min(1.0, left_grams / total_grams))
    return round(qty * ratio, 3)


def consume(inv_id: str, grams: float | None = None) -> dict:
    """消耗库存：按克数比例扣 qty 与 grams，扣完置 consumed，并写 events 供统计口径使用。"""
    conn = get_conn()
    try:
        row = _fetch(conn, inv_id)
        if row["status"] != STATUS_ACTIVE:
            raise AppError("inventory_not_active", f"库存状态为 {row['status']}，无法消耗", 409)
        take, left, carbon_kg, money = _consume_query(conn, row, grams)
        status = STATUS_CONSUMED if left <= EPSILON else STATUS_ACTIVE
        conn.execute(
            "UPDATE inventory SET qty = ?, grams = ?, status = ? WHERE id = ?",
            (_qty_after(row, left), max(left, 0.0), status, inv_id),
        )
        conn.execute(
            "INSERT INTO events(id,kind,payload,created_at) VALUES(?,?,?,?)",
            (
                _new_id("ev_"),
                EVENT_CONSUME,
                json.dumps(
                    {
                        "inventory_id": inv_id,
                        "item_id": row["item_id"],
                        "name": row["name"],
                        "grams": take,
                        "carbon_saved_kg": carbon_kg,
                        "money_saved": money,
                    },
                    ensure_ascii=False,
                ),
                now_iso(),
            ),
        )
        conn.commit()
        row = _fetch(conn, inv_id)
    finally:
        conn.close()

    data = _row_to_dict(row)
    data["consumed_grams"] = round(take, 2)
    return data


def discard(inv_id: str, reason: str, grams: float | None = None) -> dict:
    """丢弃库存：写 waste_log（含碳当量），扣完置 discarded。"""
    normalized = str(reason or "").strip()
    if normalized not in DISCARD_REASONS:
        raise AppError(
            "invalid_reason",
            f"丢弃原因必须是 {'/'.join(DISCARD_REASONS)} 之一",
            400,
        )

    conn = get_conn()
    try:
        row = _fetch(conn, inv_id)
        if row["status"] != STATUS_ACTIVE:
            raise AppError("inventory_not_active", f"库存状态为 {row['status']}，无法丢弃", 409)
        take, left, carbon_kg, _money = _consume_query(conn, row, grams)
        status = STATUS_DISCARDED if left <= EPSILON else STATUS_ACTIVE
        conn.execute(
            "UPDATE inventory SET qty = ?, grams = ?, status = ? WHERE id = ?",
            (_qty_after(row, left), max(left, 0.0), status, inv_id),
        )
        conn.execute(
            "INSERT INTO waste_log(id,inventory_id,name,grams,reason,carbon_kg,created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (
                _new_id("wl_"),
                inv_id,
                row["name"],
                take,
                normalized,
                carbon_kg,
                now_iso(),
            ),
        )
        conn.commit()
        row = _fetch(conn, inv_id)
    finally:
        conn.close()

    data = _row_to_dict(row)
    data["discarded_grams"] = round(take, 2)
    data["carbon_kg"] = round(carbon_kg, 4)
    return data
