"""用户偏好 API（契约 §6.10）：手动增删查 + 偏好即知识库条目。

推断出来的偏好由对话改计划自动写入（`source=dialog`），这里只负责
用户可见的增删查；delete 是「可控性底线」，必须能删掉错误推断。

路由前缀只写 `/preferences`：`main.py` 的 `_mount` 会补上 `/api`；
被 `app/api/plan.py` 合并挂载时，父 router 已带 `/api`，不会重复。
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.domain import preferences as preference_store
from app.domain.tools_registry import AppError

router = APIRouter(prefix="/preferences", tags=["preferences"])

PreferenceKind = Literal["avoid", "like", "time", "portion", "health"]


class PreferenceIn(BaseModel):
    text: str = Field(min_length=1, max_length=preference_store.MAX_TEXT_CHARS)
    kind: PreferenceKind = preference_store.DEFAULT_KIND
    confidence: float | None = Field(default=None, ge=0, le=1)


@router.get("")
def read_preferences(kind: str | None = Query(default=None)) -> dict:
    """返回全部偏好（含低置信度项，`active=false` 表示尚未生效）。"""
    if kind and kind not in preference_store.KINDS:
        raise AppError(
            "invalid_preference_kind",
            f"偏好类型只能是 {'/'.join(preference_store.KINDS)} 之一",
            400,
        )
    return {"items": preference_store.list_preferences(kind)}


@router.post("")
def create_preference(payload: PreferenceIn) -> dict:
    return preference_store.add_preference(
        payload.text,
        payload.kind,
        source=preference_store.SOURCE_MANUAL,
        confidence=payload.confidence,
    )


@router.delete("/{pref_id}")
def delete_preference(pref_id: str) -> dict:
    return preference_store.delete_preference(pref_id)
