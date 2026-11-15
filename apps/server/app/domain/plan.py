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

from app.db.conn import get_conn
from app.domain import tools_registry
from app.domain.recipes import (
    _Stopwatch,
    _Trace,
    _invoke_tool,
    resolve_provider,
)
from app.domain.recipes import _persist_run as _persist_recipe_run
from app.domain.tools_registry import AppError

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

UNDERSTAND_SYSTEM = "阶段：understand\n你是「食光」的配餐助手，只输出 JSON。"
COMPOSE_SYSTEM = "阶段：compose\n你是「食光」的配餐助手，只能从给定的菜谱里选，只输出 JSON。"


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
        available = float(remaining.get(key, 0.0)) if key else 0.0
        unit = (stock.get(key) or {}).get("unit") or ingredient.get("unit") or "份"
        take = min(need, available)
        label = key or name

        if take > EPSILON:
            if label in uses:
                uses[label]["qty"] += take
            else:
                uses[label] = {"name": label, "qty": take, "unit": unit}
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
        {"name": row["name"], "qty": _round_qty(row["qty"]), "unit": row["unit"]}
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
    if recipe.get("source"):
        return [{"source": recipe["source"], "locator": recipe.get("locator") or "全文"}]
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
                "optional": entry["optional"],
            }
        )
    shopping.sort(key=lambda row: (row["optional"], -float(row["qty"])))
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


def verify(days: list[dict], shopping: list[dict], snapshot: dict) -> tuple[dict, list[str]]:
    """执行契约 §6.8 的 5 条规则，返回 (coverage, problems)。"""
    problems: list[str] = []
    stock = snapshot["stock"]
    expired_names = {item["name"] for item in snapshot["expired"]}
    known_recipes = _recipe_ids()
    totals: dict[str, float] = {}

    meal_count = 0
    for day in days:
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
                totals[use["name"]] = totals.get(use["name"], 0.0) + float(use["qty"])

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
    if meal_count > 0 and coverage["unused_expiring"] > 0 and coverage["expiring_used"] == 0:
        problems.append("有临期食材却一道都没用上，未体现优先消耗")

    names = [row["name"] for row in shopping]
    if len(names) != len(set(names)):
        problems.append("购物清单有重复食材")
    shopping_names = set(names)
    for day in days:
        for meal in day["meals"]:
            for missing in meal.get("missing", []):
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
    user = "\n".join(
        [
            "可用库存（按到期排序，已剔除过期）：",
            *(stock_lines or ["- （空）"]),
            "",
            "候选菜谱（只能从这些里选，recipe_id 原样使用）：",
            *(recipe_lines or ["- （空）"]),
            "",
            f"分配 {day_count} 天 × {len(MEAL_SLOTS)} 餐（槽位只能是 {slots}），{servings} 人份。",
            "同一食材跨餐累计用量不能超过库存；缺的料会被汇总进购物清单。",
            '输出 JSON：{"meals":[{"day":1,"slot":"午餐","recipe_id":"...","reason":"一句话中文理由"}]}',
        ]
    )
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
    from app.domain.inventory import now_iso

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
            return _empty_plan(plan_id, run_id, warnings)

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
        if not candidates:
            trace.add(STEP_ALLOCATE, "empty", watch, "候选菜谱为空")
            trace.add(STEP_COMPOSE, "skipped", _Stopwatch(), "无候选，跳过配餐")
            trace.add(STEP_VERIFY, "skipped", _Stopwatch(), "空计划无需校验")
            warnings.append(NO_RECIPE_WARNING)
            _persist_run(run_id, STATE_DEGRADED, trace.steps)
            _persist_event(plan_id, run_id, {"state": STATE_DEGRADED, "meals": 0})
            return _empty_plan(plan_id, run_id, warnings)

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
                    _compose_messages(candidates, snapshot, day_count, servings)
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

        # ---- 5 verify：五条规则独立复算 ----
        watch = _Stopwatch()
        coverage, problems = verify(built["days"], built["shopping"], snapshot)

        if problems and llm is not None and not degraded:
            hint = "；".join(problems[:3])
            logger.info("饮食计划 verify 未通过，重试一次：%s", hint)
            try:
                data = await llm.chat_json(
                    _compose_messages(candidates, snapshot, day_count, servings, hint)
                )
                retry_assignments = _parse_compose(data, candidates, day_count)
            except Exception as exc:
                logger.warning("计划 compose 重试失败：%s", exc)
                retry_assignments = None
            if retry_assignments:
                built = _materialize(
                    retry_assignments, candidates_by_id, snapshot, servings, start_date, day_count
                )
                coverage, problems = verify(built["days"], built["shopping"], snapshot)

        if problems:
            # 规则版兜底：必然满足用量/引用约束
            built = _materialize(greedy, candidates_by_id, snapshot, servings, start_date, day_count)
            coverage, problems = verify(built["days"], built["shopping"], snapshot)
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
            coverage, problems = verify(built["days"], built["shopping"], snapshot)
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

        return {
            "plan_id": plan_id,
            "run_id": run_id,
            "days": built["days"],
            "shopping": built["shopping"],
            "coverage": coverage,
            "warnings": warnings,
        }

    except AppError:
        raise
    except Exception as exc:
        logger.exception("饮食计划流水线异常")
        _persist_run(run_id, STATE_FAILED, trace.steps)
        raise AppError("meal_plan_failed", "饮食计划生成失败，请稍后重试", 500, str(exc)) from exc
