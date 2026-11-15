"""SSE 输出helper（契约 §6.6）：仅周报使用。

事件体一律 ``data: <json>\\n\\n``；前端按 ``type`` 字段分派
（``delta`` / ``citations`` / ``done`` / ``error``）。
"""

from __future__ import annotations

import json
from typing import Any

SSE_MEDIA_TYPE = "text/event-stream"
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # 关掉 Nginx 缓冲，保证逐字下发
}
SSE_DONE_EVENT = {"type": "done"}


def sse_event(payload: dict[str, Any]) -> str:
    """把一个 dict 编码成一条 SSE 事件。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def sse_error(code: str, message: str) -> str:
    """流内错误（HTTP 头已发出时用这个，不静默失败）。"""
    return sse_event({"type": "error", "code": code, "message": message})


def sse_delta(text: str) -> str:
    return sse_event({"type": "delta", "text": text})


def sse_done() -> str:
    return sse_event(dict(SSE_DONE_EVENT))
