"""备菜流水线（契约 §6.12）：多道菜合并成一条带并行关系的时间轴。

- 从 `recipes` 表取真实 `steps`，交给 LLM 合并排序；每条输出必须带
  `source: recipe:<id>` 与 `locator: 步骤 n`，verify 会独立复算来源与总时长
- 模型不可用 / 输出不过校验：按「预处理（切/洗/腌）优先、长耗时先起锅」规则版排序，
  总时长 = 预处理耗时 + 最长单菜耗时，并在 `warnings` 标「已降级」
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any

from app.db.conn import get_conn
from app.domain.tools_registry import AppError, resolve_provider

logger = logging.getLogger(__name__)

MAX_RECIPES = 6
MAX_STEPS = 40
MAX_TIPS = 3
MAX_STEP_MINUTES = 240
MIN_MINUTES = 1
PREP_STEP_MINUTES = 2
LLM_ATTEMPTS = 2
DEFAULT_START_AT = "18:30"
MINUTES_PER_DAY = 24 * 60

PREP_KEYWORDS: tuple[str, ...] = (
    "切",
    "洗",
    "腌",
    "泡",
    "解冻",
    "剁",
    "摘",
    "剥",
    "掰",
    "淘",
    "焯",
    "沥",
)

DEGRADE_WARNING = "已降级：模型不可用或输出未通过校验，本次按「预处理优先 + 长耗时先起锅」规则排序"
VERIFY_WARNING = "校验仍有未消除的问题：{detail}"
BAD_START_WARNING = "开始时间「{raw}」格式应为 HH:MM，本次按 {fallback} 排"
CROSS_DAY_WARNING = "预计结束时间超过 23:59，时间轴会跨到第二天"
SKIP_RECIPE_WARNING = "菜谱「{title}」没有可执行的步骤，已跳过"
MISSING_STEPS_MESSAGE = "所选菜谱都没有步骤，无法排流水线"
NO_RECIPE_MESSAGE = "至少需要一道菜谱"
TOO_MANY_MESSAGE = f"一次最多排 {MAX_RECIPES} 道菜"
NOT_FOUND_MESSAGE = "菜谱不存在：{ids}"

COOK_SYSTEM = "阶段：cook\n你是「食光」的备菜调度助手，只输出 JSON，不输出解释。"

_LOCATOR_PATTERN = re.compile(r"步骤\s*(\d+)")
_TIME_PATTERN = re.compile(r"^(\d{1,2}):(\d{2})$")


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _loads_steps(value: Any) -> list[str]:
    if isinstance(value, list):
        rows = value
    else:
        try:
            rows = json.loads(value or "[]")
        except (TypeError, json.JSONDecodeError):
            rows = []
    if not isinstance(rows, list):
        return []
    return [_norm(row) for row in rows if _norm(row)]


# --------------------------------------------------------------------------- #
# 取数
# --------------------------------------------------------------------------- #

def _load_recipes(recipe_ids: list[str]) -> tuple[list[dict], list[str]]:
    """按传入顺序取菜谱（去重）；不存在的 id 直接 404，不抛栈。"""
    ids: list[str] = []
    for raw in recipe_ids or []:
        text = _norm(raw)
        if text and text not in ids:
            ids.append(text)
    if not ids:
        raise AppError("invalid_request", NO_RECIPE_MESSAGE, 400)
    if len(ids) > MAX_RECIPES:
        raise AppError("too_many_recipes", TOO_MANY_MESSAGE, 400)

    placeholders = ",".join("?" * len(ids))
    conn = get_conn()
    try:
        rows = conn.execute(
            f"SELECT * FROM recipes WHERE id IN ({placeholders})", ids
        ).fetchall()
    finally:
        conn.close()
    found = {row["id"]: row for row in rows}

    missing = [rid for rid in ids if rid not in found]
    if missing:
        raise AppError("recipe_not_found", NOT_FOUND_MESSAGE.format(ids="、".join(missing)), 404)

    recipes: list[dict] = []
    warnings: list[str] = []
    for rid in ids:
        row = found[rid]
        steps = _loads_steps(row["steps"])
        if not steps:
            warnings.append(SKIP_RECIPE_WARNING.format(title=row["title"]))
            continue
        recipes.append(
            {
                "recipe_id": rid,
                "title": row["title"],
                "minutes": max(int(row["minutes"] or 0), MIN_MINUTES),
                "steps": steps,
            }
        )
    if not recipes:
        raise AppError("recipe_steps_missing", MISSING_STEPS_MESSAGE, 422)
    return recipes, warnings


def _resolve_start(start_at: str | None) -> tuple[int, str, list[str]]:
    """HH:MM → 当天分钟数；缺省用当前时间，格式错用默认值并写 warning。"""
    warnings: list[str] = []
    text = _norm(start_at)
    if not text:
        now = datetime.now().astimezone()
        return now.hour * 60 + now.minute, now.strftime("%H:%M"), warnings

    match = _TIME_PATTERN.match(text)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour * 60 + minute, f"{hour:02d}:{minute:02d}", warnings

    hour, minute = (int(part) for part in DEFAULT_START_AT.split(":"))
    warnings.append(BAD_START_WARNING.format(raw=text, fallback=DEFAULT_START_AT))
    return hour * 60 + minute, DEFAULT_START_AT, warnings


def _fmt(minute: int) -> str:
    minute = int(minute) % MINUTES_PER_DAY
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _parse_at(value: Any) -> int | None:
    match = _TIME_PATTERN.match(_norm(value))
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour * 60 + minute


def _parse_minutes(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        minutes = int(round(float(value)))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"步骤耗时「{value}」不是数字") from exc
    if not 0 <= minutes <= MAX_STEP_MINUTES:
        raise ValueError(f"步骤耗时「{value}」超出 0~{MAX_STEP_MINUTES} 分钟")
    return minutes


# --------------------------------------------------------------------------- #
# LLM 版
# --------------------------------------------------------------------------- #

def _sequence_messages(
    recipes: list[dict], start_text: str, hint: str | None = None
) -> list[dict]:
    lines = ["需要一个人同时做这几道菜，请排出可以照着执行的时间轴："]
    for recipe in recipes:
        lines.append(
            f"- recipe_id={recipe['recipe_id']}｜{recipe['title']}｜约 {recipe['minutes']} 分钟"
        )
        for index, step in enumerate(recipe["steps"], start=1):
            lines.append(f"  步骤 {index}：{step}")
    longest = max(recipe["minutes"] for recipe in recipes)
    lines += [
        "",
        f"从 {start_text} 开始。只能使用上面列出的步骤，可以合并同类动作，但每条都要标明来源。",
        '输出 JSON：{"steps":[{"order":1,"at":"18:30","action":"...","minutes":5,'
        '"parallel_with":[],"source":"recipe:r_002","locator":"步骤 1"}],"tips":["..."],"warnings":[]}',
        "at 用 HH:MM 且不早于开始时间；minutes 是这一步占用的分钟数（整数，可为 0）；"
        "parallel_with 填可以同时进行的其他步骤 order。",
        "source 必须是上面列出的 recipe:<id>；locator 必须是「步骤 n」且 n 在该菜谱步骤范围内。",
        f"总时长不能小于最长那道菜的 {longest} 分钟，并且每道菜都要有步骤。",
    ]
    user = "\n".join(lines)
    if hint:
        user += f"\n上次输出未通过校验：{hint}。请修正后重新输出完整时间轴。"
    return [
        {"role": "system", "content": COOK_SYSTEM},
        {"role": "user", "content": user},
    ]


def _parse_sequence(data: Any, recipes: list[dict], start_minute: int) -> dict:
    """解析模型输出；任何结构/来源问题都抛 ValueError（交给上层重试/降级）。"""
    if not isinstance(data, dict):
        raise ValueError("输出不是 JSON 对象")
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("steps 缺失或为空")

    by_id = {recipe["recipe_id"]: recipe for recipe in recipes}
    steps: list[dict] = []
    for row in raw_steps[:MAX_STEPS]:
        if not isinstance(row, dict):
            continue
        source = _norm(row.get("source"))
        recipe_id = source.split(":", 1)[1] if source.startswith("recipe:") else ""
        if recipe_id not in by_id:
            raise ValueError(f"步骤来源「{source}」不是所选菜谱")
        locator = _norm(row.get("locator"))
        match = _LOCATOR_PATTERN.search(locator)
        if not match:
            raise ValueError(f"引用「{locator}」应写成「步骤 n」")
        position = int(match.group(1))
        if not 1 <= position <= len(by_id[recipe_id]["steps"]):
            raise ValueError(
                f"引用「{locator}」超出「{by_id[recipe_id]['title']}」的步骤范围"
            )
        action = _norm(row.get("action"))
        if not action:
            raise ValueError("存在空步骤文本")
        at = _parse_at(row.get("at"))
        if at is None:
            raise ValueError(f"步骤时间「{row.get('at')}」应为 HH:MM")
        if at < start_minute:
            raise ValueError(f"步骤时间「{_fmt(at)}」早于开始时间 {_fmt(start_minute)}")
        steps.append(
            {
                "action": action,
                "minutes": _parse_minutes(row.get("minutes")),
                "start": at,
                "source": source,
                "locator": f"步骤 {position}",
            }
        )

    if not steps:
        raise ValueError("没有可用的步骤")
    covered = {step["source"] for step in steps}
    missing = [
        recipe["recipe_id"]
        for recipe in recipes
        if f"recipe:{recipe['recipe_id']}" not in covered
    ]
    if missing:
        raise ValueError(f"缺少菜谱 {'、'.join(missing)} 的步骤")

    tips = data.get("tips") if isinstance(data.get("tips"), list) else []
    warnings = data.get("warnings") if isinstance(data.get("warnings"), list) else []
    return _finalize(steps, recipes, start_minute, tips=tips, warnings=warnings)


# --------------------------------------------------------------------------- #
# 规则版
# --------------------------------------------------------------------------- #

def _split_steps(steps: list[str]) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """按关键词分成「预处理」与「下锅」两组；全是预处理时把最后一步当下锅。"""
    prep: list[tuple[int, str]] = []
    cook: list[tuple[int, str]] = []
    for index, text in enumerate(steps, start=1):
        bucket = prep if any(keyword in text for keyword in PREP_KEYWORDS) else cook
        bucket.append((index, text))
    if not cook and prep:
        cook = [prep.pop()]
    return prep, cook


def _rule_steps(recipes: list[dict], start_minute: int) -> tuple[list[dict], list[str]]:
    """预处理顺序执行，下锅块全部从预处理结束时同时起锅，长菜先起。"""
    clock = start_minute
    steps: list[dict] = []
    cook_plan: dict[str, list[tuple[int, str]]] = {}
    has_prep = False

    for recipe in recipes:
        prep, cook = _split_steps(recipe["steps"])
        cook_plan[recipe["recipe_id"]] = cook
        if prep:
            has_prep = True
        for index, text in prep:
            steps.append(
                {
                    "action": text,
                    "minutes": PREP_STEP_MINUTES,
                    "start": clock,
                    "source": f"recipe:{recipe['recipe_id']}",
                    "locator": f"步骤 {index}",
                }
            )
            clock += PREP_STEP_MINUTES
    prep_end = clock

    ordered = sorted(recipes, key=lambda item: (-item["minutes"], item["recipe_id"]))
    for recipe in ordered:
        cook_steps = cook_plan[recipe["recipe_id"]]
        count = len(cook_steps)
        if count == 0:
            continue
        base, remainder = divmod(recipe["minutes"], count)
        offset = 0
        for position, (index, text) in enumerate(cook_steps):
            duration = base + (remainder if position == count - 1 else 0)
            steps.append(
                {
                    "action": text,
                    "minutes": duration,
                    "start": prep_end + offset,
                    "source": f"recipe:{recipe['recipe_id']}",
                    "locator": f"步骤 {index}",
                }
            )
            offset += duration

    tips: list[str] = []
    if len(recipes) > 1:
        longest = ordered[0]
        tips.append(f"先把「{longest['title']}」起锅，它最久（{longest['minutes']} 分钟）")
        tips.append("预处理一次做完再开火，中途不用来回洗刀")
    if has_prep and len(recipes) > 1:
        tips.append("腌制、焯水可以和别的菜的切配并行，不用等前一道做完")
    return steps, tips


# --------------------------------------------------------------------------- #
# 组装 + verify
# --------------------------------------------------------------------------- #

def _finalize(
    steps: list[dict],
    recipes: list[dict],
    start_minute: int,
    *,
    tips: list[Any],
    warnings: list[Any],
) -> dict:
    """排序编号、算并行关系、算总时长，输出契约 §6.12 结构。"""
    steps.sort(key=lambda step: step["start"])  # 稳定排序：同一时刻保留原顺序
    for order, step in enumerate(steps, start=1):
        step["order"] = order
        step["parallel_with"] = []

    for current in steps:
        end_current = current["start"] + current["minutes"]
        for other in steps:
            if other is current or other["source"] == current["source"]:
                continue
            end_other = other["start"] + other["minutes"]
            if current["start"] < end_other and other["start"] < end_current:
                current["parallel_with"].append(other["order"])

    end_minute = max(step["start"] + step["minutes"] for step in steps)
    computed = max(end_minute - start_minute, 0)
    longest = max(recipe["minutes"] for recipe in recipes)
    total = max(computed, longest)

    public_steps = [
        {
            "order": step["order"],
            "at": _fmt(step["start"]),
            "action": step["action"],
            "minutes": step["minutes"],
            "parallel_with": step["parallel_with"],
            "source": step["source"],
            "locator": step["locator"],
        }
        for step in steps
    ]
    return {
        "total_minutes": int(total),
        "steps": public_steps,
        "tips": [str(tip).strip() for tip in tips if _norm(tip)][:MAX_TIPS],
        "warnings": [str(warning).strip() for warning in warnings if _norm(warning)][:MAX_TIPS],
    }


def verify_sequence(result: dict, recipes: list[dict], start_minute: int) -> list[str]:
    """契约 §6.12 的判定条件：来源可追溯、覆盖每道菜、总时长不小于最长单菜。"""
    problems: list[str] = []
    by_id = {recipe["recipe_id"]: recipe for recipe in recipes}
    steps = result.get("steps") or []
    if not steps:
        return ["时间轴没有任何步骤"]

    covered: set[str] = set()
    for step in steps:
        source = str(step.get("source") or "")
        recipe_id = source.split(":", 1)[1] if source.startswith("recipe:") else ""
        if recipe_id not in by_id:
            problems.append(f"步骤来源无效：{source or '（空）'}")
            continue
        covered.add(source)
        match = _LOCATOR_PATTERN.search(str(step.get("locator") or ""))
        if not match or not 1 <= int(match.group(1)) <= len(by_id[recipe_id]["steps"]):
            problems.append(f"步骤引用无效：{step.get('locator')}（{source}）")
        if not _norm(step.get("action")):
            problems.append("存在空步骤文本")
        if _parse_at(step.get("at")) is None:
            problems.append(f"步骤时间无效：{step.get('at')}")

    missing = [
        recipe_id
        for recipe_id in by_id
        if f"recipe:{recipe_id}" not in covered
    ]
    if missing:
        problems.append(f"缺少菜谱步骤：{'、'.join(missing)}")

    longest = max(recipe["minutes"] for recipe in recipes)
    if int(result.get("total_minutes") or 0) < longest:
        problems.append(
            f"总时长 {result.get('total_minutes')} 分钟小于最长单菜 {longest} 分钟"
        )

    end_minute = max(
        (_parse_at(step.get("at")) or start_minute) + int(step.get("minutes") or 0)
        for step in steps
    )
    if end_minute - start_minute > int(result.get("total_minutes") or 0):
        problems.append(
            f"总时长 {result.get('total_minutes')} 分钟小于时间轴实际占用 {end_minute - start_minute} 分钟"
        )
    return problems


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #

async def plan_sequence(
    recipe_ids: list[str],
    start_at: str | None = None,
    *,
    provider=None,
) -> dict:
    """返回 {total_minutes, steps, tips, warnings}（契约 §6.12）。"""
    recipes, warnings = _load_recipes(recipe_ids)
    start_minute, start_text, start_warnings = _resolve_start(start_at)
    warnings.extend(start_warnings)

    llm = resolve_provider(provider)
    result: dict | None = None
    hint: str | None = None
    if llm is not None:
        for attempt in range(LLM_ATTEMPTS):
            try:
                data = await llm.chat_json(_sequence_messages(recipes, start_text, hint))
                result = _parse_sequence(data, recipes, start_minute)
                break
            except Exception as exc:  # 网络 / JSON / 结构问题统一重试
                hint = _norm(exc)[:120] or type(exc).__name__
                logger.warning("备菜时间轴第 %d 次尝试失败：%s", attempt + 1, hint)
                result = None

    if result is None:
        steps, tips = _rule_steps(recipes, start_minute)
        result = _finalize(steps, recipes, start_minute, tips=tips, warnings=[])
        warnings.append(DEGRADE_WARNING)

    problems = verify_sequence(result, recipes, start_minute)
    if problems:
        logger.warning("备菜时间轴校验未通过：%s", problems)
        # 规则版必定满足「总时长 ≥ 最长单菜」，用它兜底一次
        steps, tips = _rule_steps(recipes, start_minute)
        result = _finalize(steps, recipes, start_minute, tips=tips, warnings=[])
        if DEGRADE_WARNING not in warnings:
            warnings.append(DEGRADE_WARNING)
        problems = verify_sequence(result, recipes, start_minute)

    if problems:
        warnings.append(VERIFY_WARNING.format(detail="；".join(problems[:2])))
    if start_minute + int(result["total_minutes"]) >= MINUTES_PER_DAY:
        warnings.append(CROSS_DAY_WARNING)

    result["warnings"] = list(
        dict.fromkeys([*warnings, *result.get("warnings", [])])
    )
    return result
