"""库存对账 API（契约 §6.13 / §6.14）。

- `POST /api/inventory/reconcile`：multipart 冰箱照片 → 识别 → 与 active 库存比对
  （只读，改动必须再走 `/apply`，契约 §6.13 规则 2）
- `POST /api/inventory/reconcile/apply`：按用户确认的动作落库（幂等 + 写 events）

视觉链路直接复用 `app/api/capture.py`（归一化 / fixture 降级 / 上传上限），
商品名折算复用 `app/api/receipt.py` 的别名表匹配，都不复制实现。
"""

from __future__ import annotations

import base64
import json
import logging
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel, Field

from app import config
from app.db.conn import ensure_schema, get_conn
from app.domain import inventory as inventory_domain
from app.domain import reconcile as reconcile_domain
from app.domain.inventory import now_iso
from app.domain.tools_registry import AppError, resolve_provider

logger = logging.getLogger(__name__)

# 挂在 /api/inventory 下（父 router 负责前缀），include 在 app/api/inventory.py 末尾
router = APIRouter(prefix="/reconcile", tags=["inventory"])

UPLOAD_DIR = config.UPLOAD_DIR
DEFAULT_QTY = 1.0
DEGRADE_WARNING = "已降级：视觉模型不可用，返回内置样例，请务必人工核对"

RECONCILE_PROMPT = (
    "你是冰箱库存核对助手。请数清图片里能看清的每一种食材，输出 JSON："
    '{"items":[{"name":"鸡蛋","qty":6,"unit":"个","confidence":0.92}]}。'
    "name 用常见中文名；qty 是数出来的数量（不是猜测）；unit 是单位；confidence 是 0~1 的置信度。"
    "看不清是什么就在 name 前加「看不清：」并把 confidence 调到 0.5 以下；"
    "拿不准数量就把 confidence 调低。绝对不要编造看不见的食材。"
)


class MissingActionIn(BaseModel):
    """missing 项的默认动作是 keep（契约 §6.13 规则 2）。"""

    inventory_id: str = Field(min_length=1)
    action: Literal["consumed", "discarded", "keep"] = "keep"
    reason: str | None = None
    grams: float | None = Field(default=None, gt=0)


class ReducedIn(BaseModel):
    inventory_id: str = Field(min_length=1)
    qty: float = Field(gt=0)


class AddedIn(BaseModel):
    name: str = Field(min_length=1)
    qty: float = Field(default=DEFAULT_QTY, gt=0)
    unit: str | None = None


class ReconcileApplyIn(BaseModel):
    image_id: str | None = None
    checked_at: str | None = None
    # 契约 §6.13 规则 4：一次请求的客户端标识；缺省由服务端生成（只在该请求内去重）
    request_id: str | None = None
    missing: list[MissingActionIn] = Field(default_factory=list)
    reduced: list[ReducedIn] = Field(default_factory=list)
    added: list[AddedIn] = Field(default_factory=list)


def _shared():
    """拍照识别链路的公共实现（延迟导入，避免 inventory ↔ reconcile ↔ capture 循环引用）。"""
    from app.api import capture

    return capture


def _name_matcher():
    """名称 → 标准名（精确 → 别名表 → 模糊），别名表实现只在 receipt 一处。"""
    from app.api import receipt

    return receipt


def _normalize_items(raw_items: list[dict]) -> tuple[list[dict], list[str]]:
    """归一化 + 别名折算，补 item_id / matched（保质期由入库时按食材库补齐）。"""
    shared = _shared()
    matcher = _name_matcher()
    warnings: list[str] = []
    items: list[dict] = []
    conn = get_conn()
    try:
        for raw in raw_items:
            normalized = shared._normalize(raw)
            if not normalized["name"]:
                continue
            name, item = matcher._match_item(conn, normalized["name"], fuzzy=False)
            items.append(
                {
                    "name": name,
                    "qty": normalized["qty"],
                    "unit": normalized["unit"]
                    or (item["unit"] if item is not None and item["unit"] else ""),
                    "confidence": normalized["confidence"],
                    "item_id": item["id"] if item is not None else None,
                    "matched": item is not None,
                }
            )
            if item is None:
                warnings.append(matcher.UNMATCHED_WARNING.format(name=name))
    finally:
        conn.close()
    return items, warnings


@router.post("")
async def reconcile_inventory(file: UploadFile = File(...)) -> dict:
    content = await file.read()
    shared = _shared()
    ensure_schema()  # 不跑 lifespan 的场景（TestClient 直连）也要有 images / inventory 表
    if not content:
        raise AppError("empty_file", "上传的图片为空", 400)
    if len(content) > config.MAX_UPLOAD_BYTES:
        raise AppError(
            "payload_too_large",
            f"图片超过 {shared._upload_limit_label()}，请压缩后再传",
            413,
        )

    mime = (file.content_type or "image/jpeg").lower()
    ext = shared.EXT_BY_MIME.get(mime) or Path(file.filename or "").suffix or ".jpg"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    image_id = f"img_{uuid.uuid4().hex[:12]}"
    saved = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    saved.write_bytes(content)
    checked_at = now_iso()

    warnings: list[str] = []
    provider = resolve_provider(None)
    raw_items: list[dict] = []
    provider_ok = False

    if provider is not None:
        try:
            encoded = base64.b64encode(content).decode("ascii")
            data = await provider.chat_vision(encoded, mime, RECONCILE_PROMPT)
            raw_items = shared._flatten(data) if isinstance(data, dict) else []
            warnings.extend(shared._provider_warnings(data))
            provider_ok = True
        except Exception as exc:
            logger.warning("对账识别失败：%s", exc)

    if not provider_ok:
        # 模型不可用才拿内置样例兜底；模型正常但什么都没识别出来是用户照片的问题
        raw_items = shared._load_fixture()
        if not raw_items:
            raise AppError("vision_unavailable", "视觉识别服务不可用，请稍后重试", 502)
        warnings.append(DEGRADE_WARNING)

    recognized, item_warnings = _normalize_items(raw_items)
    warnings.extend(item_warnings)

    inventory = inventory_domain.list_inventory(inventory_domain.STATUS_ACTIVE)
    diff = reconcile_domain.build_diff(recognized, inventory)
    warnings.extend(diff["warnings"])

    # 与 §6.2 一致：识别痕迹进 images，库存本身不动（改动必须再走 /apply）
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO images(id,path,created_at,recognized) VALUES(?,?,?,?)",
            (
                image_id,
                shared._stored_path(saved),
                checked_at,
                json.dumps(
                    {"kind": "reconcile", "items": recognized, "diff": diff, "warnings": warnings},
                    ensure_ascii=False,
                ),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    logger.info(
        "库存对账：识别 %d 项，missing=%d reduced=%d added=%d suspect=%d",
        len(recognized),
        len(diff["missing"]),
        len(diff["reduced"]),
        len(diff["added"]),
        len(diff["suspect"]),
    )
    return {
        "image_id": image_id,
        "checked_at": checked_at,
        "missing": diff["missing"],
        "reduced": diff["reduced"],
        "added": diff["added"],
        "suspect": diff["suspect"],
        "warnings": warnings,
    }


@router.post("/apply")
def apply_reconcile(payload: ReconcileApplyIn) -> dict:
    return reconcile_domain.apply(payload.model_dump(exclude_none=True))
