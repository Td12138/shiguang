"""生成演示用历史数据：让「浪费率 / 碳账」页在录视频时有真实曲线。

用法（在 apps/server 下）：
    python scripts/seed_demo.py --reset        # 清空库存与浪费记录后重建
    python scripts/seed_demo.py --days 30      # 默认就是 30 天

设计口径（与契约 §6.5 一致）：
    grams     = qty × items.avg_grams
    carbon_kg = grams/1000 × items.carbon_kg_per_kg
    waste_rate= thrown / (thrown + saved)
目标区间：浪费率 15–20%，碳账 4–6 kg，曲线有起伏（不是一条直线）。
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.db.conn import connection, init_db  # noqa: E402

HISTORY_DAYS = 30

# (食材 id, 数量, 天数前买入, 结局, 丢弃原因)  —— 结局: consumed / discarded
HISTORY: tuple[tuple[str, float, int, str, str], ...] = (
    ("spinach", 1, 27, "discarded", "forgot"),
    ("tomato", 3, 26, "consumed", ""),
    ("egg", 10, 25, "consumed", ""),
    ("firm_tofu", 2, 24, "consumed", ""),
    ("chicken_breast", 2, 22, "consumed", ""),
    ("broccoli", 2, 21, "discarded", "spoiled"),
    ("milk", 1, 20, "consumed", ""),
    ("lettuce", 1, 19, "consumed", ""),
    ("pork_tenderloin", 1, 18, "consumed", ""),
    ("cucumber", 3, 16, "consumed", ""),
    ("yogurt", 3, 15, "discarded", "too_much"),
    ("shiitake", 4, 14, "consumed", ""),
    ("noodles", 1, 13, "consumed", ""),
    ("green_pepper", 2, 12, "consumed", ""),
    ("frozen_shrimp", 1, 11, "discarded", "forgot"),
    ("carrot", 3, 9, "consumed", ""),
    ("napa_cabbage", 1, 8, "consumed", ""),
    ("beef_brisket", 1, 6, "consumed", ""),
    ("rice", 2, 5, "consumed", ""),
    ("tomato", 2, 3, "consumed", ""),
)

# 当前库存：(食材 id, 数量, 剩余天数)。剩余天数为负 = 已过期
ACTIVE: tuple[tuple[str, float, int], ...] = (
    ("spinach", 1, -1),        # 已过期，演示红色
    ("lettuce", 1, 1),         # 明天到期，演示黄色
    ("tomato", 3, 3),
    ("egg", 6, 20),
    ("firm_tofu", 1, 2),
    ("chicken_breast", 1, 60),
    ("milk", 1, 5),
    ("shiitake", 4, 3),
)


def _item_row(conn, item_id: str):
    return conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def main() -> int:
    parser = argparse.ArgumentParser(description="生成演示历史数据")
    parser.add_argument("--reset", action="store_true", help="先清空 inventory / waste_log")
    parser.add_argument("--days", type=int, default=HISTORY_DAYS)
    args = parser.parse_args()

    init_db()
    today = date.today()
    now = datetime.now().astimezone()

    with connection() as conn:
        if args.reset:
            conn.execute("DELETE FROM waste_log")
            conn.execute("DELETE FROM inventory")
            conn.execute("DELETE FROM events")

        created = 0
        for item_id, qty, days_ago, verdict, reason in HISTORY:
            item = _item_row(conn, item_id)
            if item is None:
                continue
            added = today - timedelta(days=days_ago)
            expires = added + timedelta(days=int(item["shelf_life_days"]))
            grams = qty * float(item["avg_grams"] or 100)
            inv_id = _new_id("inv")
            stamp = (now - timedelta(days=days_ago)).isoformat(timespec="seconds")
            conn.execute(
                "INSERT INTO inventory(id,item_id,name,qty,unit,grams,added_at,expires_at,status,"
                "image_id,confidence,note) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (inv_id, item_id, item["name"], qty, item["unit"], grams,
                 added.isoformat(), expires.isoformat(), verdict, "", 0.9, ""),
            )
            if verdict == "discarded":
                carbon = grams / 1000.0 * float(item["carbon_kg_per_kg"] or 0)
                conn.execute(
                    "INSERT INTO waste_log(id,inventory_id,name,grams,reason,carbon_kg,created_at)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (_new_id("waste"), inv_id, item["name"], grams, reason, carbon, stamp),
                )
            else:
                # 统计口径（stats.py）只认 events.kind='consume'，这里补齐，否则 saved_grams 恒为 0
                carbon = grams / 1000.0 * float(item["carbon_kg_per_kg"] or 0)
                money = grams / 1000.0 * float(item["price_per_kg"] or 0)
                conn.execute(
                    "INSERT INTO events(id,kind,payload,created_at) VALUES(?,?,?,?)",
                    (
                        _new_id("evt"),
                        "consume",
                        json.dumps(
                            {
                                "name": item["name"],
                                "inventory_id": inv_id,
                                "grams": round(grams, 1),
                                "carbon_saved_kg": round(carbon, 3),
                                "money_saved": round(money, 2),
                            },
                            ensure_ascii=False,
                        ),
                        stamp,
                    ),
                )
            created += 1

        for item_id, qty, days_left in ACTIVE:
            item = _item_row(conn, item_id)
            if item is None:
                continue
            expires = today + timedelta(days=days_left)
            added = expires - timedelta(days=int(item["shelf_life_days"]))
            grams = qty * float(item["avg_grams"] or 100)
            conn.execute(
                "INSERT INTO inventory(id,item_id,name,qty,unit,grams,added_at,expires_at,status,"
                "image_id,confidence,note) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (_new_id("inv"), item_id, item["name"], qty, item["unit"], grams,
                 added.isoformat(), expires.isoformat(), "active", "", 0.9, ""),
            )
            created += 1

        row = conn.execute(
            "SELECT COUNT(*) AS n FROM inventory WHERE status='active'"
        ).fetchone()

    print(f"已写入 {created} 条记录，其中在库 {row['n']} 条；历史窗口 {args.days} 天")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
