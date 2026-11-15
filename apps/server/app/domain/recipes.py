"""菜谱建议 Agent 流水线（契约 §9）。

五步：understand → plan → retrieve → compose → verify，每步写进 `agent_runs.steps`
（name / status / started_at / ms / summary）。任一步失败都有明确降级路径，
降级时在响应 `warnings` 里标注「已降级」，不静默假装成功。
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from app.db.conn import get_conn
from app.domain import tools_registry
from app.domain.inventory import stale_active_warning
from app.domain.tools_registry import AppError, resolve_provider
from app.rag import citations as citation_utils

logger = logging.getLogger(__name__)

RUN_KIND = "recipes_suggest"
STATE_RUNNING = "running"
STATE_OK = "ok"
STATE_DEGRADED = "degraded"
STATE_FAILED = "failed"

STEP_UNDERSTAND = "understand"
STEP_PLAN = "plan"
STEP_RETRIEVE = "retrieve"
STEP_COMPOSE = "compose"
STEP_VERIFY = "verify"

DEFAULT_MAX_MINUTES = 30
DEFAULT_LIMIT = 3
MAX_LIMIT = 10
PLAN_TOP_K = 10
MIN_RECIPE_STEPS = 3
CANDIDATE_MULTIPLIER = 2
COMPOSE_ATTEMPTS = 2
EPSILON = 1e-6
DEGRADE_WARNING = "已降级：模型不可用或输出未通过校验，本次按检索分数排序并用模板生成理由"

UNDERSTAND_SYSTEM = "阶段：understand\n你是「食光」的菜谱规划助手，只输出 JSON，不输出解释。"
COMPOSE_SYSTEM = "阶段：compose\n你是「食光」的菜谱推荐助手，只输出 JSON，不输出解释。"

# 进度回调（契约 §6.15）：domain 每完成一步 await 一次，SSE 层据此发 step 事件
StepCallback = Callable[[dict], Awaitable[None]]


class _Stopwatch:
    def __init__(self) -> None:
        self._t0 = time.perf_counter()
        self.started_at = _now_iso()

    def ms(self) -> int:
        return int((time.perf_counter() - self._t0) * 1000)


def _now_iso() -> str:
    from datetime import datetime

    return datetime.now().astimezone().isoformat(timespec="seconds")


def _new_run_id() -> str:
    return f"run_{uuid.uuid4().hex[:12]}"


class _Trace:
    """收集五步轨迹，最后一次性落库。

    ``on_step`` 只给流式接口用（契约 §6.15）：每完成一步就 await 一次回调，把
    step 即时推给前端。默认 ``None`` 时行为与之前完全一致（只收集、结束时落库）。
    """

    def __init__(self, on_step: StepCallback | None = None) -> None:
        self.steps: list[dict] = []
        self._on_step = on_step

    async def add(self, name: str, status: str, watch: _Stopwatch, summary: str) -> None:
        step = {
            "name": name,
            "status": status,
            "started_at": watch.started_at,
            "ms": watch.ms(),
            "summary": summary,
        }
        self.steps.append(step)
        if self._on_step is not None:
            # 传副本：回调方（SSE 层）不得改动落库的轨迹
            await self._on_step(dict(step))


async def _invoke_tool(name: str, args: dict, fallback):
    """优先走 core.tools.call（真正的工具注册表），失败退回同一实现（本地直调）。

    core 缺失（并行开发阶段）时直接本地调用，保证降级路径可测。
    """
    try:
        from app.core.tools import call as tool_call
    except ImportError:
        return fallback(**args)

    result = await tool_call(name, args)
    if isinstance(result, dict) and result.get("error"):
        logger.warning("工具 %s 通过注册表失败（%s），改用本地实现", name, result.get("error"))
        return fallback(**args)
    return result


def _persist_run(run_id: str, state: str, steps: list[dict], kind: str = RUN_KIND) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO agent_runs(id,kind,state,steps,created_at) VALUES(?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET state=excluded.state, steps=excluded.steps, kind=excluded.kind",
            (
                run_id,
                kind,
                state,
                json.dumps(steps, ensure_ascii=False),
                _now_iso(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_run(run_id: str) -> dict:
    """GET /api/agent/runs/{id} 的数据源。"""
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM agent_runs WHERE id = ?", (run_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise AppError("run_not_found", f"Agent 运行记录不存在：{run_id}", 404)
    try:
        steps = json.loads(row["steps"] or "[]")
    except json.JSONDecodeError:
        steps = []
    return {
        "id": row["id"],
        "kind": row["kind"],
        "state": row["state"],
        "steps": steps,
        "created_at": row["created_at"],
    }


# --------------------------------------------------------------------------- #
# Prompt
# --------------------------------------------------------------------------- #

def _understand_messages(use: list[str], max_minutes: int, limit: int) -> list[dict]:
    user = (
        f"用户点名的库存 id：{use or '未指定'}；可接受最大耗时 {max_minutes} 分钟；"
        f"需要 {limit} 条建议。\n"
        '请输出 JSON：{"max_minutes": 整数, "servings": 整数, "taste": 字符串或 null, '
        '"note": 一句话说明}'
    )
    return [
        {"role": "system", "content": UNDERSTAND_SYSTEM},
        {"role": "user", "content": user},
    ]


def _compose_messages(
    candidates: list[dict],
    inventory_items: list[dict],
    constraints: dict,
    limit: int,
    hint: str | None = None,
) -> list[dict]:
    inventory_lines = [
        f"- {item['name']}（{item['qty']}{item.get('unit') or ''}，{item['days_left']} 天后到期）"
        for item in inventory_items
    ]
    candidate_lines = []
    for cand in candidates:
        ingredients = "、".join(
            str(x.get("name") or "") for x in cand.get("ingredients", []) if x.get("name")
        )
        candidate_lines.append(
            f"- recipe_id={cand['recipe_id']}｜{cand['title']}｜{cand['minutes']} 分钟｜"
            f"食材：{ingredients}｜引用：{cand['source']} {cand['locator']}"
        )

    user = "\n".join(
        [
            "库存（按临期排序）：",
            *(inventory_lines or ["- （空）"]),
            "",
            "检索到的候选菜谱（只能从这里选，recipe_id 必须原样使用）：",
            *(candidate_lines or ["- （空）"]),
            "",
            f"约束：{json.dumps(constraints, ensure_ascii=False)}；最多 {limit} 条。",
            '输出 JSON：{"recommendations":[{"recipe_id":"...","reason":"一句话中文理由",'
            '"citations":[{"source":"...","locator":"..."}]}]}',
            "citations 必须取自上面列出的「引用」，不得编造；reason 要提到用掉了哪样临期食材。",
        ]
    )
    if hint:
        user += f"\n上次输出未通过校验：{hint}。请修正后重新输出。"
    return [
        {"role": "system", "content": COMPOSE_SYSTEM},
        {"role": "user", "content": user},
    ]


# --------------------------------------------------------------------------- #
# 各步实现
# --------------------------------------------------------------------------- #

def _normalize_constraints(data: Any, defaults: dict) -> dict:
    constraints = dict(defaults)
    if not isinstance(data, dict):
        return constraints
    try:
        if data.get("max_minutes"):
            constraints["max_minutes"] = max(1, min(int(data["max_minutes"]), 240))
        if data.get("servings"):
            constraints["servings"] = max(1, min(int(data["servings"]), 8))
    except (TypeError, ValueError):
        pass
    taste = data.get("taste")
    if isinstance(taste, str) and taste.strip():
        constraints["taste"] = taste.strip()
    note = data.get("note")
    if isinstance(note, str) and note.strip():
        constraints["note"] = note.strip()[:60]
    return constraints


def _select_inventory(items: list[dict], use: list[str]) -> list[dict]:
    if not use:
        return items
    chosen = [item for item in items if item["id"] in set(use)]
    rest = [item for item in items if item["id"] not in set(use)]
    return chosen + rest


def _parse_compose(data: Any) -> list[dict]:
    if not isinstance(data, dict):
        raise ValueError("输出不是 JSON 对象")
    raw = data.get("recommendations")
    if not isinstance(raw, list) or not raw:
        raise ValueError("recommendations 缺失或为空")
    parsed: list[dict] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        recipe_id = str(row.get("recipe_id") or "").strip()
        if not recipe_id:
            continue
        parsed.append(
            {
                "recipe_id": recipe_id,
                "reason": str(row.get("reason") or "").strip(),
                "citations": row.get("citations") if isinstance(row.get("citations"), list) else [],
            }
        )
    if not parsed:
        raise ValueError("没有可用的 recipe_id")
    return parsed


def _sanitize_citations(raw: list, candidate: dict, allowed: set[tuple[str, str]]) -> list[dict]:
    """只保留来自本次检索结果的引用；LLM 没给或给了假的，用候选自带引用兜底。"""
    kept: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip()
        locator = str(item.get("locator") or "").strip()
        key = (source, locator)
        if not source or key not in allowed or key in seen:
            continue
        seen.add(key)
        # 前端角标要弹原文：text 取候选 chunk 的 body（截断 120 字）
        kept.append(citation_utils.make(source, locator, candidate.get("body")))
    if not kept:
        fallback = citation_utils.from_chunk(candidate)
        if fallback["source"]:
            kept.append(fallback)
    return kept


def _assemble(
    parsed: list[dict], candidates: list[dict], limit: int
) -> tuple[list[dict], list[str]]:
    """把 LLM 输出对齐到候选 chunk，返回 (推荐列表, 无效 recipe_id 列表)。"""
    by_id = {cand["recipe_id"]: cand for cand in candidates}
    allowed = {
        (cand["source"], cand["locator"]): cand for cand in candidates if cand.get("source")
    }
    allowed_keys = set(allowed)
    recommendations: list[dict] = []
    invalid: list[str] = []
    seen: set[str] = set()

    for row in parsed:
        recipe_id = row["recipe_id"]
        candidate = by_id.get(recipe_id)
        if candidate is None:
            invalid.append(recipe_id)
            continue
        if recipe_id in seen:
            continue
        seen.add(recipe_id)
        recommendations.append(
            {
                "recipe_id": recipe_id,
                "title": candidate["title"],
                "minutes": candidate["minutes"],
                "reason": row["reason"] or _template_reason(candidate, []),
                "missing": candidate.get("missing", []),
                "citations": _sanitize_citations(row["citations"], candidate, allowed_keys),
                "score": round(float(candidate.get("rel", 0.0)), 4),
            }
        )
        if len(recommendations) >= limit:
            break
    return recommendations, invalid


def _verify(
    recommendations: list[dict], candidates: list[dict]
) -> tuple[list[dict], list[str]]:
    """规则校验：recipe_id 在检索结果内、步骤 ≥3；返回 (通过, 不通过原因)。"""
    by_id = {cand["recipe_id"]: cand for cand in candidates}
    kept: list[dict] = []
    problems: list[str] = []
    for rec in recommendations:
        candidate = by_id.get(rec["recipe_id"])
        if candidate is None:
            problems.append(f"{rec['recipe_id']} 不在检索结果中")
            continue
        if int(candidate.get("steps_count", 0)) < MIN_RECIPE_STEPS:
            problems.append(f"{rec['recipe_id']} 步骤不足 {MIN_RECIPE_STEPS} 步")
            continue
        kept.append(rec)
    return kept, problems


def _template_reason(candidate: dict, inventory_items: list[dict]) -> str:
    matched: list[dict] = []
    for ingredient in candidate.get("ingredients", []):
        name = str(ingredient.get("name") or "").strip()
        if not name:
            continue
        for item in inventory_items:
            if name in item["name"] or item["name"] in name:
                matched.append(item)
                break

    if matched:
        best = min(matched, key=lambda item: item.get("days_left", 0))
        days = int(best.get("days_left", 0))
        if days < 0:
            head = f"先处理已经过期的{best['name']}"
        elif days == 0:
            head = f"用掉今天到期的{best['name']}"
        elif days == 1:
            head = f"用掉明天到期的{best['name']}"
        else:
            head = f"用掉你 {days} 天后到期的{best['name']}"
    else:
        head = "主要用你冰箱里现有的食材"

    missing = [m["name"] for m in candidate.get("missing", []) if not m.get("optional")]
    if missing:
        tail = f"，还需补{'、'.join(missing[:2])}"
    else:
        tail = "，不用额外采购"
    return f"{head}，{candidate['minutes']} 分钟可完成{tail}。"


def _degraded_recommendations(
    candidates: list[dict], inventory_items: list[dict], limit: int
) -> list[dict]:
    """规则版：按检索分数排序 + 模板理由（不编造引用，只保留步骤达标的菜谱）。"""
    recommendations: list[dict] = []
    for candidate in candidates:
        if int(candidate.get("steps_count", 0)) < MIN_RECIPE_STEPS:
            continue
        recommendations.append(
            {
                "recipe_id": candidate["recipe_id"],
                "title": candidate["title"],
                "minutes": candidate["minutes"],
                "reason": _template_reason(candidate, inventory_items),
                "missing": candidate.get("missing", []),
                "citations": citation_utils.collect([candidate], 1),
                "score": round(float(candidate.get("rel", 0.0)), 4),
            }
        )
        if len(recommendations) >= limit:
            break
    return recommendations


def _round_qty(value: float) -> float | int:
    if abs(value - round(value)) < 1e-6:
        return int(round(value))
    return round(value, 2)


def _matched_inventory(name: str, inventory_items: list[dict]) -> list[dict]:
    """按名称互含匹配库存行，临期优先（前端按 inventory_id 直接扣库存）。"""
    rows = [
        item
        for item in inventory_items
        if name
        and (
            name == str(item.get("name") or "")
            or name in str(item.get("name") or "")
            or str(item.get("name") or "") in name
        )
    ]
    rows.sort(key=lambda item: int(item.get("days_left", 0)))
    return rows


def _attach_uses(
    recommendations: list[dict], candidates: list[dict], inventory_items: list[dict]
) -> None:
    """给每条推荐补 uses：[{inventory_id,name,qty,unit}]，跨推荐不重复占用同一库存。"""
    by_id = {cand["recipe_id"]: cand for cand in candidates}
    remaining = {
        item["id"]: float(item.get("qty") or 0.0) for item in inventory_items
    }

    for rec in recommendations:
        candidate = by_id.get(rec["recipe_id"]) or {}
        uses: list[dict] = []
        for ingredient in candidate.get("ingredients", []):
            name = str(ingredient.get("name") or "").strip()
            need = float(ingredient.get("qty") or 1)
            if not name or need <= 0:
                continue
            for item in _matched_inventory(name, inventory_items):
                available = remaining.get(item["id"], 0.0)
                if available <= EPSILON:
                    continue
                take = min(need, available)
                uses.append(
                    {
                        "inventory_id": item["id"],
                        "name": item["name"],
                        "qty": _round_qty(take),
                        "unit": item.get("unit") or ingredient.get("unit") or "",
                    }
                )
                remaining[item["id"]] = available - take
                need -= take
                if need <= EPSILON:
                    break
        rec["uses"] = uses


async def _try_compose(
    provider, messages: list[dict]
) -> tuple[list[dict] | None, str | None]:
    """调 LLM 解析输出，最多 COMPOSE_ATTEMPTS 次；全失败返回 (None, 原因)。"""
    last_error: str | None = None
    for _attempt in range(COMPOSE_ATTEMPTS):
        try:
            data = await provider.chat_json(messages)
            return _parse_compose(data), None
        except Exception as exc:  # 网络、JSON、结构问题统一重试
            last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("compose 第 %d 次尝试失败：%s", _attempt + 1, last_error)
    return None, last_error


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #

async def suggest(
    use: list[str] | None = None,
    max_minutes: int = DEFAULT_MAX_MINUTES,
    limit: int = DEFAULT_LIMIT,
    *,
    provider=None,
    on_step: StepCallback | None = None,
) -> dict:
    """五步流水线；返回 {run_id, recommendations, warnings}。

    ``on_step`` 仅流式接口传（契约 §6.15），非流式保持默认 ``None``。"""
    use = [str(x) for x in (use or [])]
    max_minutes = max(1, min(int(max_minutes or DEFAULT_MAX_MINUTES), 240))
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))

    run_id = _new_run_id()
    trace = _Trace(on_step)
    warnings: list[str] = []
    state = STATE_OK
    _persist_run(run_id, STATE_RUNNING, trace.steps)

    llm = resolve_provider(provider)
    tools_registry.register_all()  # 幂等：core 注册表里要有 5 个工具

    try:
        # ---- 1 understand ----
        watch = _Stopwatch()
        constraints = {
            "max_minutes": max_minutes,
            "use": use,
            "servings": 1,
            "taste": None,
        }
        if llm is None:
            await trace.add(STEP_UNDERSTAND, STATE_DEGRADED, watch, "无可用模型，按输入参数执行")
            warnings.append("已降级：模型不可用，意图解析按输入参数执行")
        else:
            try:
                data = await llm.chat_json(_understand_messages(use, max_minutes, limit))
                constraints = _normalize_constraints(data, constraints)
                await trace.add(
                    STEP_UNDERSTAND,
                    STATE_OK,
                    watch,
                    f"意图：{constraints['servings']} 人份 / {constraints['max_minutes']} 分钟内",
                )
            except Exception as exc:
                logger.warning("understand 失败，按输入参数继续：%s", exc)
                await trace.add(STEP_UNDERSTAND, STATE_DEGRADED, watch, "解析失败，按输入参数执行")
                warnings.append("已降级：意图解析失败，按输入参数执行")

        # ---- 2 plan ----
        watch = _Stopwatch()
        try:
            planned = await _invoke_tool(
                "list_inventory",
                {"sort": "expiry", "limit": PLAN_TOP_K},
                tools_registry.list_inventory,
            )
        except Exception as exc:
            await trace.add(STEP_PLAN, "error", watch, "库存读取失败")
            _persist_run(run_id, STATE_FAILED, trace.steps)
            raise AppError("plan_failed", "读取库存失败，请稍后重试", 500, str(exc)) from exc

        inventory_items = _select_inventory(planned["items"], use)
        # 契约 §6.14：数据陈旧时必须提示「先拍一张对账」，但不阻断生成
        stale_warning = stale_active_warning()
        if stale_warning:
            warnings.append(stale_warning)
        expired = [item for item in inventory_items if int(item.get("days_left", 0)) < 0]
        if expired:
            # 食品安全底线：过期食材不参与推荐，只提示处理
            inventory_items = [
                item for item in inventory_items if int(item.get("days_left", 0)) >= 0
            ]
            warnings.append(
                "有 {} 样已过期（{}），已排除在推荐之外，请先确认是否丢弃".format(
                    len(expired), "、".join(str(item["name"]) for item in expired)
                )
            )
        await trace.add(
            STEP_PLAN,
            STATE_OK,
            watch,
            f"取临期 {len(inventory_items)} 项（最紧急："
            f"{inventory_items[0]['name'] if inventory_items else '无'} ）",
        )
        if not inventory_items:
            warnings.append("库存为空，建议先拍照入库")

        # ---- 3 retrieve ----
        watch = _Stopwatch()
        names = [item["name"] for item in inventory_items]
        found = await _invoke_tool(
            "find_recipes",
            {
                "ingredients": names,
                "max_minutes": constraints["max_minutes"],
                "limit": max(limit * CANDIDATE_MULTIPLIER, limit),
            },
            tools_registry.find_recipes,
        )
        candidates = found["items"]
        if not candidates:
            await trace.add(STEP_RETRIEVE, "empty", watch, "检索无匹配菜谱")
            await trace.add(STEP_COMPOSE, "skipped", _Stopwatch(), "无候选，跳过排序")
            await trace.add(STEP_VERIFY, "skipped", _Stopwatch(), "无候选，跳过校验")
            _persist_run(run_id, STATE_DEGRADED, trace.steps)
            return {
                "run_id": run_id,
                "recommendations": [],
                "warnings": warnings + ["库存里没有匹配菜谱"],
            }
        await trace.add(STEP_RETRIEVE, STATE_OK, watch, f"命中 {len(candidates)} 个候选菜谱")

        # ---- 4 compose ----
        watch = _Stopwatch()
        messages = _compose_messages(candidates, inventory_items, constraints, limit)
        parsed: list[dict] | None = None
        if llm is not None:
            parsed, _reason = await _try_compose(llm, messages)

        if parsed is None:
            recommendations = _degraded_recommendations(candidates, inventory_items, limit)
            _attach_uses(recommendations, candidates, inventory_items)
            state = STATE_DEGRADED
            await trace.add(STEP_COMPOSE, STATE_DEGRADED, watch, "模型不可用，按检索分数排序")
            warnings.append(DEGRADE_WARNING)
            await trace.add(STEP_VERIFY, STATE_DEGRADED, _Stopwatch(), "规则版无需校验，沿用模板结果")
            _persist_run(run_id, state, trace.steps)
            return {"run_id": run_id, "recommendations": recommendations, "warnings": warnings}

        recommendations, invalid = _assemble(parsed, candidates, limit)
        await trace.add(
            STEP_COMPOSE,
            STATE_OK if not invalid else STATE_DEGRADED,
            watch,
            f"模型给出 {len(recommendations)} 条，引用已对齐检索结果",
        )

        # ---- 5 verify（不过则重试 1 次，仍不过则剔除）----
        watch = _Stopwatch()
        kept, problems = _verify(recommendations, candidates)
        problems = [f"{rid} 不在检索结果中" for rid in invalid] + problems
        retried = False
        if problems and llm is not None:
            retried = True
            hint = "；".join(problems[:3])
            logger.info("verify 未通过，重试一次：%s", hint)
            parsed_retry, _reason = await _try_compose(
                llm, _compose_messages(candidates, inventory_items, constraints, limit, hint)
            )
            if parsed_retry:
                retry_recommendations, retry_invalid = _assemble(parsed_retry, candidates, limit)
                kept_retry, retry_problems = _verify(retry_recommendations, candidates)
                retry_problems = [
                    f"{rid} 不在检索结果中" for rid in retry_invalid
                ] + retry_problems
                if len(kept_retry) >= len(kept):
                    kept, problems = kept_retry, retry_problems
                else:
                    problems = retry_problems

        if not kept:
            recommendations = _degraded_recommendations(candidates, inventory_items, limit)
            state = STATE_DEGRADED
            await trace.add(STEP_VERIFY, STATE_DEGRADED, watch, "校验全部不通过，改用规则版")
            warnings.append(DEGRADE_WARNING)
        else:
            recommendations = kept
            if problems:
                warnings.append(f"已剔除 {len(problems)} 条未通过校验的建议")
            await trace.add(
                STEP_VERIFY,
                STATE_OK if not problems else STATE_DEGRADED,
                watch,
                f"通过 {len(kept)} 条" + ("，已重试一次" if retried else ""),
            )

        _persist_run(run_id, state, trace.steps)
        _attach_uses(recommendations, candidates, inventory_items)
        return {"run_id": run_id, "recommendations": recommendations, "warnings": warnings}

    except AppError:
        raise
    except Exception as exc:
        logger.exception("菜谱建议流水线异常")
        _persist_run(run_id, STATE_FAILED, trace.steps)
        raise AppError("agent_failed", "菜谱建议生成失败，请稍后重试", 500, str(exc)) from exc
