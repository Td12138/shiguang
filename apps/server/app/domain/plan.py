"""饮食计划 Agent（契约 §2 P0-8 / §6.8）。

五步：understand → plan → allocate → compose → verify，trace 落 `agent_runs`
（kind=`meal_plan`）。返回 `plan_id` + `run_id`。

硬规则（也是 verify 的判定条件，代码内独立复算、不信任上游）：
1. 过期食材绝不进计划，只在 warnings 提示
2. 同一食材跨餐累计用量不超过库存数量
3. 每餐必须挂真实 recipe_id（存在于 recipes 表）与 citations
4. 优先消耗 3 天内到期的食材（coverage.expiring_used 可核对）
5. 缺料合并成一份购物清单，同一食材不重复

降级（模型不可用 / 输出未过校验）：按到期顺序 + BM25 命中做贪心分配，
warnings 标「已降级」，同样要过 verify。
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, Field

from app.db.conn import ensure_schema, get_conn
from app.domain import instruction as instruction_parser
from app.domain import preferences as preference_store
from app.domain import tools_registry
from app.domain.inventory import now_iso
from app.domain.recipes import (
    _Stopwatch,
    _Trace,
    _invoke_tool,
    resolve_provider,
)
from app.domain.recipes import _persist_run as _persist_recipe_run
from app.domain.tools_registry import AppError
from app.rag import citations as citation_utils

logger = logging.getLogger(__name__)

RUN_KIND = "meal_plan"
EVENT_KIND = "meal_plan"
STATE_RUNNING = "running"
STATE_OK = "ok"
STATE_DEGRADED = "degraded"
STATE_FAILED = "failed"

STEP_UNDERSTAND = "understand"
STEP_PLAN = "plan"
STEP_ALLOCATE = "allocate"
STEP_COMPOSE = "compose"
STEP_VERIFY = "verify"

DEFAULT_DAYS = 3
MAX_DAYS = 7
DEFAULT_SERVINGS = 1
DEFAULT_MAX_MINUTES = 30
MEAL_SLOTS: tuple[str, ...] = ("午餐", "晚餐")
PLAN_TOP_K = 50
CANDIDATE_POOL = 12
EXPIRING_DAYS = 3
MIN_RECIPE_STEPS = 3
EPSILON = 1e-6

SCORE_EXPIRING = 3.0
SCORE_STOCKED = 1.2
PENALTY_MISSING = 0.8
PENALTY_MINUTES = 0.02
PENALTY_REPEAT_RECIPE = 0.6
PENALTY_SAME_AS_PREV = 2.5
SCORE_RELEVANCE = 0.5

DEGRADE_WARNING = "已降级：模型不可用或输出未通过校验，本次按到期顺序 + 检索命中做贪心分配"
EMPTY_INVENTORY_WARNING = "库存为空，先拍照识别或手动入库再生成计划"
NO_RECIPE_WARNING = "菜谱库里没有匹配的菜谱，暂时无法生成计划"
EXPIRED_WARNING_TEMPLATE = "「{name}」已过期 {days} 天，先处理掉（不会进计划）"
UNUSED_EXPIRING_TEMPLATE = "「{name}」{days} 天后到期，这次没排进计划，记得优先吃掉"
PREFERENCE_EXCLUDED_TEMPLATE = "已按忌口偏好排除：{names}"
ALL_BLOCKED_WARNING = "候选菜谱都含有你忌口的食材（{names}），改一下偏好或先补充别的食材"
EMPTY_PLAN_REVISE_WARNING = "这个计划当时没有可用食材，先补库存再重新生成吧"

UNDERSTAND_SYSTEM = "阶段：understand\n你是「食光」的配餐助手，只输出 JSON。"
COMPOSE_SYSTEM = "阶段：compose\n你是「食光」的配餐助手，只能从给定的菜谱里选，只输出 JSON。"
REVISE_SYSTEM = "阶段：revise\n你是「食光」的配餐助手，只输出 JSON，不输出解释。"

# ---- 改计划（契约 §6.9）----
REVISE_MAX_INSTRUCTION = 500
REVISE_LIGHT_BONUS = 2.0
REVISE_SWAP_BONUS = 5.0
REVISE_HEAVY_PENALTY = 1.0
REVISE_SAME_RECIPE_PENALTY = 0.5

LIGHT_KEYWORDS: tuple[str, ...] = (
    "清炒",
    "清蒸",
    "白灼",
    "蒸",
    "煮",
    "汤",
    "拌",
    "焯",
    "凉拌",
    "炖",
)
HEAVY_KEYWORDS: tuple[str, ...] = ("辣", "炸", "红烧", "油焖", "干锅", "煎", "烤", "肥", "奶油", "芝士")
REVISE_NO_CHANGE_TEMPLATE = "指令里没有能落到这份计划上的改动（{detail}），计划保持不变"
REVISE_NO_CANDIDATE_TEMPLATE = "没有符合条件的菜谱（{constraints}），{scope}保持不变"
REVISE_DEGRADED_WARNING = "已降级：模型不可用，本次指令按规则解析"
REVISE_CONFLICT_TEMPLATE = "本次指令要「{name}」，与你之前记住的偏好「{text}」冲突，已按本次指令处理"
REVISE_LEARNED_LOW_TEMPLATE = "可能记住：{text}（置信度 {confidence}，确认后才会生效）"
REVISE_SCOPE_TEMPLATE = "{date} {slot}"
REVISE_WHOLE_PLAN = "整份计划"


def _new_plan_id() -> str:
    return f"plan_{uuid.uuid4().hex[:12]}"


def _persist_run(run_id: str, state: str, steps: list[dict]) -> None:
    _persist_recipe_run(run_id, state, steps, RUN_KIND)


def _round_qty(value: float) -> float | int:
    if abs(value - round(value)) < 1e-6:
        return int(round(value))
    return round(value, 2)


def _norm(name: Any) -> str:
    return str(name or "").strip()


def _match_stock(name: str, keys: list[str]) -> str | None:
    for key in keys:
        if key == name or key in name or name in key:
            return key
    return None


# --------------------------------------------------------------------------- #
# 库存快照与候选菜谱
# --------------------------------------------------------------------------- #

def _split_inventory(items: list[dict]) -> dict:
    usable = [item for item in items if int(item.get("days_left", 0)) >= 0]
    expired = [item for item in items if int(item.get("days_left", 0)) < 0]
    return {
        "usable": usable,
        "expired": expired,
        "stock": {item["name"]: item for item in usable},
        "expiring": {
            item["name"] for item in usable if int(item.get("days_left", 0)) <= EXPIRING_DAYS
        },
    }


def _expired_warnings(snapshot: dict) -> list[str]:
    return [
        EXPIRED_WARNING_TEMPLATE.format(name=item["name"], days=abs(int(item["days_left"])))
        for item in snapshot["expired"]
    ]


# --------------------------------------------------------------------------- #
# 分配（贪心 + 统一 materialize）
# --------------------------------------------------------------------------- #

def _deduct(
    recipe: dict, remaining: dict[str, float], stock: dict[str, dict], servings: int
) -> tuple[list[dict], list[dict], list[dict]]:
    """按库存扣减一道菜，返回 (uses, missing, shortfalls)。"""
    uses: dict[str, dict] = {}
    missing: list[dict] = []
    shortfalls: list[dict] = []

    for ingredient in recipe.get("ingredients", []):
        name = _norm(ingredient.get("name"))
        if not name:
            continue
        need = float(ingredient.get("qty") or 1) * servings
        optional = bool(ingredient.get("optional"))
        key = _match_stock(name, list(remaining))
        stock_row = stock.get(key) or {}
        available = float(remaining.get(key, 0.0)) if key else 0.0
        unit = stock_row.get("unit") or ingredient.get("unit") or "份"
        take = min(need, available)
        label = key or name

        if take > EPSILON:
            if label in uses:
                uses[label]["qty"] += take
            else:
                # inventory_id 让前端「做了这道菜」能直接按 id 扣库存
                uses[label] = {
                    "name": label,
                    "qty": take,
                    "unit": unit,
                    "inventory_id": stock_row.get("id"),
                }
            remaining[label] = round(available - take, 6)

        if need - take > EPSILON:
            missing.append({"name": label, "optional": optional})
            shortfalls.append(
                {
                    "name": label,
                    "qty": round(need - take, 4),
                    "unit": unit,
                    "optional": optional,
                }
            )

    normalized_uses = [
        {
            "name": row["name"],
            "qty": _round_qty(row["qty"]),
            "unit": row["unit"],
            "inventory_id": row.get("inventory_id"),
        }
        for row in uses.values()
    ]
    return normalized_uses, missing, shortfalls


def _score(
    recipe: dict,
    remaining: dict[str, float],
    expiring: set[str],
    used_count: int,
    same_as_prev: bool,
    servings: int,
) -> float:
    expiring_cov = 0
    stocked_cov = 0
    missing_required = 0
    for ingredient in recipe.get("ingredients", []):
        name = _norm(ingredient.get("name"))
        if not name:
            continue
        key = _match_stock(name, list(remaining))
        available = float(remaining.get(key, 0.0)) if key else 0.0
        if available <= EPSILON:
            if not ingredient.get("optional"):
                missing_required += 1
            continue
        if key in expiring:
            expiring_cov += 1
        else:
            stocked_cov += 1

    if expiring_cov + stocked_cov == 0:  # 一道菜一点库存都用不上 → 不排
        return float("-inf")

    return (
        SCORE_EXPIRING * expiring_cov
        + SCORE_STOCKED * stocked_cov
        - PENALTY_MISSING * missing_required
        - PENALTY_MINUTES * float(recipe.get("minutes") or 0)
        - PENALTY_REPEAT_RECIPE * used_count
        - (PENALTY_SAME_AS_PREV if same_as_prev else 0.0)
        + SCORE_RELEVANCE * float(recipe.get("rel") or 0.0)
    )


def _greedy_assignments(
    candidates: list[dict],
    snapshot: dict,
    day_count: int,
    servings: int,
) -> list[dict]:
    """按到期顺序 + BM25 命中贪心分配（同步扣减库存，超量自动转缺料）。"""
    stock = snapshot["stock"]
    remaining = {name: float(row.get("qty") or 0.0) for name, row in stock.items()}
    assignments: list[dict] = []
    used_count: dict[str, int] = {}
    previous_id: str | None = None

    for day in range(1, day_count + 1):
        for slot in MEAL_SLOTS:
            best: dict | None = None
            best_score = float("-inf")
            for candidate in candidates:
                score = _score(
                    candidate,
                    remaining,
                    snapshot["expiring"],
                    used_count.get(candidate["recipe_id"], 0),
                    candidate["recipe_id"] == previous_id,
                    servings,
                )
                if score > best_score:
                    best, best_score = candidate, score
            if best is None:
                break
            assignments.append({"day": day, "slot": slot, "recipe_id": best["recipe_id"]})
            used_count[best["recipe_id"]] = used_count.get(best["recipe_id"], 0) + 1
            previous_id = best["recipe_id"]
            _deduct(best, remaining, stock, servings)
    return assignments


def _citations(recipe: dict) -> list[dict]:
    """每餐挂真实引用，带原文摘录（前端角标要弹原文，契约 §8）。"""
    if recipe.get("source"):
        return [
            citation_utils.make(
                recipe["source"], recipe.get("locator") or "全文", recipe.get("body")
            )
        ]
    return []


def _template_reason(meal: dict) -> str:
    used = "、".join(row["name"] for row in meal["uses"]) or "现有食材"
    required = [row["name"] for row in meal["missing"] if not row.get("optional")]
    tail = f"，还需补{'、'.join(required[:2])}" if required else "，不用额外采购"
    return f"用掉{used}，{meal['minutes']} 分钟可完成{tail}。"


def _materialize(
    assignments: list[dict],
    candidates_by_id: dict[str, dict],
    snapshot: dict,
    servings: int,
    start_date: date,
    day_count: int,
) -> dict:
    """按顺序落成 days / shopping / coverage（库存逐餐扣减，超量转缺料）。"""
    stock = snapshot["stock"]
    remaining = {name: float(row.get("qty") or 0.0) for name, row in stock.items()}
    by_day: dict[int, list[dict]] = {day: [] for day in range(1, day_count + 1)}
    meals: list[dict] = []

    for assignment in assignments:
        recipe = candidates_by_id.get(assignment["recipe_id"])
        if recipe is None:
            continue
        uses, missing, shortfalls = _deduct(recipe, remaining, stock, servings)
        meal = {
            "slot": assignment.get("slot") or MEAL_SLOTS[0],
            "recipe_id": recipe["recipe_id"],
            "title": recipe["title"],
            "minutes": int(recipe.get("minutes") or 0),
            "uses": uses,
            "missing": missing,
            "citations": _citations(recipe),
            "reason": _norm(assignment.get("reason")) or "",
        }
        if not meal["reason"]:
            meal["reason"] = _template_reason(meal)
        meals.append({**meal, "_shortfalls": shortfalls, "_day": int(assignment["day"])})
        by_day.setdefault(int(assignment["day"]), []).append(meal)

    days: list[dict] = []
    for day in range(1, day_count + 1):
        day_meals = by_day.get(day, [])
        slot_order = {slot: index for index, slot in enumerate(MEAL_SLOTS)}
        day_meals.sort(key=lambda row: slot_order.get(row["slot"], 99))
        days.append(
            {
                "date": (start_date + timedelta(days=day - 1)).isoformat(),
                "meals": day_meals,
            }
        )

    shopping = _build_shopping(meals, stock)
    coverage = _coverage(days, snapshot)
    return {"days": days, "shopping": shopping, "coverage": coverage, "meals": meals}


def _build_shopping(meals: list[dict], stock: dict[str, dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for meal in meals:
        for shortfall in meal.get("_shortfalls", []):
            entry = merged.setdefault(
                shortfall["name"],
                {
                    "name": shortfall["name"],
                    "qty": 0.0,
                    "unit": shortfall["unit"],
                    "optional": True,
                    "_meals": 0,
                },
            )
            entry["qty"] += float(shortfall["qty"])
            entry["_meals"] += 1
            entry["optional"] = entry["optional"] and bool(shortfall["optional"])

    shopping: list[dict] = []
    for entry in merged.values():
        if entry["optional"]:
            continue  # 可选调味料不进采购清单，只列必买
        initial = float((stock.get(entry["name"]) or {}).get("qty") or 0.0)
        if initial > EPSILON:
            reason = f"{entry['_meals']} 道菜需要，库存只剩 {_round_qty(initial)}{entry['unit']}"
        else:
            reason = f"{entry['_meals']} 道菜需要，库存没有"
        shopping.append(
            {
                "name": entry["name"],
                "qty": _round_qty(entry["qty"]),
                "unit": entry["unit"],
                "reason": reason,
                "optional": False,
            }
        )
    shopping.sort(key=lambda row: -float(row["qty"]))
    return shopping


def _coverage(days: list[dict], snapshot: dict) -> dict:
    used = {row["name"] for day in days for meal in day["meals"] for row in meal["uses"]}
    expiring = set(snapshot["expiring"])
    expiring_used = used & expiring
    return {
        "used_items": len(used),
        "expiring_used": len(expiring_used),
        "unused_expiring": len(expiring - used),
    }


# --------------------------------------------------------------------------- #
# verify：独立复算，不信任 materialize 的结果
# --------------------------------------------------------------------------- #

def _recipe_ids() -> set[str]:
    conn = get_conn()
    try:
        return {row["id"] for row in conn.execute("SELECT id FROM recipes").fetchall()}
    finally:
        conn.close()


def _hits_blocked(name: str, blocked: set[str] | None) -> bool:
    if not blocked or not name:
        return False
    return _match_stock(name, list(blocked)) is not None


def _recipe_blocked(recipe: dict, blocked: set[str] | None) -> bool:
    """菜谱里有忌口食材（含可选配料）就整道排除。"""
    if not blocked:
        return False
    return any(
        _hits_blocked(_norm(ingredient.get("name")), blocked)
        for ingredient in recipe.get("ingredients", [])
    )


def verify(
    days: list[dict],
    shopping: list[dict],
    snapshot: dict,
    *,
    blocked: set[str] | None = None,
) -> tuple[dict, list[str]]:
    """执行契约 §6.8 的 5 条规则（+ 偏好忌口硬约束），返回 (coverage, problems)。"""
    problems: list[str] = []
    stock = snapshot["stock"]
    expired_names = {item["name"] for item in snapshot["expired"]}
    known_recipes = _recipe_ids()
    totals: dict[str, float] = {}

    meal_count = 0
    for day in days:
        if not day.get("meals"):
            # 模型经常只排第一天就收工，空着的一天等于没做
            problems.append(f"第 {day['date']} 没有任何餐次")
        for meal in day["meals"]:
            meal_count += 1
            recipe_id = str(meal.get("recipe_id") or "")
            if not recipe_id or recipe_id not in known_recipes:
                problems.append(f"第 {day['date']} 的 {meal.get('slot')} 没挂真实 recipe_id")
            if not meal.get("citations"):
                problems.append(f"第 {day['date']} 的 {meal.get('slot')} 缺 citations")
            for use in meal.get("uses", []):
                if use["name"] in expired_names:
                    problems.append(f"过期食材「{use['name']}」进了计划")
                if _hits_blocked(use["name"], blocked):
                    problems.append(f"忌口食材「{use['name']}」进了计划")
                totals[use["name"]] = totals.get(use["name"], 0.0) + float(use["qty"])
            for missing in meal.get("missing", []):
                if _hits_blocked(missing["name"], blocked):
                    problems.append(f"忌口食材「{missing['name']}」被列进菜谱")

    for name, total in totals.items():
        row = stock.get(name)
        if row is None:
            problems.append(f"「{name}」不在可用库存里")
            continue
        if total > float(row.get("qty") or 0.0) + EPSILON:
            problems.append(
                f"「{name}」累计用量 {round(total, 2)} 超过库存 {row.get('qty')}"
            )

    coverage = _coverage(days, snapshot)
    unused_expiring = {
        name for name in snapshot["expiring"] - {
            row["name"] for day in days for meal in day["meals"] for row in meal["uses"]
        }
        if not _hits_blocked(name, blocked)  # 忌口食材本来就不该用，不算「没优先消耗」
    }
    if meal_count > 0 and unused_expiring and coverage["expiring_used"] == 0:
        problems.append("有临期食材却一道都没用上，未体现优先消耗")

    names = [row["name"] for row in shopping]
    if len(names) != len(set(names)):
        problems.append("购物清单有重复食材")
    shopping_names = set(names)
    for day in days:
        for meal in day["meals"]:
            for missing in meal.get("missing", []):
                if missing.get("optional"):
                    continue  # 可选调味料不进采购清单（契约 §6.8 规则 5 只约束必买）
                if missing["name"] not in shopping_names:
                    problems.append(f"缺料「{missing['name']}」没进购物清单")

    return coverage, problems


# --------------------------------------------------------------------------- #
# Prompt
# --------------------------------------------------------------------------- #

def _understand_messages(days: int, servings: int, max_minutes: int) -> list[dict]:
    user = (
        f"用户要 {days} 天配餐，{servings} 人份，单餐不超过 {max_minutes} 分钟。\n"
        '请输出 JSON：{"days": 整数, "servings": 整数, "max_minutes": 整数, "note": 一句话}'
    )
    return [
        {"role": "system", "content": UNDERSTAND_SYSTEM},
        {"role": "user", "content": user},
    ]


def _compose_messages(
    candidates: list[dict],
    snapshot: dict,
    day_count: int,
    servings: int,
    hint: str | None = None,
    preference_lines: list[str] | None = None,
) -> list[dict]:
    stock_lines = [
        f"- {item['name']}：{item['qty']}{item.get('unit') or ''}，{item['days_left']} 天后到期"
        for item in snapshot["usable"]
    ]
    recipe_lines = [
        f"- recipe_id={cand['recipe_id']}｜{cand['title']}｜{cand['minutes']} 分钟｜引用："
        f"{cand['source']} {cand['locator']}"
        for cand in candidates
    ]
    slots = "/".join(MEAL_SLOTS)
    sections = [
        "可用库存（按到期排序，已剔除过期）：",
        *(stock_lines or ["- （空）"]),
        "",
    ]
    if preference_lines:
        sections += ["用户偏好（忌口是硬性要求）：", *preference_lines, ""]
    sections += [
        "候选菜谱（只能从这些里选，recipe_id 原样使用）：",
        *(recipe_lines or ["- （空）"]),
        "",
        f"分配 {day_count} 天 × {len(MEAL_SLOTS)} 餐（槽位只能是 {slots}），{servings} 人份。",
        "同一食材跨餐累计用量不能超过库存；缺的料会被汇总进购物清单。",
        '输出 JSON：{"meals":[{"day":1,"slot":"午餐","recipe_id":"...","reason":"一句话中文理由"}]}',
    ]
    user = "\n".join(sections)
    if hint:
        user += f"\n上次方案未通过校验：{hint}。请修正后重新给出完整方案。"
    return [
        {"role": "system", "content": COMPOSE_SYSTEM},
        {"role": "user", "content": user},
    ]


def _parse_compose(
    data: Any, candidates: list[dict], day_count: int
) -> list[dict] | None:
    """兼容 {"meals": [...]} 与 {"recommendations": [...]} 两种形态。"""
    if not isinstance(data, dict):
        return None
    known = {cand["recipe_id"] for cand in candidates}
    slots = list(MEAL_SLOTS)
    requested = day_count * len(slots)

    rows = data.get("meals")
    if not isinstance(rows, list):
        rows = data.get("recommendations")
    if not isinstance(rows, list) or not rows:
        return None

    assignments: list[dict] = []
    seen_slots: set[tuple[int, str]] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        recipe_id = _norm(row.get("recipe_id"))
        if recipe_id not in known:
            continue
        day = int(row.get("day") or (index // len(slots) + 1))
        slot = _norm(row.get("slot")) or slots[index % len(slots)]
        if slot not in slots:
            slot = slots[index % len(slots)]
        if not 1 <= day <= day_count:
            continue
        if (day, slot) in seen_slots:
            continue
        seen_slots.add((day, slot))
        assignments.append(
            {"day": day, "slot": slot, "recipe_id": recipe_id, "reason": _norm(row.get("reason"))}
        )
        if len(assignments) >= requested:
            break
    return assignments or None


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #

def _empty_plan(plan_id: str, run_id: str, warnings: list[str]) -> dict:
    return {
        "plan_id": plan_id,
        "run_id": run_id,
        "days": [],
        "shopping": [],
        "coverage": {"used_items": 0, "expiring_used": 0, "unused_expiring": 0},
        "warnings": warnings,
    }


def _persist_event(plan_id: str, run_id: str, payload: dict) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO events(id,kind,payload,created_at) VALUES(?,?,?,?)",
            (
                f"ev_{uuid.uuid4().hex[:12]}",
                EVENT_KIND,
                json.dumps({"plan_id": plan_id, "run_id": run_id, **payload}, ensure_ascii=False),
                now_iso(),
            ),
        )
        conn.commit()
    except Exception:
        logger.exception("饮食计划事件写入失败（不影响响应）")
    finally:
        conn.close()


def _save_plan(plan: dict, params: dict) -> None:
    """存档计划（契约 §6.10 meal_plans）：revise 要能读回原计划。"""
    timestamp = now_iso()
    payload = {**plan, "params": params}
    ensure_schema()
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO meal_plans(id,payload,created_at,updated_at) VALUES(?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at",
            (plan["plan_id"], json.dumps(payload, ensure_ascii=False), timestamp, timestamp),
        )
        conn.commit()
    except Exception:
        logger.exception("饮食计划存档失败（不影响本次响应）：%s", plan.get("plan_id"))
    finally:
        conn.close()


def load_plan(plan_id: str) -> dict:
    """读回存档计划；不存在抛 404（revise 的数据源）。"""
    ensure_schema()
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT payload FROM meal_plans WHERE id = ?", (plan_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise AppError("plan_not_found", f"没有找到这份计划（可能已过期或未生成）：{plan_id}", 404)
    try:
        data = json.loads(row["payload"] or "{}")
    except json.JSONDecodeError as exc:
        logger.error("计划存档损坏：%s", plan_id)
        raise AppError("plan_corrupted", "计划存档损坏，请重新生成", 500) from exc
    if not isinstance(data, dict):
        raise AppError("plan_corrupted", "计划存档损坏，请重新生成", 500)
    return data


async def build_plan(
    days: int = DEFAULT_DAYS,
    servings: int = DEFAULT_SERVINGS,
    max_minutes: int = DEFAULT_MAX_MINUTES,
    *,
    provider=None,
) -> dict:
    day_count = max(1, min(int(days or DEFAULT_DAYS), MAX_DAYS))
    servings = max(1, min(int(servings or DEFAULT_SERVINGS), 8))
    max_minutes = max(1, min(int(max_minutes or DEFAULT_MAX_MINUTES), 240))

    plan_id = _new_plan_id()
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    trace = _Trace()
    warnings: list[str] = []
    state = STATE_OK
    start_date = date.today() + timedelta(days=1)

    _persist_run(run_id, STATE_RUNNING, trace.steps)
    llm = resolve_provider(provider)
    tools_registry.register_all()

    try:
        # ---- 1 understand ----
        watch = _Stopwatch()
        if llm is None:
            trace.add(STEP_UNDERSTAND, STATE_DEGRADED, watch, "无可用模型，按输入参数执行")
            warnings.append("已降级：模型不可用，人数与时间按输入参数执行")
        else:
            try:
                data = await llm.chat_json(_understand_messages(day_count, servings, max_minutes))
                if isinstance(data, dict):
                    day_count = max(1, min(int(data.get("days") or day_count), MAX_DAYS))
                    servings = max(1, min(int(data.get("servings") or servings), 8))
                    max_minutes = max(1, min(int(data.get("max_minutes") or max_minutes), 240))
                trace.add(
                    STEP_UNDERSTAND,
                    STATE_OK,
                    watch,
                    f"{day_count} 天 × {len(MEAL_SLOTS)} 餐，{servings} 人份，单餐 ≤{max_minutes} 分钟",
                )
            except Exception as exc:
                logger.warning("计划 understand 失败，按输入参数继续：%s", exc)
                trace.add(STEP_UNDERSTAND, STATE_DEGRADED, watch, "解析失败，按输入参数执行")
                warnings.append("已降级：意图解析失败，按输入参数执行")

        # ---- 2 plan：取库存、剔除过期 ----
        watch = _Stopwatch()
        try:
            planned = await _invoke_tool(
                "list_inventory",
                {"sort": "expiry", "limit": PLAN_TOP_K},
                tools_registry.list_inventory,
            )
        except Exception as exc:
            trace.add(STEP_PLAN, "error", watch, "库存读取失败")
            _persist_run(run_id, STATE_FAILED, trace.steps)
            raise AppError("plan_failed", "读取库存失败，请稍后重试", 500, str(exc)) from exc

        snapshot = _split_inventory(planned.get("items", []))
        warnings.extend(_expired_warnings(snapshot))

        # ---- 偏好注入（契约 §6.10）：avoid 是硬约束，其余进 Prompt 软约束 ----
        prefs = preference_store.active_preferences()
        preference_lines = preference_store.prompt_lines(prefs)
        warnings.extend(preference_store.warnings_for_low_confidence())
        blocked = preference_store.blocked_names(
            [item["name"] for item in snapshot["usable"]], prefs=prefs
        )

        trace.add(
            STEP_PLAN,
            STATE_OK,
            watch,
            f"可用 {len(snapshot['usable'])} 项、临期 {len(snapshot['expiring'])} 项、"
            f"过期 {len(snapshot['expired'])} 项（已排除）",
        )

        if not snapshot["usable"]:
            trace.add(STEP_ALLOCATE, "empty", _Stopwatch(), "没有可用食材")
            trace.add(STEP_COMPOSE, "skipped", _Stopwatch(), "无可用食材，跳过配餐")
            trace.add(STEP_VERIFY, "skipped", _Stopwatch(), "空计划无需校验")
            warnings.append(EMPTY_INVENTORY_WARNING)
            _persist_run(run_id, STATE_DEGRADED, trace.steps)
            _persist_event(plan_id, run_id, {"state": STATE_DEGRADED, "meals": 0})
            empty = _empty_plan(plan_id, run_id, warnings)
            _save_plan(empty, {"days": day_count, "servings": servings, "max_minutes": max_minutes})
            return empty

        # ---- 3 allocate：检索候选 + 贪心草案 ----
        watch = _Stopwatch()
        names = [item["name"] for item in snapshot["usable"]]
        found = await _invoke_tool(
            "find_recipes",
            {"ingredients": names, "max_minutes": max_minutes, "limit": CANDIDATE_POOL},
            tools_registry.find_recipes,
        )
        candidates = [
            item
            for item in found.get("items", [])
            if int(item.get("steps_count") or 0) >= MIN_RECIPE_STEPS
        ]
        if blocked:
            # 候选菜谱里的配料名也纳入词表，避免「菜谱里有鸡蛋但库存没有」被漏掉
            recipe_names = [
                _norm(ingredient.get("name"))
                for item in candidates
                for ingredient in item.get("ingredients", [])
            ]
            blocked |= preference_store.blocked_names(recipe_names, prefs=prefs)
            candidates = [item for item in candidates if not _recipe_blocked(item, blocked)]
            warnings.append(
                PREFERENCE_EXCLUDED_TEMPLATE.format(names="、".join(sorted(blocked)))
            )
        if not candidates:
            trace.add(STEP_ALLOCATE, "empty", watch, "候选菜谱为空")
            trace.add(STEP_COMPOSE, "skipped", _Stopwatch(), "无候选，跳过配餐")
            trace.add(STEP_VERIFY, "skipped", _Stopwatch(), "空计划无需校验")
            warnings.append(
                ALL_BLOCKED_WARNING.format(names="、".join(sorted(blocked)))
                if blocked
                else NO_RECIPE_WARNING
            )
            _persist_run(run_id, STATE_DEGRADED, trace.steps)
            _persist_event(plan_id, run_id, {"state": STATE_DEGRADED, "meals": 0})
            empty = _empty_plan(plan_id, run_id, warnings)
            _save_plan(empty, {"days": day_count, "servings": servings, "max_minutes": max_minutes})
            return empty

        candidates_by_id = {item["recipe_id"]: item for item in candidates}
        greedy = _greedy_assignments(candidates, snapshot, day_count, servings)
        trace.add(
            STEP_ALLOCATE,
            STATE_OK,
            watch,
            f"候选 {len(candidates)} 道，贪心排出 {len(greedy)} 餐（临期优先）",
        )

        # ---- 4 compose：模型可选，失败即用贪心 ----
        watch = _Stopwatch()
        assignments = None
        degraded = False
        if llm is not None:
            try:
                data = await llm.chat_json(
                    _compose_messages(
                        candidates, snapshot, day_count, servings,
                        preference_lines=preference_lines,
                    )
                )
                assignments = _parse_compose(data, candidates, day_count)
            except Exception as exc:
                logger.warning("计划 compose 失败：%s", exc)

        if not assignments:
            assignments = greedy
            degraded = True
            warnings.append(DEGRADE_WARNING)
            trace.add(STEP_COMPOSE, STATE_DEGRADED, watch, "模型不可用，按检索结果贪心配餐")
        else:
            trace.add(
                STEP_COMPOSE,
                STATE_OK,
                watch,
                f"模型给出 {len(assignments)} 餐，理由与引用已对齐菜谱库",
            )

        built = _materialize(
            assignments, candidates_by_id, snapshot, servings, start_date, day_count
        )

        # ---- 5 verify：五条规则 + 忌口硬约束，独立复算 ----
        watch = _Stopwatch()
        coverage, problems = verify(built["days"], built["shopping"], snapshot, blocked=blocked)

        if problems and llm is not None and not degraded:
            hint = "；".join(problems[:3])
            logger.info("饮食计划 verify 未通过，重试一次：%s", hint)
            try:
                data = await llm.chat_json(
                    _compose_messages(
                        candidates, snapshot, day_count, servings, hint,
                        preference_lines=preference_lines,
                    )
                )
                retry_assignments = _parse_compose(data, candidates, day_count)
            except Exception as exc:
                logger.warning("计划 compose 重试失败：%s", exc)
                retry_assignments = None
            if retry_assignments:
                built = _materialize(
                    retry_assignments, candidates_by_id, snapshot, servings, start_date, day_count
                )
                coverage, problems = verify(
                    built["days"], built["shopping"], snapshot, blocked=blocked
                )

        if problems:
            # 规则版兜底：必然满足用量/引用约束
            built = _materialize(greedy, candidates_by_id, snapshot, servings, start_date, day_count)
            coverage, problems = verify(
                built["days"], built["shopping"], snapshot, blocked=blocked
            )
            degraded = True
            if DEGRADE_WARNING not in warnings:
                warnings.append(DEGRADE_WARNING)

        if problems:
            # 仍不通过：剔除坏餐（真实 recipe_id / citations 缺失），再复算一次
            valid_ids = _recipe_ids()
            filtered = [
                assignment
                for assignment in greedy
                if assignment["recipe_id"] in candidates_by_id
                and assignment["recipe_id"] in valid_ids
            ]
            built = _materialize(
                filtered, candidates_by_id, snapshot, servings, start_date, day_count
            )
            coverage, problems = verify(
                built["days"], built["shopping"], snapshot, blocked=blocked
            )
            degraded = True
            logger.warning("饮食计划兜底后仍有校验问题：%s", problems)

        meals_count = sum(len(day["meals"]) for day in built["days"])
        unused = [
            item for item in snapshot["usable"] if item["name"] not in {
                row["name"] for day in built["days"] for meal in day["meals"] for row in meal["uses"]
            }
        ]
        for item in unused:
            if item["name"] in snapshot["expiring"]:
                warnings.append(
                    UNUSED_EXPIRING_TEMPLATE.format(name=item["name"], days=item["days_left"])
                )
        if problems:
            warnings.append("校验仍有未消除的问题：" + "；".join(problems[:2]))

        state = STATE_DEGRADED if (degraded or problems) else STATE_OK
        trace.add(
            STEP_VERIFY,
            STATE_OK if not problems else STATE_DEGRADED,
            watch,
            f"5 条规则校验：{len(problems)} 个问题，"
            f"用掉 {coverage['used_items']} 项（临期 {coverage['expiring_used']} 项）",
        )
        _persist_run(run_id, state, trace.steps)
        _persist_event(
            plan_id,
            run_id,
            {"state": state, "meals": meals_count, "coverage": coverage},
        )

        plan = {
            "plan_id": plan_id,
            "run_id": run_id,
            "days": built["days"],
            "shopping": built["shopping"],
            "coverage": coverage,
            "warnings": warnings,
        }
        _save_plan(plan, {"days": day_count, "servings": servings, "max_minutes": max_minutes})
        return plan

    except AppError:
        raise
    except Exception as exc:
        logger.exception("饮食计划流水线异常")
        _persist_run(run_id, STATE_FAILED, trace.steps)
        raise AppError("meal_plan_failed", "饮食计划生成失败，请稍后重试", 500, str(exc)) from exc


# --------------------------------------------------------------------------- #
# 对话改计划（契约 §6.9）
# --------------------------------------------------------------------------- #

class ReviseIntent(BaseModel):
    """指令解析的结构化输出（契约 §7：schema 校验，失败重试后降级到规则版）。"""

    days: list[int] = Field(default_factory=list, description="要改第几天，从 1 开始")
    slots: list[str] = Field(default_factory=list, description="要改哪几餐，空=当天全部")
    avoid: list[str] = Field(default_factory=list, description="不要的食材")
    requested: list[str] = Field(default_factory=list, description="点名想吃的食材")
    light: bool = Field(default=False, description="是否要清淡少油")
    swap_to: str | None = Field(default=None, description="点名想换成的菜名")


def _revise_messages(instruction: str, day_count: int, vocabulary: list[str]) -> list[dict]:
    # 刻意不提「配餐 / 饮食计划」，避免 mock 回放数据被误判成配餐结果
    user = "\n".join(
        [
            f"用户在一份已有 {day_count} 天的吃饭安排上提了一个修改要求：{instruction}",
            f"可选食材名（avoid 只能从这里取）：{'、'.join(vocabulary[:60]) or '（无）'}",
            '输出 JSON：{"days":[2],"slots":["午餐"],"avoid":["鸡蛋"],"requested":[],'
            '"light":true,"swap_to":null,"note":"一句话"}',
            'days 是第几天（从 1 开始，空数组表示整份安排）；slots 为空表示当天所有餐次；',
            "avoid 只放用户明确不要的食材；light 表示要清淡少油；swap_to 是用户点名想换成的菜名。",
        ]
    )
    return [
        {"role": "system", "content": REVISE_SYSTEM},
        {"role": "user", "content": user},
    ]


def _parse_revise_intent(data: Any) -> dict:
    """把模型输出收口成普通 dict（schema 已校验过，这里只做类型清洗）。"""
    if not isinstance(data, dict):
        return {}
    out: dict[str, Any] = {}
    days = data.get("days")
    if isinstance(days, list):
        out["days"] = [int(day) for day in days if str(day).isdigit()]
    slots = data.get("slots")
    if isinstance(slots, list):
        out["slots"] = [str(slot).strip() for slot in slots if str(slot).strip()]
    avoid = data.get("avoid")
    if isinstance(avoid, list):
        out["avoid"] = [str(name).strip() for name in avoid if str(name).strip()]
    requested = data.get("requested")
    if isinstance(requested, list):
        out["requested"] = [str(name).strip() for name in requested if str(name).strip()]
    if data.get("light"):
        out["light"] = True
    swap_to = str(data.get("swap_to") or "").strip()
    if swap_to:
        out["swap_to"] = swap_to
    return out


def _loads_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _candidate_from_row(row) -> dict:
    """把 recipes 表的一行转成与检索结果同构的候选（未涉及的餐要原样保留）。"""
    from app.rag.index import recipe_chunk

    chunk = recipe_chunk(row)
    ingredients = [row_item for row_item in _loads_list(row["ingredients"]) if isinstance(row_item, dict)]
    steps = _loads_list(row["steps"])
    return {
        "recipe_id": row["id"],
        "title": row["title"],
        "minutes": int(row["minutes"] or 0),
        "servings": int(row["servings"] or 1),
        "ingredients": ingredients,
        "steps_count": len(steps),
        "source": chunk["source"],
        "locator": chunk["locator"],
        "body": chunk["body"],
        "rel": 0.0,
    }


def _load_candidates(recipe_ids: list[str]) -> dict[str, dict]:
    ids = sorted({str(rid) for rid in recipe_ids if rid})
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    conn = get_conn()
    try:
        rows = conn.execute(
            f"SELECT * FROM recipes WHERE id IN ({placeholders})", ids
        ).fetchall()
    finally:
        conn.close()
    return {row["id"]: _candidate_from_row(row) for row in rows}


def _ingredient_vocabulary() -> list[str]:
    """指令解析用的词表：库存名 + 全库菜谱配料名。"""
    conn = get_conn()
    try:
        inventory_names = [
            str(row["name"]).strip()
            for row in conn.execute(
                "SELECT name FROM inventory WHERE status = ?", ("active",)
            ).fetchall()
        ]
        recipe_rows = conn.execute("SELECT ingredients FROM recipes").fetchall()
    finally:
        conn.close()

    names = set(inventory_names)
    for row in recipe_rows:
        for ingredient in _loads_list(row["ingredients"]):
            if isinstance(ingredient, dict):
                name = _norm(ingredient.get("name"))
                if name:
                    names.add(name)
    return sorted(names, key=len, reverse=True)


def _light_score(recipe: dict) -> float:
    text = str(recipe.get("title") or "") + " " + " ".join(
        _norm(ingredient.get("name")) for ingredient in recipe.get("ingredients", [])
    )
    score = 0.0
    score += sum(1.0 for keyword in LIGHT_KEYWORDS if keyword in text)
    score -= REVISE_HEAVY_PENALTY * sum(
        1.0 for keyword in HEAVY_KEYWORDS if keyword in text
    )
    return score


def _target_keys(days: list[dict], intent: dict) -> set[tuple[str, str]]:
    """指令点名了哪天/哪餐 → 精确目标；什么都没点名 → 空集（由调用方展开）。"""
    day_indexes = [int(day) for day in intent.get("days") or []]
    slot_names = [slot for slot in intent.get("slots") or [] if slot in MEAL_SLOTS]
    targets: set[tuple[str, str]] = set()

    selected_days = [
        days[index - 1] for index in day_indexes if 1 <= index <= len(days)
    ]
    if not selected_days:
        selected_days = days if slot_names else []

    for day in selected_days:
        for meal in day.get("meals", []):
            if slot_names and meal.get("slot") not in slot_names:
                continue
            targets.add((str(day["date"]), str(meal.get("slot"))))
    return targets


def _scope_label(date_text: str, slot: str) -> str:
    return REVISE_SCOPE_TEMPLATE.format(date=date_text, slot=slot)


def _pick_for_revise(
    candidates: list[dict],
    remaining: dict[str, float],
    snapshot: dict,
    servings: int,
    used_count: dict[str, int],
    previous_id: str | None,
    intent: dict,
    blocked: set[str],
    current_id: str,
    max_minutes: int,
) -> dict | None:
    """挑一道替换菜谱：先排除「和原来一样」，实在没有才允许保留。"""

    def evaluate(allow_same: bool, allow_empty_stock: bool) -> dict | None:
        best: dict | None = None
        best_score = float("-inf")
        for candidate in candidates:
            recipe_id = candidate["recipe_id"]
            if not allow_same and recipe_id == current_id:
                continue
            if _recipe_blocked(candidate, blocked):
                continue
            if max_minutes and int(candidate.get("minutes") or 0) > max_minutes:
                continue
            score = _score(
                candidate,
                remaining,
                snapshot["expiring"],
                used_count.get(recipe_id, 0),
                recipe_id == previous_id,
                servings,
            )
            if score == float("-inf"):
                if not allow_empty_stock:
                    continue
                # 忌口/点名要求必须换，但库存已被排完：允许排一道「全缺料」的菜进购物清单
                score = 0.0
            if intent.get("light"):
                score += REVISE_LIGHT_BONUS * _light_score(candidate)
            swap_to = intent.get("swap_to")
            if swap_to and swap_to in str(candidate.get("title") or ""):
                score += REVISE_SWAP_BONUS
            if recipe_id == current_id:
                score -= REVISE_SAME_RECIPE_PENALTY
            if score > best_score:
                best, best_score = candidate, score
        return best

    return (
        evaluate(allow_same=False, allow_empty_stock=False)
        or evaluate(allow_same=True, allow_empty_stock=False)
        or evaluate(allow_same=False, allow_empty_stock=True)
        or evaluate(allow_same=True, allow_empty_stock=True)
    )


def _satisfies(recipe: dict, intent: dict, blocked: set[str]) -> bool:
    """被点名的餐如果本来就满足这次指令，就不要为了改而改。"""
    if recipe is None or _recipe_blocked(recipe, blocked):
        return False
    if intent.get("light") and _light_score(recipe) <= 0:
        return False
    swap_to = str(intent.get("swap_to") or "")
    if swap_to and swap_to not in str(recipe.get("title") or ""):
        return False
    requested = intent.get("requested") or []
    if requested:
        haystack = str(recipe.get("title") or "") + " " + str(recipe.get("body") or "") + " " + " ".join(
            _norm(ingredient.get("name")) for ingredient in recipe.get("ingredients", [])
        )
        if not any(name in haystack for name in requested):
            return False
    return True


def _revise_assignments(
    days: list[dict],
    targets: set[tuple[str, str]],
    candidates: list[dict],
    fixed_by_id: dict[str, dict],
    snapshot: dict,
    servings: int,
    intent: dict,
    blocked: set[str],
    max_minutes: int,
) -> tuple[list[dict] | None, str | None]:
    """按天/餐顺序重排：只有 targets 或触犯忌口的餐换菜，其余原样保留。"""
    stock = snapshot["stock"]
    remaining = {name: float(row.get("qty") or 0.0) for name, row in stock.items()}
    used_count: dict[str, int] = {}
    previous_id: str | None = None
    assignments: list[dict] = []

    for day_index, day in enumerate(days, start=1):
        for meal in day.get("meals", []):
            recipe_id = str(meal.get("recipe_id") or "")
            recipe = fixed_by_id.get(recipe_id)
            key = (str(day["date"]), str(meal.get("slot")))
            must_change = recipe is None or _recipe_blocked(recipe, blocked)
            if not must_change and key in targets:
                must_change = not _satisfies(recipe, intent, blocked)

            if not must_change:
                assignments.append(
                    {"day": day_index, "slot": meal.get("slot"), "recipe_id": recipe_id}
                )
                used_count[recipe_id] = used_count.get(recipe_id, 0) + 1
                previous_id = recipe_id
                _deduct(recipe, remaining, stock, servings)
                continue

            replacement = _pick_for_revise(
                candidates,
                remaining,
                snapshot,
                servings,
                used_count,
                previous_id,
                intent,
                blocked,
                recipe_id,
                max_minutes,
            )
            if replacement is None:
                return None, _scope_label(key[0], key[1])

            assignments.append(
                {
                    "day": day_index,
                    "slot": meal.get("slot"),
                    "recipe_id": replacement["recipe_id"],
                }
            )
            used_count[replacement["recipe_id"]] = (
                used_count.get(replacement["recipe_id"], 0) + 1
            )
            previous_id = replacement["recipe_id"]
            _deduct(replacement, remaining, stock, servings)

    return assignments, None


def _diff_days(old_days: list[dict], new_days: list[dict]) -> list[dict]:
    """前后计划逐餐对比（按 date + slot 对齐），保证 changed 与两份计划对得上。"""
    old_map = {
        (str(day["date"]), str(meal.get("slot"))): meal
        for day in old_days
        for meal in day.get("meals", [])
    }
    new_map = {
        (str(day["date"]), str(meal.get("slot"))): meal
        for day in new_days
        for meal in day.get("meals", [])
    }

    changed: list[dict] = []
    for day in new_days:
        for meal in day.get("meals", []):
            key = (str(day["date"]), str(meal.get("slot")))
            previous = old_map.get(key)
            if previous is None or previous.get("recipe_id") != meal.get("recipe_id"):
                changed.append(
                    {
                        "date": key[0],
                        "slot": key[1],
                        "from": previous.get("title") if previous else None,
                        "to": meal.get("title"),
                        "reason": "",
                    }
                )
    for key, previous in old_map.items():
        if key not in new_map:
            changed.append(
                {
                    "date": key[0],
                    "slot": key[1],
                    "from": previous.get("title"),
                    "to": None,
                    "reason": "",
                }
            )
    return changed


def _intent_summary(intent: dict) -> str:
    parts: list[str] = []
    if intent.get("avoid"):
        parts.append("去掉" + "、".join(intent["avoid"]))
    if intent.get("light"):
        parts.append("改清淡少油")
    if intent.get("swap_to"):
        parts.append("换成" + str(intent["swap_to"]))
    if intent.get("requested"):
        parts.append("加入" + "、".join(intent["requested"]))
    return "、".join(parts) or "按你的要求调整"


def _revise_result(
    plan_id: str,
    run_id: str,
    original: dict,
    warnings: list[str],
    changed: list[dict],
    learned: list[dict],
) -> dict:
    return {
        "plan_id": plan_id,
        "run_id": run_id,
        "days": original["days"],
        "shopping": original["shopping"],
        "coverage": original["coverage"],
        "warnings": warnings,
        "changed": changed,
        "learned": learned,
    }


async def revise(plan_id: str, instruction: str, *, provider=None) -> dict:
    """在一份已存档的计划上按对话指令局部重排（契约 §6.9）。"""
    text = " ".join(str(instruction or "").split())[:REVISE_MAX_INSTRUCTION]
    if not text:
        raise AppError(
            "invalid_instruction",
            "请说明要怎么改，例如「第二天想吃清淡点，不要鸡蛋」",
            400,
        )

    stored = load_plan(plan_id)
    original = {
        "days": stored.get("days") or [],
        "shopping": stored.get("shopping") or [],
        "coverage": stored.get("coverage")
        or {"used_items": 0, "expiring_used": 0, "unused_expiring": 0},
    }
    params = stored.get("params") or {}
    servings = max(1, min(int(params.get("servings") or DEFAULT_SERVINGS), 8))
    max_minutes = max(1, min(int(params.get("max_minutes") or DEFAULT_MAX_MINUTES), 240))
    day_count = len(original["days"])

    run_id = f"run_{uuid.uuid4().hex[:12]}"
    trace = _Trace()
    warnings: list[str] = []
    llm = resolve_provider(provider)
    tools_registry.register_all()
    _persist_run(run_id, STATE_RUNNING, trace.steps)

    try:
        # ---- 1 understand：解析指令（LLM + 规则版交叉）----
        watch = _Stopwatch()
        vocabulary = _ingredient_vocabulary()
        rule_intent = instruction_parser.parse_instruction(text, vocabulary)
        intent = rule_intent
        if llm is None:
            warnings.append(REVISE_DEGRADED_WARNING)
            trace.add(STEP_UNDERSTAND, STATE_DEGRADED, watch, "模型不可用，按规则解析指令")
        else:
            try:
                data = await llm.chat_json(
                    _revise_messages(text, day_count, vocabulary), schema=ReviseIntent
                )
                intent = instruction_parser.merge_intents(rule_intent, _parse_revise_intent(data))
                trace.add(STEP_UNDERSTAND, STATE_OK, watch, f"改动意图：{_intent_summary(intent)}")
            except Exception as exc:
                logger.info("改计划指令解析失败，改用规则版：%s", exc)
                trace.add(STEP_UNDERSTAND, STATE_DEGRADED, watch, "解析失败，改用规则版")
                warnings.append(REVISE_DEGRADED_WARNING)

        if day_count == 0:
            for step, note in (
                (STEP_PLAN, "空计划，无需读库存"),
                (STEP_ALLOCATE, "空计划，无需重排"),
                (STEP_COMPOSE, "空计划，无需配餐"),
                (STEP_VERIFY, "空计划无需校验"),
            ):
                trace.add(step, "skipped", _Stopwatch(), note)
            warnings.append(EMPTY_PLAN_REVISE_WARNING)
            _persist_run(run_id, STATE_DEGRADED, trace.steps)
            return _revise_result(plan_id, run_id, original, warnings, [], [])

        requested_days = [int(day) for day in intent.get("days") or []]
        if requested_days and not any(1 <= day <= day_count for day in requested_days):
            for step, note in (
                (STEP_PLAN, "序号越界，未读库存"),
                (STEP_ALLOCATE, "序号越界，未重排"),
                (STEP_COMPOSE, "序号越界，未配餐"),
                (STEP_VERIFY, "没有改动，无需校验"),
            ):
                trace.add(step, "skipped", _Stopwatch(), note)
            warnings.append(
                REVISE_NO_CHANGE_TEMPLATE.format(detail=f"这份计划只有 {day_count} 天")
            )
            _persist_run(run_id, STATE_DEGRADED, trace.steps)
            return _revise_result(plan_id, run_id, original, warnings, [], [])

        # ---- 2 plan：当前库存 + 已记忆偏好 ----
        watch = _Stopwatch()
        planned = await _invoke_tool(
            "list_inventory",
            {"sort": "expiry", "limit": PLAN_TOP_K},
            tools_registry.list_inventory,
        )
        snapshot = _split_inventory(planned.get("items", []))
        warnings.extend(_expired_warnings(snapshot))

        prefs = preference_store.active_preferences()
        warnings.extend(preference_store.warnings_for_low_confidence())
        blocked = preference_store.blocked_names(
            [item["name"] for item in snapshot["usable"]], prefs=prefs
        )

        # 指令与已记忆偏好冲突：本次指令为准（契约 §6.9 规则 2）
        for conflict in preference_store.instruction_conflicts(text, vocabulary, prefs):
            warnings.append(
                REVISE_CONFLICT_TEMPLATE.format(name=conflict["name"], text=conflict["text"])
            )
            blocked.discard(conflict["name"])
        blocked |= {name for name in intent.get("avoid") or [] if name}

        trace.add(
            STEP_PLAN,
            STATE_OK,
            watch,
            f"可用 {len(snapshot['usable'])} 项、忌口 {len(blocked)} 项、过期 {len(snapshot['expired'])} 项",
        )

        # ---- 3 allocate：检索候选（未涉及的餐直接用存档里的菜谱）----
        watch = _Stopwatch()
        names = [item["name"] for item in snapshot["usable"]]
        found = await _invoke_tool(
            "find_recipes",
            {"ingredients": names, "max_minutes": max_minutes, "limit": CANDIDATE_POOL},
            tools_registry.find_recipes,
        )
        candidates = [
            item
            for item in found.get("items", [])
            if int(item.get("steps_count") or 0) >= MIN_RECIPE_STEPS
            and not _recipe_blocked(item, blocked)
        ]
        fixed_by_id = _load_candidates(
            [meal.get("recipe_id") for day in original["days"] for meal in day.get("meals", [])]
        )
        targets = _target_keys(original["days"], intent)
        if not targets and (
            intent.get("avoid") or intent.get("light") or intent.get("swap_to")
        ):
            targets = {
                (str(day["date"]), str(meal.get("slot")))
                for day in original["days"]
                for meal in day.get("meals", [])
            }
        trace.add(
            STEP_ALLOCATE,
            STATE_OK if candidates else "empty",
            watch,
            f"候选 {len(candidates)} 道，需要调整 {len(targets)} 餐",
        )

        # ---- 4 compose：局部重排 ----
        watch = _Stopwatch()
        summary = _intent_summary(intent)
        assignments, failed_scope = _revise_assignments(
            original["days"],
            targets,
            candidates,
            fixed_by_id,
            snapshot,
            servings,
            intent,
            blocked,
            max_minutes,
        )
        if assignments is None:
            trace.add(STEP_COMPOSE, "empty", watch, f"{failed_scope} 没有可用替换菜谱")
            trace.add(STEP_VERIFY, "skipped", _Stopwatch(), "没有改动，无需校验")
            warnings.append(
                REVISE_NO_CANDIDATE_TEMPLATE.format(constraints=summary, scope=failed_scope)
            )
            _persist_run(run_id, STATE_DEGRADED, trace.steps)
            _persist_event(plan_id, run_id, {"state": STATE_DEGRADED, "revised": 0})
            return _revise_result(plan_id, run_id, original, warnings, [], [])

        candidates_by_id = {**fixed_by_id, **{cand["recipe_id"]: cand for cand in candidates}}
        start_date = date.fromisoformat(str(original["days"][0]["date"])[:10])
        built = _materialize(
            assignments, candidates_by_id, snapshot, servings, start_date, day_count
        )
        trace.add(STEP_COMPOSE, STATE_OK, watch, f"局部重排 {len(targets)} 餐（其余原样保留）")

        # ---- 5 verify：改完仍须过 §6.8 五条规则 + 忌口硬约束 ----
        watch = _Stopwatch()
        coverage, problems = verify(
            built["days"], built["shopping"], snapshot, blocked=blocked
        )
        if problems:
            trace.add(STEP_VERIFY, "error", watch, f"{len(problems)} 个问题，本次不落库")
            warnings.append(
                "按你的要求改完之后仍不满足计划规则（"
                + "；".join(problems[:2])
                + "），这次先不改，原计划保持不变"
            )
            _persist_run(run_id, STATE_DEGRADED, trace.steps)
            _persist_event(plan_id, run_id, {"state": STATE_DEGRADED, "revised": 0})
            return _revise_result(plan_id, run_id, original, warnings, [], [])

        changed = _diff_days(original["days"], built["days"])
        if not changed:
            trace.add(STEP_VERIFY, STATE_OK, watch, "无需改动，计划保持原样")
            warnings.append(REVISE_NO_CHANGE_TEMPLATE.format(detail=summary))
            _persist_run(run_id, STATE_DEGRADED, trace.steps)
            _persist_event(plan_id, run_id, {"state": STATE_DEGRADED, "revised": 0})
            return _revise_result(plan_id, run_id, original, warnings, [], [])

        for entry in changed:
            entry["reason"] = summary
        trace.add(
            STEP_VERIFY,
            STATE_OK,
            watch,
            f"5 条规则校验通过，改动 {len(changed)} 餐，"
            f"用掉 {coverage['used_items']} 项（临期 {coverage['expiring_used']} 项）",
        )

        # ---- 学偏好：改成功了才学，失败不影响主流程 ----
        learned = await preference_store.learn_from_instruction(text, llm, vocabulary)
        for row in learned:
            if row["confidence"] < preference_store.MIN_ACTIVE_CONFIDENCE:
                warnings.append(
                    REVISE_LEARNED_LOW_TEMPLATE.format(
                        text=row["text"], confidence=row["confidence"]
                    )
                )

        result = {
            "plan_id": plan_id,
            "run_id": run_id,
            "days": built["days"],
            "shopping": built["shopping"],
            "coverage": coverage,
            "warnings": warnings,
            "changed": changed,
            "learned": learned,
        }
        _save_plan(
            {
                "plan_id": plan_id,
                "run_id": run_id,
                "days": built["days"],
                "shopping": built["shopping"],
                "coverage": coverage,
                "warnings": warnings,
            },
            params,
        )
        state = STATE_DEGRADED if REVISE_DEGRADED_WARNING in warnings else STATE_OK
        _persist_run(run_id, state, trace.steps)
        _persist_event(
            plan_id,
            run_id,
            {"state": state, "revised": len(changed), "coverage": coverage},
        )
        return result

    except AppError:
        raise
    except Exception as exc:
        logger.exception("改计划流水线异常")
        _persist_run(run_id, STATE_FAILED, trace.steps)
        raise AppError("plan_revise_failed", "改计划失败，请稍后重试", 500, str(exc)) from exc
