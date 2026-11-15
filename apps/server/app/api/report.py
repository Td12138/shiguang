"""周报 SSE API（契约 §6.6）。事件：delta / citations / done。"""

from __future__ import annotations

import logging
from typing import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.domain import report as report_domain

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/report", tags=["report"])

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


async def _event_stream() -> AsyncIterator[str]:
    try:
        async for event in report_domain.stream_weekly():
            yield report_domain.event_stream_line(event)
    except Exception:  # 流里不能抛栈给前端
        logger.exception("周报流式生成异常")
        yield report_domain.event_stream_line(
            {"type": "delta", "text": "周报生成失败，请稍后重试。"}
        )
        yield report_domain.event_stream_line({"type": "citations", "items": []})
        yield report_domain.event_stream_line({"type": "done"})


@router.post("/weekly")
def weekly() -> StreamingResponse:
    return StreamingResponse(
        _event_stream(), media_type="text/event-stream", headers=SSE_HEADERS
    )
