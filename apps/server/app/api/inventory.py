"""库存 API（契约 §6.3）。"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.domain import inventory as inventory_domain
from app.domain.inventory import DISCARD_REASONS, STATUS_ACTIVE
from app.domain.tools_registry import AppError

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


class InventoryItemIn(BaseModel):
    name: str = Field(min_length=1)
    qty: float = Field(default=1, gt=0)
    unit: str | None = None
    expires_at: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    item_id: str | None = None
    note: str | None = None


class InventoryIn(BaseModel):
    image_id: str | None = None
    # 契约 §6.11：小票确认入库时传 purchased_at，入库时间按购物日期记（缺省=当前时间）
    added_at: str | None = None
    items: list[InventoryItemIn] = Field(min_length=1)


class InventoryPatch(BaseModel):
    qty: float | None = Field(default=None, gt=0)
    expires_at: str | None = None
    note: str | None = None


class ConsumeIn(BaseModel):
    grams: float | None = Field(default=None, gt=0)


class DiscardIn(BaseModel):
    reason: Literal["forgot", "spoiled", "too_much"]
    grams: float | None = Field(default=None, gt=0)


@router.post("")
def create_items(payload: InventoryIn) -> dict:
    return inventory_domain.add_items(payload.model_dump(exclude_none=True))


@router.get("")
def read_items(
    status: str = Query(default=STATUS_ACTIVE, description="active|consumed|discarded|all")
) -> list[dict]:
    if status not in (*inventory_domain.VALID_STATUSES, "all"):
        raise AppError("invalid_status", f"status 只能是 {'/'.join(inventory_domain.VALID_STATUSES)} 或 all", 400)
    return inventory_domain.list_inventory(status)


@router.patch("/{item_id}")
def patch_item(item_id: str, payload: InventoryPatch) -> dict:
    if payload.qty is None and payload.expires_at is None and payload.note is None:
        raise AppError("empty_patch", "至少提供 qty / expires_at / note 之一", 400)
    return inventory_domain.update_inventory(
        item_id,
        qty=payload.qty,
        expires_at=payload.expires_at,
        note=payload.note,
    )


@router.post("/{item_id}/consume")
def consume_item(item_id: str, payload: ConsumeIn | None = None) -> dict:
    grams = payload.grams if payload else None
    return inventory_domain.consume(item_id, grams)


@router.post("/{item_id}/discard")
def discard_item(item_id: str, payload: DiscardIn) -> dict:
    if payload.reason not in DISCARD_REASONS:
        raise AppError("invalid_reason", "丢弃原因不合法", 400)
    return inventory_domain.discard(item_id, payload.reason, payload.grams)
