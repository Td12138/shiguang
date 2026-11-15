"""饮食计划 API（契约 §6.8）。"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.domain import plan as plan_domain

router = APIRouter(prefix="/api/plan", tags=["plan"])


class MealPlanIn(BaseModel):
    days: int = Field(default=plan_domain.DEFAULT_DAYS, ge=1, le=plan_domain.MAX_DAYS)
    servings: int = Field(default=plan_domain.DEFAULT_SERVINGS, ge=1, le=8)
    max_minutes: int = Field(default=plan_domain.DEFAULT_MAX_MINUTES, ge=1, le=240)


@router.post("/meals")
async def create_meal_plan(payload: MealPlanIn) -> dict:
    return await plan_domain.build_plan(
        days=payload.days,
        servings=payload.servings,
        max_minutes=payload.max_minutes,
    )
