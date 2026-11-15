"""小票识别（契约 §6.11，批量入库的前置步骤）。

- 复用 `app/api/capture.py` 的视觉链路与响应口径（延迟导入，避免与 capture 循环引用）
- 商品名先精确、再别名表（`app/data/aliases.json`）、最后模糊匹配食材库
- **价格认不出就给 `null`，绝不编造**；`total_price` 只在小票上有合计时给数
- 日期/合计解析失败只写 `warnings`，不阻断识别
- 识别结果不入库，确认后仍走 `POST /api/inventory`（`added_at` 可用 `purchased_at`）
"""

from __future__ import annotations

import base64
import json
import logging
import math
import re
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, UploadFile

from app import config
from app.db.conn import get_conn
from app.domain.inventory import DEFAULT_SHELF_LIFE_DAYS, find_item, now_iso, today
from app.domain.tools_registry import AppError, resolve_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/receipt", tags=["capture"])

UPLOAD_DIR = config.UPLOAD_DIR
ALIAS_FILE = config.DATA_DIR / "aliases.json"
FIXTURES_DIR = config.FIXTURES_DIR
FIXTURE_FILE = FIXTURES_DIR / "receipt.json"

LOW_CONFIDENCE = config.CONFIDENCE_WARN_THRESHOLD
DEFAULT_UNIT = "份"
MAX_PRICE = 100000.0
MIN_YEAR = 2000
MAX_YEAR = 2100
PROVIDER_WARNING_LIMIT = 3
# 小票里商品名/数量/价格的常见中英文字段（视觉模型输出姿势不固定）
NAME_KEYS = ("name", "product", "商品", "商品名", "品名", "名称")
QTY_KEYS = ("qty", "quantity", "数量", "count")
UNIT_KEYS = ("unit", "单位", "规格")
PRICE_KEYS = ("price", "subtotal", "小计", "金额", "单价", "unit_price")
DATE_KEYS = ("purchased_at", "date", "日期", "购买日期", "交易日期")
TOTAL_KEYS = ("total_price", "total", "合计", "总计", "amount")

RECEIPT_PROMPT = (
    "你是小票识别助手。请把图片里的小票、外卖单或购物截图逐行识别成 JSON："
    '{"items":[{"name":"西兰花","qty":1,"unit":"颗","price":6.5,"confidence":0.88}],'
    '"purchased_at":"2026-11-15","total_price":23.6}。'
    "name 用商品常见中文名（去掉品牌与规格）；qty 是数量；unit 是单位；"
    "price 是该行实付金额（单位元）；confidence 是 0~1 的置信度。"
    "price 认不出来必须输出 null，绝对不要猜；小票上没有合计 total_price 就给 null；"
    "日期看不清 purchased_at 就给 null；不确定就调低 confidence，不要编造。"
    '为兼容只取 items 的解析，请在每一行额外带上 "purchased_at" 与 "total_price"（整张小票的值，认不出给 null）。'
)

LOW_CONF_WARNING = "第 {index} 项「{name}」识别置信度较低（{confidence}），请确认"
UNMATCHED_WARNING = "「{name}」不在食材库，已标记未匹配（不计入碳账）"
PRICE_MISSING_WARNING = "第 {index} 项「{name}」未识别到价格，price 置为 null（不编造）"
PRICE_NO_ANY_WARNING = "小票上没有识别到价格，price 已全部置为 null（不编造）"
PRICE_BAD_WARNING = "第 {index} 项「{name}」价格无法解析（{raw}），price 置为 null"
TOTAL_BAD_WARNING = "小票合计无法解析（{raw}），total_price 置为 null"
DATE_BAD_WARNING = "小票日期无法解析（{raw}），到期日按今天推算"
DATE_FUTURE_WARNING = "小票日期 {value} 晚于今天，到期日按今天推算"
DEGRADE_WARNING = "已降级：视觉模型不可用，返回内置样例，请务必人工核对"
EMPTY_ITEMS_MESSAGE = "没有从小票里识别出商品条目，请换一张更清晰的图片"

_DATE_PATTERN = re.compile(r"(\d{4})\D{1,4}(\d{1,2})\D{1,4}(\d{1,2})")
_NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")
_ALIASES: dict[str, str] | None = None


def _shared():
    """拍照识别链路的公共实现（延迟导入，避免 capture.py ↔ receipt.py 循环引用）。"""
    from app.api import capture

    return capture


# --------------------------------------------------------------------------- #
# 解析工具
# --------------------------------------------------------------------------- #

def _pick(raw: Any, keys: tuple[str, ...]) -> Any:
    if not isinstance(raw, dict):
        return None
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return None


def _parse_number(value: Any) -> float | None:
    """把 ``6.5`` / ``"￥6.50"`` / ``"1,234.5 元"`` 解析成金额；失败返回 None。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip().replace(",", "")
        match = _NUMBER_PATTERN.search(text)
        if not match:
            return None
        try:
            number = float(match.group())
        except ValueError:
            return None
    if not math.isfinite(number) or number < 0 or number > MAX_PRICE:
        return None
    return round(number, 2)


def _parse_date(value: Any) -> str | None:
    """支持 ``2026-11-15`` / ``2026/11/15`` / ``2026年11月15日``，格式不合法返回 None。"""
    if value in (None, ""):
        return None
    match = _DATE_PATTERN.search(str(value).strip())
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    if not MIN_YEAR <= year <= MAX_YEAR:
        return None
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _alias_map() -> dict[str, str]:
    """别名表（`_说明` 之类的元数据键跳过），读不到就当空表。"""
    global _ALIASES
    if _ALIASES is None:
        try:
            data = json.loads(ALIAS_FILE.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            logger.warning("别名表读取失败：%s", ALIAS_FILE)
            data = {}
        _ALIASES = {
            str(key): str(value)
            for key, value in data.items()
            if isinstance(value, str) and not str(key).startswith("_")
        }
    return _ALIASES


def _match_item(conn, name: str, *, fuzzy: bool = True) -> tuple[str, Any]:
    """先精确、再别名、最后（可选）模糊包含；返回 (标准名, items 行或 None)。

    ``fuzzy=False`` 供库存对账使用：对账只认精确名/别名，
    否则「番茄酱」会被映射成「番茄」，把调味酱当成番茄减量。
    """
    row = conn.execute("SELECT * FROM items WHERE name = ?", (name,)).fetchone()
    if row is not None:
        return row["name"], row
    alias = _alias_map().get(name)
    if alias:
        row = conn.execute("SELECT * FROM items WHERE name = ?", (alias,)).fetchone()
        if row is not None:
            return row["name"], row
    if not fuzzy:
        return name, None
    row = find_item(conn, name)
    if row is not None:
        return row["name"], row
    return name, None


def _merge_keys(raw: dict) -> dict:
    """把中文字段名折成 capture._normalize 认得的键。"""
    merged = dict(raw)
    for keys, target in (
        (NAME_KEYS, "name"),
        (QTY_KEYS, "qty"),
        (UNIT_KEYS, "unit"),
    ):
        if merged.get(target) in (None, ""):
            value = _pick(raw, keys)
            if value not in (None, ""):
                merged[target] = value
    return merged


def _load_fixture() -> dict | None:
    path = FIXTURE_FILE if FIXTURE_FILE.is_file() else next(
        iter(sorted(FIXTURES_DIR.glob("receipt*.json"))), None
    )
    if path is None:
        return None
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        logger.warning("小票 fixture 读取失败：%s", path)
        return None
    return data if isinstance(data, dict) else None


# --------------------------------------------------------------------------- #
# 端点
# --------------------------------------------------------------------------- #

@router.post("")
async def recognize_receipt(file: UploadFile = File(...)) -> dict:
    content = await file.read()
    if not content:
        raise AppError("empty_file", "上传的图片为空", 400)
    if len(content) > config.MAX_UPLOAD_BYTES:
        raise AppError(
            "payload_too_large",
            f"图片超过 {_shared()._upload_limit_label()}，请压缩后再传",
            413,
        )

    shared = _shared()
    mime = (file.content_type or "image/jpeg").lower()
    ext = shared.EXT_BY_MIME.get(mime) or Path(file.filename or "").suffix or ".jpg"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    image_id = f"img_{uuid.uuid4().hex[:12]}"
    saved = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    saved.write_bytes(content)

    warnings: list[str] = []
    provider = resolve_provider(None)
    data: dict[str, Any] = {}
    provider_ok = False

    if provider is not None:
        try:
            encoded = base64.b64encode(content).decode("ascii")
            raw = await provider.chat_vision(encoded, mime, RECEIPT_PROMPT)
            if isinstance(raw, dict):
                data = raw
                provider_ok = True
        except Exception as exc:
            logger.warning("小票识别失败：%s", exc)

    raw_items = shared._flatten(data) if data else []
    if not raw_items and not provider_ok:
        # 视觉模型不可用才拿内置样例兜底；模型正常但没识别出条目属于用户图片问题
        fixture = _load_fixture()
        if fixture is None:
            raise AppError("vision_unavailable", "小票识别服务不可用，请稍后重试", 502)
        data = fixture
        raw_items = shared._flatten(data)
        warnings.append(DEGRADE_WARNING)
    if not raw_items:
        raise AppError("receipt_empty", EMPTY_ITEMS_MESSAGE, 422)

    provider_warnings = data.get("warnings")
    if isinstance(provider_warnings, list):
        for item in provider_warnings[:PROVIDER_WARNING_LIMIT]:
            if isinstance(item, str) and item.strip():
                warnings.append(item.strip())

    # ---- 小票级字段：日期与合计（认不出就 null，不编造） ----
    date_raw = _pick(data, DATE_KEYS)
    if date_raw in (None, ""):
        for row in raw_items:
            date_raw = _pick(row, DATE_KEYS)
            if date_raw not in (None, ""):
                break
    total_raw = _pick(data, TOTAL_KEYS)
    if total_raw in (None, ""):
        for row in raw_items:
            total_raw = _pick(row, TOTAL_KEYS)
            if total_raw not in (None, ""):
                break

    purchased_at = _parse_date(date_raw)
    if date_raw not in (None, "") and purchased_at is None:
        warnings.append(DATE_BAD_WARNING.format(raw=date_raw))
    expires_base = today()
    if purchased_at is not None:
        parsed = date.fromisoformat(purchased_at)
        if parsed > today():
            warnings.append(DATE_FUTURE_WARNING.format(value=purchased_at))
        else:
            expires_base = parsed

    total_price = _parse_number(total_raw)
    if total_raw not in (None, "") and total_price is None:
        warnings.append(TOTAL_BAD_WARNING.format(raw=total_raw))

    # ---- 商品行：名称匹配 + 价格 + 到期日 ----
    items: list[dict] = []
    missing_price: list[tuple[int, str]] = []
    conn = get_conn()
    try:
        for index, row in enumerate(raw_items, start=1):
            normalized = shared._normalize(_merge_keys(row))
            if not normalized["name"]:
                continue
            raw_name = normalized["name"]
            name, item = _match_item(conn, raw_name)
            shelf = (
                int(item["shelf_life_days"] or DEFAULT_SHELF_LIFE_DAYS)
                if item is not None
                else DEFAULT_SHELF_LIFE_DAYS
            )
            unit = normalized["unit"] or (item["unit"] if item is not None and item["unit"] else DEFAULT_UNIT)
            confidence = normalized["confidence"]

            price_raw = _pick(row, PRICE_KEYS)
            price = _parse_number(price_raw)
            if price is None:
                if price_raw not in (None, ""):
                    warnings.append(
                        PRICE_BAD_WARNING.format(index=index, name=name, raw=price_raw)
                    )
                else:
                    missing_price.append((index, name))

            items.append(
                {
                    "name": name,
                    "qty": normalized["qty"],
                    "unit": unit,
                    "price": price,
                    "confidence": confidence,
                    "item_id": item["id"] if item is not None else None,
                    "shelf_life_days": shelf,
                    "expires_at": (expires_base + timedelta(days=shelf)).isoformat(),
                    "matched": item is not None,
                }
            )
            if confidence < LOW_CONFIDENCE:
                warnings.append(
                    LOW_CONF_WARNING.format(index=index, name=name, confidence=confidence)
                )
            if item is None:
                warnings.append(UNMATCHED_WARNING.format(name=name))

        if missing_price and len(missing_price) == len(items):
            warnings.append(PRICE_NO_ANY_WARNING)
        else:
            for index, name in missing_price:
                warnings.append(PRICE_MISSING_WARNING.format(index=index, name=name))

        conn.execute(
            "INSERT INTO images(id,path,created_at,recognized) VALUES(?,?,?,?)",
            (
                image_id,
                shared._stored_path(saved),
                now_iso(),
                json.dumps(
                    {
                        "items": items,
                        "purchased_at": purchased_at,
                        "total_price": total_price,
                        "warnings": warnings,
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "image_id": image_id,
        "items": items,
        "purchased_at": purchased_at,
        "total_price": total_price,
        "warnings": warnings,
    }
