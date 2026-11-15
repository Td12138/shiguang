"""用户偏好（契约 §6.10）：进知识库、跨会话生效。

- 存储：`preferences` 表；同时写一条 `source=pref:<id>` 的 FTS chunk，可被 RAG 检索
- 语义：`avoid` 是**硬约束**（生成/改计划时禁止该食材出现），其余是软约束（进 Prompt）
- 置信度：`confidence < 0.6` 只保存不生效，调用方在 warnings 里提示「可能记住」
- 学习：对话改计划成功后再抽取一次；抽取失败只记日志，绝不影响主流程
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from pydantic import BaseModel, Field

from app.db.conn import ensure_schema, get_conn
from app.domain import instruction as instruction_parser
from app.domain.inventory import now_iso
from app.domain.tools_registry import AppError
from app.rag import index as rag_index

logger = logging.getLogger(__name__)

ID_PREFIX = "pref_"
KIND_AVOID = "avoid"
KIND_LIKE = "like"
KIND_TIME = "time"
KIND_PORTION = "portion"
KIND_HEALTH = "health"
KINDS: tuple[str, ...] = (KIND_AVOID, KIND_LIKE, KIND_TIME, KIND_PORTION, KIND_HEALTH)

SOURCE_DIALOG = "dialog"
SOURCE_MANUAL = "manual"
SOURCES: tuple[str, ...] = (SOURCE_DIALOG, SOURCE_MANUAL)

MIN_ACTIVE_CONFIDENCE = 0.6
MANUAL_CONFIDENCE = 1.0
DEFAULT_DIALOG_CONFIDENCE = 0.8
RULE_CONFIDENCE = 0.8
LIGHT_CONFIDENCE = 0.65
MAX_TEXT_CHARS = 120
MAX_LEARNED = 5

LIGHT_TEXT = "口味清淡，少油少盐"
AVOID_TEXT_TEMPLATE = "不吃{name}"
DEFAULT_KIND = KIND_AVOID

LOW_CONFIDENCE_TEMPLATE = (
    "记住的偏好「{text}」置信度只有 {confidence}（不到 {threshold}），暂不生效，"
    "可在偏好页确认后再启用"
)

LEARN_SYSTEM = (
    "阶段：preference\n你是「食光」的偏好抽取器。从用户对饮食计划的一句话指令里，"
    "抽取可以长期记住的饮食偏好，只输出 JSON，不输出解释。"
)
LEARN_USER_TEMPLATE = (
    "用户指令：{instruction}\n"
    '输出 JSON：{{"preferences":[{{"text":"一句话偏好（中文，如「不吃鸡蛋」）",'
    '"kind":"avoid|like|time|portion|health","confidence":0-1}}]}}\n'
    "只抽可以跨会话复用的稳定偏好；一次性的「今天随便」不要抽。不确定就给低置信度。"
)


def _new_id() -> str:
    return f"{ID_PREFIX}{uuid.uuid4().hex[:8]}"


def _clamp_confidence(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return round(max(0.0, min(number, 1.0)), 2)


def _row_to_dict(row) -> dict:
    data = dict(row)
    confidence = _clamp_confidence(data.get("confidence"), 0.0)
    data["confidence"] = confidence
    data["active"] = confidence >= MIN_ACTIVE_CONFIDENCE
    return data


def _prepare_text(text: Any) -> str:
    normalized = " ".join(str(text or "").split())[:MAX_TEXT_CHARS]
    if not normalized:
        raise AppError("invalid_preference_text", "偏好内容不能为空", 400)
    return normalized


def _prepare_kind(kind: Any) -> str:
    normalized = str(kind or DEFAULT_KIND).strip()
    if normalized not in KINDS:
        raise AppError(
            "invalid_preference_kind",
            f"偏好类型只能是 {'/'.join(KINDS)} 之一",
            400,
        )
    return normalized


def list_preferences(kind: str | None = None) -> list[dict]:
    """GET /api/preferences 的数据源（含低置信度项，前端按 active 区分展示）。"""
    ensure_schema()
    conn = get_conn()
    try:
        if kind:
            rows = conn.execute(
                "SELECT * FROM preferences WHERE kind = ? ORDER BY created_at, id", (kind,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM preferences ORDER BY created_at, id"
            ).fetchall()
    finally:
        conn.close()
    return [_row_to_dict(row) for row in rows]


def get_preference(pref_id: str) -> dict:
    ensure_schema()
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM preferences WHERE id = ?", (pref_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise AppError("preference_not_found", f"偏好不存在：{pref_id}", 404)
    return _row_to_dict(row)


def _find_duplicate(conn, text: str, kind: str):
    return conn.execute(
        "SELECT * FROM preferences WHERE kind = ? AND text = ? ORDER BY created_at LIMIT 1",
        (kind, text),
    ).fetchone()


def _upsert(
    text: Any,
    kind: Any,
    *,
    source: str,
    confidence: Any,
) -> tuple[dict, bool]:
    normalized_text = _prepare_text(text)
    normalized_kind = _prepare_kind(kind)
    if source not in SOURCES:
        raise AppError("invalid_preference_source", "偏好来源只能是 dialog/manual", 400)
    default = MANUAL_CONFIDENCE if source == SOURCE_MANUAL else DEFAULT_DIALOG_CONFIDENCE
    normalized_confidence = _clamp_confidence(confidence, default)
    timestamp = now_iso()

    ensure_schema()
    conn = get_conn()
    created = False
    try:
        row = _find_duplicate(conn, normalized_text, normalized_kind)
        if row is not None:
            # 重复学到同一偏好：抬高置信度（用户多次说要吃/不吃，更确定），不重复插入
            merged = max(_clamp_confidence(row["confidence"], 0.0), normalized_confidence)
            conn.execute(
                "UPDATE preferences SET confidence = ?, updated_at = ? WHERE id = ?",
                (merged, timestamp, row["id"]),
            )
            pref_id = row["id"]
        else:
            pref_id = _new_id()
            conn.execute(
                "INSERT INTO preferences(id,text,kind,source,confidence,user_id,created_at,updated_at)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (
                    pref_id,
                    normalized_text,
                    normalized_kind,
                    source,
                    normalized_confidence,
                    None,
                    timestamp,
                    timestamp,
                ),
            )
            created = True
        conn.commit()
        row = conn.execute("SELECT * FROM preferences WHERE id = ?", (pref_id,)).fetchone()
    finally:
        conn.close()

    try:  # 索引失败不影响偏好本身（检索降级，偏好仍生效）
        rag_index.sync_preference(pref_id)
    except Exception:
        logger.exception("偏好写入 FTS 索引失败：%s", pref_id)

    return _row_to_dict(row), created


def add_preference(
    text: Any,
    kind: Any = DEFAULT_KIND,
    *,
    source: str = SOURCE_MANUAL,
    confidence: Any = None,
) -> dict:
    """新增偏好；返回落库后的记录（重复偏好返回已有记录并抬高置信度）。"""
    row, _created = _upsert(text, kind, source=source, confidence=confidence)
    return row


def delete_preference(pref_id: str) -> dict:
    """删除偏好（契约 §6.10 的可控性底线），同步清掉 FTS 索引。"""
    get_preference(pref_id)  # 不存在直接 404
    conn = get_conn()
    try:
        conn.execute("DELETE FROM preferences WHERE id = ?", (pref_id,))
        conn.commit()
    finally:
        conn.close()

    try:
        rag_index.remove_preference(pref_id)
    except Exception:
        logger.exception("偏好 FTS 索引删除失败：%s", pref_id)
    return {"deleted": True, "id": pref_id}


# --------------------------------------------------------------------------- #
# 偏好 → 生成约束
# --------------------------------------------------------------------------- #

def active_preferences() -> list[dict]:
    return [row for row in list_preferences() if row["active"]]


def low_confidence_preferences() -> list[dict]:
    return [row for row in list_preferences() if not row["active"]]


def _matches(name: str, text: str) -> bool:
    """偏好文本里出现食材名即视为命中（「不吃鸡蛋」命中「鸡蛋」）。"""
    if not name or not text:
        return False
    if name in text:
        return True
    stripped = text.strip()
    return len(stripped) >= 2 and len(name) >= 2 and stripped in name


# 忌口表达里常见的动词/程度词，抽出后剩下的就是食材名
AVOID_PREFIXES: tuple[str, ...] = (
    "不喜欢吃", "不爱吃", "不能吃", "不可以吃", "不要吃", "不吃", "不吃任何",
    "不要", "别放", "不放", "不加", "忌口", "忌", "讨厌", "过敏于", "对", "怕",
)
AVOID_SUFFIXES: tuple[str, ...] = ("过敏", "不耐受", "一律不要", "都不要")


def avoid_terms(prefs: list[dict] | None = None) -> set[str]:
    """从忌口文本里直接抽出食材名，不依赖库存词表。

    审查发现：仅用库存名去匹配时，用户忌口的食材本来就不在库存里，
    结果 blocked 为空 → 整个硬约束失效。这里补一条独立词表。
    """
    rows = prefs if prefs is not None else active_preferences()
    terms: set[str] = set()
    for row in rows:
        if row["kind"] != KIND_AVOID or not row["active"]:
            continue
        text = str(row["text"]).strip()
        for prefix in AVOID_PREFIXES:
            if text.startswith(prefix):
                text = text[len(prefix) :]
        for suffix in AVOID_SUFFIXES:
            if text.endswith(suffix):
                text = text[: -len(suffix)]
        text = text.strip("，。,.、 ")
        if len(text) >= 2:
            terms.add(text)
    return terms


def blocked_names(
    vocabulary: list[str],
    *,
    prefs: list[dict] | None = None,
    extra: list[str] | None = None,
) -> set[str]:
    """`avoid` 硬约束命中的食材名（词表 + 本次指令额外排除项）。"""
    rows = prefs if prefs is not None else active_preferences()
    avoid_texts = [row["text"] for row in rows if row["kind"] == KIND_AVOID and row["active"]]
    names = [str(name).strip() for name in vocabulary if str(name or "").strip()]
    blocked = {name for name in names if any(_matches(name, text) for text in avoid_texts)}
    for name in extra or []:
        if str(name or "").strip():
            blocked.add(str(name).strip())
    return blocked


def soft_constraints(prefs: list[dict] | None = None) -> list[str]:
    rows = prefs if prefs is not None else active_preferences()
    return [row["text"] for row in rows if row["kind"] != KIND_AVOID]


def prompt_lines(prefs: list[dict] | None = None) -> list[str]:
    """给配餐 Prompt 的偏好段落（硬约束在前）。"""
    rows = prefs if prefs is not None else active_preferences()
    hard = [row["text"] for row in rows if row["kind"] == KIND_AVOID]
    soft = soft_constraints(rows)
    lines: list[str] = []
    if hard:
        lines.append("绝对不要使用这些食材（用户忌口）：" + "、".join(hard))
    if soft:
        lines.append("其他偏好（尽量满足）：" + "、".join(soft))
    return lines


def warnings_for_low_confidence(prefs: list[dict] | None = None) -> list[str]:
    rows = prefs if prefs is not None else low_confidence_preferences()
    return [
        LOW_CONFIDENCE_TEMPLATE.format(
            text=row["text"], confidence=row["confidence"], threshold=MIN_ACTIVE_CONFIDENCE
        )
        for row in rows
    ]


def instruction_conflicts(
    instruction: str, vocabulary: list[str], prefs: list[dict] | None = None
) -> list[dict]:
    """本次指令想要某食材、但已记住「不吃」它 → 冲突（以本次指令为准）。"""
    rows = prefs if prefs is not None else active_preferences()
    requested = instruction_parser.names_requested(instruction, vocabulary)
    conflicts: list[dict] = []
    for row in rows:
        if row["kind"] != KIND_AVOID or not row["active"]:
            continue
        for name in requested:
            if _matches(name, row["text"]):
                conflicts.append({"id": row["id"], "text": row["text"], "name": name})
                break
    return conflicts


# --------------------------------------------------------------------------- #
# 从对话学偏好
# --------------------------------------------------------------------------- #

def _learn_messages(instruction: str) -> list[dict]:
    return [
        {"role": "system", "content": LEARN_SYSTEM},
        {"role": "user", "content": LEARN_USER_TEMPLATE.format(instruction=instruction)},
    ]


class LearnedPreference(BaseModel):
    """LLM 抽取结果的结构化输出（契约 §7：schema 校验后才落库）。"""

    text: str = ""
    kind: str = KIND_AVOID
    confidence: float = Field(default=DEFAULT_DIALOG_CONFIDENCE, ge=0.0, le=1.0)


class LearnedPreferences(BaseModel):
    preferences: list[LearnedPreference] = Field(default_factory=list)


def _parse_llm(data: Any) -> list[dict]:
    if not isinstance(data, dict):
        return []
    rows = data.get("preferences")
    if not isinstance(rows, list):
        return []
    learned: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        text = " ".join(str(row.get("text") or "").split())[:MAX_TEXT_CHARS]
        kind = str(row.get("kind") or "").strip()
        if not text or kind not in KINDS:
            continue
        learned.append(
            {
                "text": text,
                "kind": kind,
                "confidence": _clamp_confidence(row.get("confidence"), DEFAULT_DIALOG_CONFIDENCE),
            }
        )
        if len(learned) >= MAX_LEARNED:
            break
    return learned


def rule_preferences(instruction: str, vocabulary: list[str]) -> list[dict]:
    """规则版抽取：中文否定词 + 清淡类关键词（模型不可用时兜底）。"""
    learned = [
        {
            "text": AVOID_TEXT_TEMPLATE.format(name=name),
            "kind": KIND_AVOID,
            "confidence": RULE_CONFIDENCE,
        }
        for name in instruction_parser.names_negated(instruction, vocabulary)
    ]
    if instruction_parser.mentions_light(instruction):
        learned.append(
            {"text": LIGHT_TEXT, "kind": KIND_HEALTH, "confidence": LIGHT_CONFIDENCE}
        )
    return learned[:MAX_LEARNED]


async def learn_from_instruction(
    instruction: str, provider, vocabulary: list[str] | None = None
) -> list[dict]:
    """对话改计划成功后调用：抽取并落库，返回**新学到**的偏好；失败返回 []。"""
    text = str(instruction or "").strip()
    if not text:
        return []

    candidates: list[dict] = []
    if provider is not None:
        try:
            data = await provider.chat_json(_learn_messages(text), schema=LearnedPreferences)
            candidates = _parse_llm(data)
        except Exception as exc:  # 学不到就算了，不影响主流程
            logger.info("偏好抽取失败，本次不学习：%s", type(exc).__name__)
    if not candidates:
        candidates = rule_preferences(text, list(vocabulary or []))

    learned: list[dict] = []
    for candidate in candidates:
        try:
            row, created = _upsert(
                candidate["text"],
                candidate["kind"],
                source=SOURCE_DIALOG,
                confidence=candidate.get("confidence"),
            )
        except AppError:
            logger.warning("偏好落库被拒绝：%s", candidate.get("text"))
            continue
        except Exception:
            logger.exception("偏好落库失败：%s", candidate.get("text"))
            continue
        if created:
            learned.append(
                {
                    "id": row["id"],
                    "text": row["text"],
                    "kind": row["kind"],
                    "confidence": row["confidence"],
                }
            )
    return learned
