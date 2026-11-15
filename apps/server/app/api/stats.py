"""统计 API（契约 §6.5）。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.domain import stats as stats_domain

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/summary")
def read_summary(range_: str = Query(default=stats_domain.DEFAULT_RANGE, alias="range")) -> dict:
    return stats_domain.summary(range_)
