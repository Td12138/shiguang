"""统计业务域（契约 §6.5 公式）。

口径（与 inventory.py 一致）：
- `saved_grams` = 已 consume 的克数（events.kind='consume'）
- `thrown_grams` = 已 discard 的克数（waste_log）
- `waste_rate = thrown / (thrown + saved)`
- `carbon_saved_kg` = Σ(consume 克数/1000 × items.carbon_kg_per_kg)
- `money_saved` = Σ(consume 克数/1000 × items.price_per_kg)
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta

from app.db.conn import get_conn

logger = logging.getLogger(__name__)

# 等效换算常量（公开因子表，避免魔法数字）
CARBON_KG_PER_CAR_KM = 0.15
CARBON_KG_PER_TREE_DAY = 0.06
DEFAULT_RANGE = "30d"
DEFAULT_RANGE_DAYS = 30
MAX_RANGE_DAYS = 365
RANGE_PATTERN = re.compile(r"^(\d{1,6})d$")

EVENT_CONSUME = "consume"


def _today() -> date:
    return datetime.now().astimezone().date()


def parse_range(value: str | None) -> tuple[int | None, str]:
    """把 `30d` / `7d` / `all` 解析成 (天数, 规范化标签)。无法识别回落默认。"""
    raw = str(value or "").strip().lower()
    if raw in ("all", "all_time", ""):
        return (None if raw in ("all", "all_time") else DEFAULT_RANGE_DAYS), (
            "all" if raw in ("all", "all_time") else DEFAULT_RANGE
        )
    match = RANGE_PATTERN.match(raw)
    if not match:
        return DEFAULT_RANGE_DAYS, DEFAULT_RANGE
    days = max(1, min(int(match.group(1)), MAX_RANGE_DAYS))
    return days, f"{days}d"


def _window_start(days: int | None) -> date | None:
    if days is None:
        return None
    return _today() - timedelta(days=days - 1)


def _day_of(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(value)[:10]
    except Exception:
        return None


def _in_window(day: str | None, start: date | None) -> bool:
    if start is None:
        return True
    return bool(day) and day >= start.isoformat()


def _load_items(conn) -> dict[str, dict]:
    return {
        row["name"]: dict(row)
        for row in conn.execute(
            "SELECT name, carbon_kg_per_kg, price_per_kg, avg_grams FROM items"
        ).fetchall()
    }


def _sum_consumed(conn, start: date | None) -> tuple[float, float, float, dict[str, float]]:
    """返回 (saved_grams, carbon_saved_kg, money_saved, 按天 saved)。"""
    items = _load_items(conn)
    rows = conn.execute(
        "SELECT payload, created_at FROM events WHERE kind = ?", (EVENT_CONSUME,)
    ).fetchall()

    saved_grams = 0.0
    carbon_saved = 0.0
    money_saved = 0.0
    by_day: dict[str, float] = {}

    for row in rows:
        day = _day_of(row["created_at"])
        if not _in_window(day, start):
            continue
        try:
            payload = json.loads(row["payload"] or "{}")
        except json.JSONDecodeError:
            payload = {}
        grams = float(payload.get("grams") or 0.0)
        if grams <= 0:
            continue
        factor = items.get(str(payload.get("name") or ""), {})
        carbon = payload.get("carbon_saved_kg")
        money = payload.get("money_saved")
        if carbon is None:
            carbon = grams / 1000.0 * float(factor.get("carbon_kg_per_kg") or 0.0)
        if money is None:
            money = grams / 1000.0 * float(factor.get("price_per_kg") or 0.0)
        saved_grams += grams
        carbon_saved += float(carbon)
        money_saved += float(money)
        by_day[day] = by_day.get(day, 0.0) + grams

    return saved_grams, carbon_saved, money_saved, by_day


def _sum_thrown(conn, start: date | None) -> tuple[float, float, dict[str, float]]:
    """返回 (thrown_grams, thrown_carbon_kg, 按天 thrown)。"""
    rows = conn.execute("SELECT grams, carbon_kg, created_at FROM waste_log").fetchall()
    thrown_grams = 0.0
    thrown_carbon = 0.0
    by_day: dict[str, float] = {}
    for row in rows:
        day = _day_of(row["created_at"])
        if not _in_window(day, start):
            continue
        grams = float(row["grams"] or 0.0)
        thrown_grams += grams
        thrown_carbon += float(row["carbon_kg"] or 0.0)
        by_day[day] = by_day.get(day, 0.0) + grams
    return thrown_grams, thrown_carbon, by_day


def _trend(days: int | None, saved_by_day: dict, thrown_by_day: dict) -> list[dict]:
    if days is None:
        known = sorted(set(saved_by_day) | set(thrown_by_day))
        if not known:
            return []
        start = date.fromisoformat(known[0])
        days = min((_today() - start).days + 1, MAX_RANGE_DAYS)
    start = _window_start(days) or _today()
    series: list[dict] = []
    for offset in range(days):
        day = (start + timedelta(days=offset)).isoformat()
        series.append(
            {
                "date": day,
                "thrown": round(thrown_by_day.get(day, 0.0), 1),
                "saved": round(saved_by_day.get(day, 0.0), 1),
            }
        )
    return series


def summary(range_value: str = DEFAULT_RANGE) -> dict:
    """GET /api/stats/summary 的数据源。"""
    days, label = parse_range(range_value)
    start = _window_start(days)

    conn = get_conn()
    try:
        saved_grams, carbon_saved, money_saved, saved_by_day = _sum_consumed(conn, start)
        thrown_grams, thrown_carbon, thrown_by_day = _sum_thrown(conn, start)
    finally:
        conn.close()

    total = thrown_grams + saved_grams
    waste_rate = (thrown_grams / total) if total > 0 else 0.0

    return {
        "range": label,
        "waste_rate": round(waste_rate, 3),
        "thrown_grams": round(thrown_grams, 1),
        "saved_grams": round(saved_grams, 1),
        "carbon_saved_kg": round(carbon_saved, 2),
        "carbon_thrown_kg": round(thrown_carbon, 2),
        "money_saved": round(money_saved, 2),
        "equivalents": {
            "car_km": round(carbon_saved / CARBON_KG_PER_CAR_KM),
            "trees_days": round(carbon_saved / CARBON_KG_PER_TREE_DAY),
        },
        "trend": _trend(days, saved_by_day, thrown_by_day),
    }


def top_waste(limit: int = 3) -> list[dict]:
    """丢弃最多的食材 top-N（周报用）。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT name, SUM(grams) AS grams, SUM(carbon_kg) AS carbon_kg FROM waste_log"
            " GROUP BY name ORDER BY grams DESC LIMIT ?",
            (max(1, limit),),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "name": row["name"],
            "grams": round(float(row["grams"] or 0.0), 1),
            "carbon_kg": round(float(row["carbon_kg"] or 0.0), 2),
        }
        for row in rows
    ]
