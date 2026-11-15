"""饮食计划 API（契约 §6.8 / §6.9 / §6.10）。

`/api/preferences` 也挂在这棵 router 树上：`main.py` 的 `BUSINESS_ROUTERS`
目前还没有 `preferences` 项（该文件由 A 维护），先把偏好路由并进来，
等 A 加上 `preferences` 后删掉这里的 `include_router` 即可，路径不变。
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api import preferences as preferences_api
from app.domain import plan as plan_domain

router = APIRouter(prefix="/api", tags=["plan"])
plan_router = APIRouter(prefix="/plan", tags=["plan"])


class MealPlanIn(BaseModel):
    days: int = Field(default=plan_domain.DEFAULT_DAYS, ge=1, le=plan_domain.MAX_DAYS)
    servings: int = Field(default=plan_domain.DEFAULT_SERVINGS, ge=1, le=8)
    max_minutes: int = Field(default=plan_domain.DEFAULT_MAX_MINUTES, ge=1, le=240)


class ReviseIn(BaseModel):
    instruction: str = Field(
        min_length=1,
        max_length=plan_domain.REVISE_MAX_INSTRUCTION,
        description="一句话说明要怎么改，例如「第二天想吃清淡点，不要鸡蛋」",
    )


@plan_router.post("/meals")
async def create_meal_plan(payload: MealPlanIn) -> dict:
    return await plan_domain.build_plan(
        days=payload.days,
        servings=payload.servings,
        max_minutes=payload.max_minutes,
    )


@plan_router.post("/meals/{plan_id}/revise")
async def revise_meal_plan(plan_id: str, payload: ReviseIn) -> dict:
    """对话改计划：只改点名的餐，返回 changed diff + 本次学到的偏好。"""
    return await plan_domain.revise(plan_id, payload.instruction)


router.include_router(plan_router)
router.include_router(preferences_api.router)
