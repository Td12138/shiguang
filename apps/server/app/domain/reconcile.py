"""库存对账业务域（契约 §6.13 对账 / §6.14 数据新鲜度）。

两块职责：

1. `build_diff`：识别结果 × `status=active` 库存 → `missing / reduced / added / suspect`
   - 只用标准名（别名表已在 API 层折算），同名多条库存按到期先后分配识别数量
   - 置信度 < 0.7 或名字看不清 → `suspect`，**不得直接判 missing**（规则 1）
   - 识别数量多于库存不算新增，只给 warning（不擅自加库存）
   - 识别为空 → 全部保留，只给 warning（规则 2：默认 keep，AI 不擅自删）
2. `apply`：按用户确认的动作落库（规则 3/4/5）
   - 先全量校验（action/reason/qty/库存状态），全部通过后才落库；整批一个事务
   - `discarded` → 复用 `inventory.discard`（写 waste_log，碳排口径与 §6.3 一致）
   - `consumed` → 复用 `inventory.consume`（写 events.kind=consume）
   - `reduced` → 同比例改 qty 与 grams
   - `added` → 复用 `inventory.add_items`（顺带刷新 verified_at）
   - 幂等：`reconcile_applied` 指纹台账 = request_id + 动作 + 目标值；
     同一 request_id 重复提交只生效一次，不同 request_id 的相同动作正常生效
   - 留痕：真正改到数据时写一条 `events(kind=reconcile)`，与业务改动同事务
3. `_resolve_checked_at`：核验时间必须可解析（§6.14），非法/未来时间收敛到服务端当前时间
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from app.db.conn import ensure_schema, get_conn, transaction
from app.domain import inventory as inventory_domain
from app.domain.inventory import (
    DEFAULT_UNIT,
    DISCARD_REASONS,
    STATUS_ACTIVE,
    days_left,
    now_iso,
)
from app.domain.tools_registry import AppError

logger = logging.getLogger(__name__)

EVENT_KIND = "reconcile"
EVENT_SOURCE = "reconcile/apply"

LOW_CONFIDENCE = 0.7
DEFAULT_QTY = 1.0
DEFAULT_CONFIDENCE = 1.0  # 模型没给置信度 = 它认为自己看清了
QTY_EPSILON = 1e-3
DEFAULT_DISCARD_REASON = "spoiled"
EMPTY_EXPIRY_ORDER = "9999-12-31"  # 没有到期日的排最后（临期优先匹配）

# 幂等台账（契约 §6.13 规则 4）：request_id 把「同一次对账的重复提交」与
# 「用户后来又真的做了一次」区分开；客户端不给就服务端生成一个
REQUEST_ID_PREFIX = "req_"
REQUEST_ID_MAX_LENGTH = 128

ACTION_KEEP = "keep"
ACTION_CONSUMED = "consumed"
ACTION_DISCARDED = "discarded"
VALID_ACTIONS: tuple[str, ...] = (ACTION_CONSUMED, ACTION_DISCARDED, ACTION_KEEP)

# 模型「明确说不清」的常见写法，命中就进 suspect（规则 1）
UNCLEAR_HINTS: tuple[str, ...] = (
    "看不清",
    "看不清是什么",
    "未知",
    "无法识别",
    "无法判断",
    "不确定",
    "模糊",
    "疑似",
    "unclear",
    "unknown",
    "n/a",
)

EMPTY_RECOGNITION_TEMPLATE = "本次没有识别出任何食材，未做任何改动：{count} 样库存全部保留（可重拍一张或手动处理）"
EMPTY_RECOGNITION_NO_STOCK = "本次没有识别出任何食材，库存本来就是空的，未做任何改动"
SUSPECT_WARNING_TEMPLATE = "「{name}」识别置信度较低（{confidence}），已放入 suspect，请人工确认"
SURPLUS_WARNING_TEMPLATE = (
    "「{name}」识别数量 {recognized}{unit} 多于库存 {stock}{unit}，未判为新增（不擅自加库存）"
)
SKIP_NOT_ACTIVE_TEMPLATE = "「{name}」当前状态是 {status}，已跳过"
SKIP_MISSING_ROW_TEMPLATE = "库存记录 {inventory_id} 已不存在，已跳过"
SKIP_ALREADY_APPLIED_TEMPLATE = "「{name}」这次改动此前已经生效，跳过（幂等）"
SKIP_SAME_QTY_TEMPLATE = "「{name}」数量已经是 {qty}{unit}，无需再改（幂等）"
SKIP_TARGET_TOO_LARGE_TEMPLATE = "「{name}」目标数量 {target}{unit} 大于当前库存 {current}{unit}，对账只能减不能增，已跳过"
SKIP_ZERO_QTY_TEMPLATE = "「{name}」目标数量为 0，要清空请用 missing + discarded/consumed，已跳过"
SKIP_ZERO_ADD_TEMPLATE = "「{name}」新增数量为 0，已跳过"
DEFAULT_REASON_WARNING_TEMPLATE = "「{name}」未提供丢弃原因，按 {reason} 记账"
DUPLICATE_IN_BATCH_TEMPLATE = "「{name}」在同一次对账里重复出现，只处理第一条"
SKIP_STATE_CHANGED_TEMPLATE = "「{name}」在对账过程中状态已变化，已跳过"
NOTHING_APPLIED_WARNING = "这次没有可落地的改动（全部 keep 或已生效过）"
CHECKED_AT_INVALID_TEMPLATE = "核验时间「{value}」不是合法时间，已按服务端当前时间记录"
CHECKED_AT_FUTURE_TEMPLATE = "核验时间「{value}」晚于当前时间，已按当前时间记录（避免被当成永远新鲜）"

REASON_LOW_CONFIDENCE = "识别置信度低（{confidence}），无法确认是否还在"
REASON_UNCLEAR = "识别结果看不清，无法确认是否还在"


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #

def _norm_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _as_float(value: Any, default: float = DEFAULT_QTY) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number or number in (float("inf"), float("-inf")):
        return default
    return number


def _round_qty(value: float) -> float | int:
    if abs(value - round(value)) < QTY_EPSILON:
        return int(round(value))
    return round(value, 3)


def _new_event_id() -> str:
    return f"ev_{uuid.uuid4().hex[:12]}"


# --------------------------------------------------------------------------- #
# build_diff：识别结果 × active 库存
# --------------------------------------------------------------------------- #

def _merge_recognized(recognized: list[dict]) -> list[dict]:
    """同名识别项合并（视觉模型常把同一样食材报两行），置信度取最高。"""
    merged: dict[str, dict] = {}
    for raw in recognized or []:
        if not isinstance(raw, dict):
            continue
        name = _norm_text(raw.get("name"))
        if not name:
            continue
        qty = max(0.0, _as_float(raw.get("qty"), DEFAULT_QTY))
        confidence = min(1.0, max(0.0, _as_float(raw.get("confidence"), DEFAULT_CONFIDENCE)))
        item_id = raw.get("item_id") or None
        entry = merged.get(name)
        if entry is None:
            merged[name] = {
                "name": name,
                "qty": qty,
                "unit": _norm_text(raw.get("unit")),
                "confidence": confidence,
                "item_id": item_id,
            }
            continue
        entry["qty"] = round(entry["qty"] + qty, 3)
        entry["confidence"] = max(entry["confidence"], confidence)
        entry["unit"] = entry["unit"] or _norm_text(raw.get("unit"))
        entry["item_id"] = entry["item_id"] or item_id
    return list(merged.values())


def _index_inventory(inventory: list[dict]) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    by_item: dict[str, list[dict]] = {}
    by_name: dict[str, list[dict]] = {}
    for row in inventory or []:
        name = _norm_text(row.get("name"))
        if name:
            by_name.setdefault(name, []).append(row)
        item_id = row.get("item_id")
        if item_id:
            by_item.setdefault(str(item_id), []).append(row)
    return by_item, by_name


def _match_rows(
    rec: dict,
    by_item: dict[str, list[dict]],
    by_name: dict[str, list[dict]],
) -> list[dict]:
    """先 item_id，再同名，最后名称互含（名称已在 API 层按别名表折算成标准名）。"""
    if rec.get("item_id"):
        rows = by_item.get(str(rec["item_id"]))
        if rows:
            return list(rows)

    name = rec["name"]
    rows = by_name.get(name)
    if rows:
        return list(rows)

    containing: list[dict] = []
    for other_name, other_rows in by_name.items():
        if name and (name in other_name or other_name in name):
            containing.extend(other_rows)
    if not containing:
        return []

    # 互含可能命中多个名称：取最长的那个名称组（「番茄」优先于「番茄酱」）
    longest = max(len(_norm_text(row.get("name"))) for row in containing)
    return [row for row in containing if len(_norm_text(row.get("name"))) == longest]


def _sort_by_expiry(rows: list[dict]) -> list[dict]:
    """同名多条库存按到期先后匹配（先到期的先被识别数量覆盖）。"""
    return sorted(
        rows,
        key=lambda row: (
            str(row.get("expires_at") or EMPTY_EXPIRY_ORDER),
            str(row.get("id") or ""),
        ),
    )


def _missing_entry(row: dict) -> dict:
    return {
        "inventory_id": row.get("id"),
        "name": row.get("name"),
        "qty": _round_qty(max(0.0, _as_float(row.get("qty"), 0.0))),
        "unit": row.get("unit"),
        "days_left": days_left(row.get("expires_at")),
    }


def _is_unclear(name: str) -> bool:
    lowered = name.lower()
    return any(hint in lowered for hint in UNCLEAR_HINTS)


def build_diff(
    recognized: list[dict],
    inventory: list[dict],
    *,
    low_confidence: float = LOW_CONFIDENCE,
) -> dict:
    """比对识别结果与 active 库存，返回 {missing,reduced,added,suspect,warnings}（只读，不改库）。"""
    warnings: list[str] = []
    missing: list[dict] = []
    reduced: list[dict] = []
    added: list[dict] = []
    suspect: list[dict] = []

    recs = _merge_recognized(recognized)
    if not recs:
        # 空识别不能当成「全部没了」：一律保留，只提示（规则 2）
        warnings.append(
            EMPTY_RECOGNITION_TEMPLATE.format(count=len(inventory or []))
            if inventory
            else EMPTY_RECOGNITION_NO_STOCK
        )
        return {"missing": [], "reduced": [], "added": [], "suspect": [], "warnings": warnings}

    by_item, by_name = _index_inventory(inventory)
    matched_ids: set[str] = set()

    for rec in recs:
        rows = [
            row
            for row in _match_rows(rec, by_item, by_name)
            if str(row.get("id")) not in matched_ids
        ]
        unclear = _is_unclear(rec["name"])
        low = rec["confidence"] < low_confidence

        if unclear or low:
            reason = (
                REASON_UNCLEAR
                if unclear
                else REASON_LOW_CONFIDENCE.format(confidence=rec["confidence"])
            )
            if rows:
                for row in rows:
                    matched_ids.add(str(row.get("id")))
                    suspect.append(
                        {
                            "inventory_id": row.get("id"),
                            "name": row.get("name"),
                            "reason": reason,
                        }
                    )
            else:
                suspect.append({"inventory_id": None, "name": rec["name"], "reason": reason})
            warnings.append(
                SUSPECT_WARNING_TEMPLATE.format(name=rec["name"], confidence=rec["confidence"])
            )
            continue

        if not rows:
            # 库存里没有这条 → 识别到的「多出来的」食材
            added.append(
                {
                    "name": rec["name"],
                    "qty": _round_qty(max(rec["qty"], 0.0)),
                    "unit": rec["unit"] or DEFAULT_UNIT,
                    "confidence": rec["confidence"],
                    "matched": bool(rec.get("item_id")),
                }
            )
            continue

        remaining = rec["qty"]
        multi_batch = len(rows) > 1
        for row in _sort_by_expiry(rows):
            matched_ids.add(str(row.get("id")))
            stock_qty = max(0.0, _as_float(row.get("qty"), 0.0))
            covered = min(remaining, stock_qty)
            remaining = round(remaining - covered, 6)
            if covered >= stock_qty - QTY_EPSILON:
                continue  # 数量对得上，keep
            if covered <= QTY_EPSILON:
                if multi_batch:
                    # 同名多批：照片分不清是哪一批，不能武断判「不见了」
                    suspect.append(
                        {
                            "inventory_id": row.get("id"),
                            "name": row.get("name"),
                            "reason": "同名食材有多批，照片无法判断少的是哪一批，请手动确认",
                        }
                    )
                else:
                    missing.append(_missing_entry(row))
                continue
            reduced.append(
                {
                    "inventory_id": row.get("id"),
                    "name": row.get("name"),
                    "from_qty": _round_qty(stock_qty),
                    "to_qty": _round_qty(covered),
                    "unit": row.get("unit"),
                }
            )

        if remaining > QTY_EPSILON:
            stock_total = sum(max(0.0, _as_float(row.get("qty"), 0.0)) for row in rows)
            warnings.append(
                SURPLUS_WARNING_TEMPLATE.format(
                    name=rec["name"],
                    recognized=_round_qty(rec["qty"]),
                    stock=_round_qty(stock_total),
                    unit=rec["unit"] or "",
                )
            )

    # 没被任何识别结果解释到的 active 行 → missing（照片里不见了）
    for row in inventory or []:
        if str(row.get("id")) not in matched_ids:
            missing.append(_missing_entry(row))

    missing.sort(key=lambda row: (int(row.get("days_left") or 0), str(row.get("name") or "")))
    reduced.sort(key=lambda row: str(row.get("name") or ""))
    added.sort(key=lambda row: str(row.get("name") or ""))
    suspect.sort(key=lambda row: (str(row.get("name") or ""), str(row.get("inventory_id") or "")))
    return {
        "missing": missing,
        "reduced": reduced,
        "added": added,
        "suspect": suspect,
        "warnings": warnings,
    }


# --------------------------------------------------------------------------- #
# apply：先全量校验 → 单事务落库 → 幂等 + 留痕
# --------------------------------------------------------------------------- #

def _fingerprint(request_id: str, action: str, inventory_id: str | None, target: Any) -> str:
    """幂等指纹 = request_id + 动作 + 目标值。

    request_id 决定「是不是同一次对账」：同一 request_id 重复提交命中同一条就跳过，
    不同 request_id 的相同动作视为「用户确实又做了一次」，正常生效。
    """
    return f"{request_id}|{action}|{inventory_id or '-'}|{target}"


def _ledger_exists(fingerprint: str) -> bool:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM reconcile_applied WHERE fingerprint = ?", (fingerprint,)
        ).fetchone()
    finally:
        conn.close()
    return row is not None


def _ledger_add(
    request_id: str,
    fingerprint: str,
    inventory_id: str | None,
    action: str,
    detail: dict,
) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO reconcile_applied"
            "(fingerprint,request_id,inventory_id,action,detail,created_at) VALUES(?,?,?,?,?,?)",
            (
                fingerprint,
                request_id,
                inventory_id,
                action,
                json.dumps(detail, ensure_ascii=False),
                now_iso(),
            ),
        )
        conn.commit()  # 事务内由外层统一提交（见 db.conn.transaction）
    finally:
        conn.close()


def _insert_event(actions: list[dict], source: dict) -> None:
    """真正改到数据就写一条 events(kind=reconcile)，可回溯「哪次核验改了什么」。

    与业务改动同事务：写失败让整批回滚，不留下「改了数据但没留痕」的状态。
    """
    if not actions:
        return
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO events(id,kind,payload,created_at) VALUES(?,?,?,?)",
            (
                _new_event_id(),
                EVENT_KIND,
                json.dumps(
                    {"source": EVENT_SOURCE, **source, "actions": actions},
                    ensure_ascii=False,
                ),
                now_iso(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _write_reduction(
    inv_id: str,
    target_qty: float,
    current_qty: float,
    current_grams: float,
) -> tuple[bool, float]:
    """按比例把 qty 收到 target_qty，grams 同步按比例缩（不重新乘 avg_grams）。

    只在 active 行上生效：返回 (是否改到数据, 新克数)，状态已变则由调用方按跳过处理。
    """
    new_grams = (
        round(current_grams * (target_qty / current_qty), 3)
        if current_qty > QTY_EPSILON
        else current_grams
    )
    conn = get_conn()
    try:
        cursor = conn.execute(
            "UPDATE inventory SET qty = ?, grams = ?, verified_at = ?"
            " WHERE id = ? AND status = ?",
            (target_qty, new_grams, now_iso(), inv_id, STATUS_ACTIVE),
        )
        conn.commit()
        changed = int(cursor.rowcount or 0) > 0
    finally:
        conn.close()
    return changed, new_grams


def _as_list(payload: dict, key: str) -> list[dict]:
    value = payload.get(key)
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise AppError("invalid_payload", f"{key} 必须是数组", 400)
    return [row for row in value if isinstance(row, dict)]


def _load_row(inv_id: str) -> dict | None:
    """读一条库存；不存在返回 None（前端拿旧 id 提交时整批不应 404 中断）。"""
    try:
        return inventory_domain.get_inventory(inv_id)
    except AppError as exc:
        if getattr(exc, "status", 500) == 404:
            return None
        raise


def _stamp_active_verified(timestamp: str) -> int:
    """对账 apply = 用户确认了这次核验：把 active 行统一盖一次核验时间（只动时间戳）。

    不盖的话，「拍完对账」之后没被改动过的食材会永远停在 stale>3，提示永不消失。
    """
    conn = get_conn()
    try:
        cursor = conn.execute(
            "UPDATE inventory SET verified_at = ? WHERE status = ?",
            (timestamp, STATUS_ACTIVE),
        )
        conn.commit()
        return int(cursor.rowcount or 0)
    finally:
        conn.close()


def _resolve_request_id(payload: dict) -> str:
    """一次 apply = 一个 request_id；缺省时服务端生成（只在该请求内去重）。"""
    raw = _norm_text(payload.get("request_id"))
    if not raw:
        return f"{REQUEST_ID_PREFIX}{uuid.uuid4().hex[:12]}"
    if len(raw) > REQUEST_ID_MAX_LENGTH:
        raise AppError(
            "invalid_request_id",
            f"request_id 不能超过 {REQUEST_ID_MAX_LENGTH} 个字符",
            400,
        )
    return raw


def _resolve_checked_at(value: Any, warnings: list[str]) -> str:
    """核验时间必须是合法时间（契约 §6.14）。

    - 非法 / 缺省 → 用服务端当前时间（不 400：apply 是用户已确认的落库动作，
      客户端时钟或格式问题不该让整批改动失败），并给一条 warning
    - 未来时间 → 收敛到当前时间（否则 stale_days 永远 0 = 假装新鲜）
    """
    raw = _norm_text(value)
    if not raw:
        return now_iso()
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        warnings.append(CHECKED_AT_INVALID_TEMPLATE.format(value=raw))
        return now_iso()

    current = datetime.now().astimezone()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=current.tzinfo)
    if parsed > current:
        warnings.append(CHECKED_AT_FUTURE_TEMPLATE.format(value=raw))
        return current.isoformat(timespec="seconds")
    return parsed.isoformat(timespec="seconds")


def _as_number(value: Any, label: str) -> float:
    """数量字段必须是有限数字，否则整批 400（不猜、不静默当 0）。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise AppError("invalid_qty", f"{label} 的数量必须是数字", 400)
    if number != number or number in (float("inf"), float("-inf")):
        raise AppError("invalid_qty", f"{label} 的数量必须是有限数字", 400)
    return number


def _opt_grams(value: Any, label: str) -> float | None:
    """missing 项的 grams：缺省 / 0 表示「全部」，负数或非数字直接 400。"""
    if value in (None, ""):
        return None
    grams = _as_number(value, label)
    if grams < 0:
        raise AppError("invalid_grams", f"{label} 的 grams 不能为负", 400)
    return grams if grams > 0 else None


def apply(payload: dict) -> dict:
    """把用户确认的对账动作落库；返回契约 §6.13 的 {applied, warnings}（额外带 skipped）。

    两阶段：先全量校验（只读），全部通过后再在一个事务里落库。
    任何一项非法 → 整批 400，数据库不留半截数据（契约 §6.13 规则 3/4/5）。
    """
    ensure_schema()
    missing = _as_list(payload, "missing")
    reduced = _as_list(payload, "reduced")
    added_rows = _as_list(payload, "added")

    applied = {"discarded": 0, "consumed": 0, "updated": 0, "added": 0}
    skipped = 0
    warnings: list[str] = []

    request_id = _resolve_request_id(payload)
    checked_at = _resolve_checked_at(payload.get("checked_at"), warnings)
    source = {
        "image_id": payload.get("image_id"),
        "request_id": request_id,
        "checked_at": checked_at,
    }

    # ---- 第 1 阶段：全量校验（只读；任何异常都在落库之前抛出）----
    ops: list[dict] = []
    seen: set[str] = set()
    used_inventory: set[str] = set()

    for index, item in enumerate(missing):
        label = f"missing[{index}]"
        inv_id = _norm_text(item.get("inventory_id"))
        if not inv_id:
            raise AppError("invalid_inventory_id", "missing 项缺少 inventory_id", 400)
        action = _norm_text(item.get("action") or ACTION_KEEP).lower()
        if action not in VALID_ACTIONS:
            raise AppError(
                "invalid_action",
                f"missing.action 只能是 {'/'.join(VALID_ACTIONS)} 之一",
                400,
            )
        if action == ACTION_KEEP:
            skipped += 1
            continue

        grams = _opt_grams(item.get("grams"), label)
        reason = None
        if action == ACTION_DISCARDED:
            reason = _norm_text(item.get("reason")) or DEFAULT_DISCARD_REASON
            if reason not in DISCARD_REASONS:
                raise AppError(
                    "invalid_reason",
                    f"丢弃原因必须是 {'/'.join(DISCARD_REASONS)} 之一",
                    400,
                )

        row = _load_row(inv_id)
        name = str(row["name"]) if row is not None else inv_id

        if inv_id in used_inventory:
            skipped += 1
            warnings.append(DUPLICATE_IN_BATCH_TEMPLATE.format(name=name))
            continue
        used_inventory.add(inv_id)

        fingerprint = _fingerprint(
            request_id, action, inv_id, "" if grams is None else _round_qty(grams)
        )
        if fingerprint in seen or _ledger_exists(fingerprint):
            skipped += 1
            warnings.append(SKIP_ALREADY_APPLIED_TEMPLATE.format(name=name))
            continue
        seen.add(fingerprint)

        if row is None:
            skipped += 1
            warnings.append(SKIP_MISSING_ROW_TEMPLATE.format(inventory_id=inv_id))
            continue
        if row["status"] != STATUS_ACTIVE:
            skipped += 1
            warnings.append(
                SKIP_NOT_ACTIVE_TEMPLATE.format(name=row["name"], status=row["status"])
            )
            continue
        if action == ACTION_DISCARDED and not item.get("reason"):
            warnings.append(
                DEFAULT_REASON_WARNING_TEMPLATE.format(name=row["name"], reason=reason)
            )

        ops.append(
            {
                "kind": "missing",
                "action": action,
                "inventory_id": inv_id,
                "name": row["name"],
                "grams": grams,
                "reason": reason,
                "fingerprint": fingerprint,
                "before_qty": _as_float(row.get("qty"), 0.0),
                "before_grams": _as_float(row.get("grams"), 0.0),
            }
        )

    for index, item in enumerate(reduced):
        label = f"reduced[{index}]"
        inv_id = _norm_text(item.get("inventory_id"))
        if not inv_id:
            raise AppError("invalid_inventory_id", "reduced 项缺少 inventory_id", 400)
        target_qty = _as_number(item.get("qty"), label)

        row = _load_row(inv_id)
        if row is None:
            skipped += 1
            warnings.append(SKIP_MISSING_ROW_TEMPLATE.format(inventory_id=inv_id))
            continue
        if inv_id in used_inventory:
            skipped += 1
            warnings.append(DUPLICATE_IN_BATCH_TEMPLATE.format(name=row["name"]))
            continue
        used_inventory.add(inv_id)
        if row["status"] != STATUS_ACTIVE:
            skipped += 1
            warnings.append(
                SKIP_NOT_ACTIVE_TEMPLATE.format(name=row["name"], status=row["status"])
            )
            continue

        current_qty = max(0.0, _as_float(row.get("qty"), 0.0))
        unit = row.get("unit") or ""

        if target_qty <= QTY_EPSILON:
            skipped += 1
            warnings.append(SKIP_ZERO_QTY_TEMPLATE.format(name=row["name"]))
            continue
        if target_qty > current_qty + QTY_EPSILON:
            skipped += 1
            warnings.append(
                SKIP_TARGET_TOO_LARGE_TEMPLATE.format(
                    name=row["name"],
                    target=_round_qty(target_qty),
                    current=_round_qty(current_qty),
                    unit=unit,
                )
            )
            continue
        if abs(target_qty - current_qty) <= QTY_EPSILON:
            skipped += 1
            warnings.append(
                SKIP_SAME_QTY_TEMPLATE.format(
                    name=row["name"], qty=_round_qty(current_qty), unit=unit
                )
            )
            continue

        fingerprint = _fingerprint(request_id, "reduced", inv_id, _round_qty(target_qty))
        if fingerprint in seen or _ledger_exists(fingerprint):
            skipped += 1
            warnings.append(SKIP_ALREADY_APPLIED_TEMPLATE.format(name=row["name"]))
            continue
        seen.add(fingerprint)

        ops.append(
            {
                "kind": "reduced",
                "inventory_id": inv_id,
                "name": row["name"],
                "target_qty": target_qty,
                "current_qty": current_qty,
                "before_grams": _as_float(row.get("grams"), 0.0),
                "fingerprint": fingerprint,
            }
        )

    for index, item in enumerate(added_rows):
        label = f"added[{index}]"
        name = _norm_text(item.get("name"))
        if not name:
            raise AppError("invalid_item", "added 项缺少 name", 400)
        qty = _as_number(item.get("qty", DEFAULT_QTY), label)
        unit = _norm_text(item.get("unit")) or None
        if qty <= QTY_EPSILON:
            skipped += 1
            warnings.append(SKIP_ZERO_ADD_TEMPLATE.format(name=name))
            continue

        fingerprint = _fingerprint(
            request_id, "added", None, f"{name}|{_round_qty(qty)}|{unit or ''}"
        )
        if fingerprint in seen or _ledger_exists(fingerprint):
            skipped += 1
            warnings.append(SKIP_ALREADY_APPLIED_TEMPLATE.format(name=name))
            continue
        seen.add(fingerprint)

        ops.append(
            {
                "kind": "added",
                "name": name,
                "qty": qty,
                "unit": unit,
                "fingerprint": fingerprint,
            }
        )

    # ---- 第 2 阶段：整批落库（同一连接 + 单事务，异常整批回滚）----
    actions: list[dict] = []
    verified = 0
    with transaction():
        for op in ops:
            kind = op["kind"]

            if kind == "added":
                result = inventory_domain.add_items(
                    {
                        "image_id": payload.get("image_id"),
                        "items": [{"name": op["name"], "qty": op["qty"], "unit": op["unit"]}],
                    }
                )
                added_count = int(result.get("added") or 0)
                applied["added"] += added_count
                detail = {
                    "inventory_id": (result.get("ids") or [None])[0],
                    "name": op["name"],
                    "action": "added",
                    "qty": _round_qty(op["qty"]),
                    "unit": op["unit"],
                }
                _ledger_add(request_id, op["fingerprint"], detail["inventory_id"], "added", detail)
                if added_count:
                    actions.append(detail)
                continue

            if kind == "reduced":
                changed, new_grams = _write_reduction(
                    op["inventory_id"], op["target_qty"], op["current_qty"], op["before_grams"]
                )
                if not changed:  # 事务内状态已变（理论上第 1 阶段已挡住）
                    skipped += 1
                    warnings.append(SKIP_STATE_CHANGED_TEMPLATE.format(name=op["name"]))
                    continue
                applied["updated"] += 1
                detail = {
                    "inventory_id": op["inventory_id"],
                    "name": op["name"],
                    "action": "reduced",
                    "from_qty": _round_qty(op["current_qty"]),
                    "to_qty": _round_qty(op["target_qty"]),
                    "grams_before": round(op["before_grams"], 2),
                    "grams_after": new_grams,
                }
                _ledger_add(request_id, op["fingerprint"], op["inventory_id"], "reduced", detail)
                actions.append(detail)
                continue

            if op["action"] == ACTION_DISCARDED:
                result = inventory_domain.discard(
                    op["inventory_id"], op["reason"], op["grams"]
                )
                applied["discarded"] += 1
                detail = {
                    "inventory_id": op["inventory_id"],
                    "name": op["name"],
                    "action": ACTION_DISCARDED,
                    "reason": op["reason"],
                    "from_qty": _round_qty(op["before_qty"]),
                    "to_qty": result.get("qty"),
                    "grams_before": round(op["before_grams"], 2),
                    "discarded_grams": result.get("discarded_grams"),
                    "carbon_kg": result.get("carbon_kg"),
                }
            else:  # consumed
                result = inventory_domain.consume(op["inventory_id"], op["grams"])
                applied["consumed"] += 1
                detail = {
                    "inventory_id": op["inventory_id"],
                    "name": op["name"],
                    "action": ACTION_CONSUMED,
                    "from_qty": _round_qty(op["before_qty"]),
                    "to_qty": result.get("qty"),
                    "grams_before": round(op["before_grams"], 2),
                    "consumed_grams": result.get("consumed_grams"),
                }
            _ledger_add(request_id, op["fingerprint"], op["inventory_id"], op["action"], detail)
            actions.append(detail)

        # 留痕与业务改动同事务：要么都落库，要么一起回滚
        _insert_event(actions, source)

        # 用户点了 apply = 确认这次核验结果：active 行统一盖时间戳（含没改动的 keep 项）
        if missing or reduced or added_rows:
            verified = _stamp_active_verified(checked_at)

    if not actions and not warnings:
        warnings.append(NOTHING_APPLIED_WARNING)
    logger.info(
        "对账落地：request_id=%s discarded=%d consumed=%d updated=%d added=%d skipped=%d 核验行=%d",
        request_id,
        applied["discarded"],
        applied["consumed"],
        applied["updated"],
        applied["added"],
        skipped,
        verified,
    )
    return {
        "request_id": request_id,
        "checked_at": checked_at,
        "applied": applied,
        "skipped": skipped,
        "verified": verified,
        "warnings": warnings,
    }

