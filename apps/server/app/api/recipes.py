"""菜谱建议 + Agent trace API（契约 §6.4 / §6.7 / §6.15）。

每次 `/api/recipes/suggest` 都会创建一条 `agent_runs`，响应体带 `run_id`。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.sse import SSE_HEADERS, SSE_MEDIA_TYPE, progress_stream
from app.domain import recipes as recipes_domain
from app.domain import tools_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["recipes"])

tools_registry.register_all()

# 流内错误兜底码（AppError 自带 code 时以 AppError 为准）
SUGGEST_STREAM_ERROR_CODE = "agent_failed"


class SuggestIn(BaseModel):
    use: list[str] = Field(default_factory=list)
    max_minutes: int = Field(default=recipes_domain.DEFAULT_MAX_MINUTES, ge=1, le=240)
    limit: int = Field(default=recipes_domain.DEFAULT_LIMIT, ge=1, le=recipes_domain.MAX_LIMIT)


@router.post("/recipes/suggest")
async def suggest(payload: SuggestIn) -> dict:
    return await recipes_domain.suggest(
        use=payload.use,
        max_minutes=payload.max_minutes,
        limit=payload.limit,
    )


@router.post("/recipes/suggest/stream")
async def stream_suggest(payload: SuggestIn, request: Request) -> StreamingResponse:
    """§6.15：同一份 suggest 的流式版（step 即时下发，result 与非流式逐字段一致）。"""
    return StreamingResponse(
        progress_stream(
            request,
            lambda on_step: recipes_domain.suggest(
                use=payload.use,
                max_minutes=payload.max_minutes,
                limit=payload.limit,
                on_step=on_step,
            ),
            error_code=SUGGEST_STREAM_ERROR_CODE,
        ),
        media_type=SSE_MEDIA_TYPE,
        headers=SSE_HEADERS,
    )


@router.get("/agent/runs/{run_id}")
def read_run(run_id: str) -> dict:
    return recipes_domain.get_run(run_id)


# 备菜流水线（契约 §6.12）：/api/cook/sequence，挂在同一棵 router 树上
from app.api import cook as cook_api  # noqa: E402

router.include_router(cook_api.router)
