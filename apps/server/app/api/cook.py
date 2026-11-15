"""备菜流水线 API（契约 §6.12）。

路由挂在 `app/api/recipes.py` 的 router 树上（/api/cook/sequence），
不改 `main.py` 的 `BUSINESS_ROUTERS`。
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.domain import cook as cook_domain

router = APIRouter(prefix="/cook", tags=["cook"])


class SequenceIn(BaseModel):
    recipe_ids: list[str] = Field(
        min_length=1,
        max_length=cook_domain.MAX_RECIPES,
        description="要一起做的菜谱 id，按前端勾选顺序",
    )
    start_at: str | None = Field(
        default=None,
        max_length=8,
        description="开始时间 HH:MM，缺省按当前时间排",
    )


@router.post("/sequence")
async def sequence(payload: SequenceIn) -> dict:
    return await cook_domain.plan_sequence(payload.recipe_ids, payload.start_at)
