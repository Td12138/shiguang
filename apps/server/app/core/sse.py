"""SSE 输出 helper（契约 §6.6 周报 / §6.15 计划与推荐流式）。

事件体一律 ``data: <json>\\n\\n``；前端按 ``type`` 字段分派
（``delta`` / ``citations`` / ``step`` / ``result`` / ``done`` / ``error``）。

``progress_stream`` 是「一次性调用 + 进度回调」这类 Agent 流水线的通用桥：
domain 每完成一步就 await 一次回调，这里转成 ``step`` 事件；调用结束发
``result``，异常发 ``error``，最后一定发 ``done``（契约 §6.15 规则 2）。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from starlette.requests import Request

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


# --------------------------------------------------------------------------- #
# 进度型流式（契约 §6.15：plan/meals/stream、recipes/suggest/stream）
# --------------------------------------------------------------------------- #

# step 事件只暴露契约要求的四个字段（started_at 留给 agent_runs，不进流）
PROGRESS_STEP_FIELDS: tuple[str, ...] = ("name", "status", "ms", "summary")
# 等事件时顺带轮询断连的时间片：有事件时零延迟，空闲时最多这么久发现一次断连
DISCONNECT_POLL_SECONDS = 0.05
DEFAULT_STREAM_ERROR_CODE = "stream_failed"
DEFAULT_STREAM_ERROR_MESSAGE = "生成失败，请稍后重试"

ProgressCallback = Callable[[dict], Awaitable[None]]
ProgressRunner = Callable[[ProgressCallback], Awaitable[dict]]


def _error_event(exc: BaseException, fallback_code: str) -> dict:
    """异常 → §6.15 的 error 事件体；AppError 带 code/message 就原样用。"""
    code = str(getattr(exc, "code", "") or fallback_code)
    message = str(getattr(exc, "message", "") or DEFAULT_STREAM_ERROR_MESSAGE)
    return {"type": "error", "code": code, "message": message}


async def progress_stream(
    request: Request,
    run: ProgressRunner,
    *,
    error_code: str = DEFAULT_STREAM_ERROR_CODE,
) -> AsyncIterator[str]:
    """把「一次性调用 + on_step 回调」转成 SSE 事件流。

    事件顺序固定：``step*`` → ``result`` → ``done``；失败时 ``step*`` → ``error`` → ``done``。
    客户端断开（AbortController）→ 回调里抛 ``CancelledError`` 取消后台任务，
    后续模型调用不会再发起（契约 §6.15 规则 4）。
    """
    queue: asyncio.Queue[dict | None] = asyncio.Queue()

    async def _on_step(step: dict) -> None:
        if await request.is_disconnected():
            raise asyncio.CancelledError("客户端已断开，停止后续步骤")
        queue.put_nowait(
            {"type": "step", **{key: step.get(key) for key in PROGRESS_STEP_FIELDS}}
        )

    async def _producer() -> None:
        try:
            payload = await run(_on_step)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - 流内异常一律转 error 事件，不抛栈给前端
            queue.put_nowait(_error_event(exc, error_code))
        else:
            queue.put_nowait({"type": "result", "payload": payload})
        finally:
            queue.put_nowait(None)  # 结束哨兵：调用方据此补 done 并收尾

    task = asyncio.create_task(_producer())
    getter: asyncio.Future | None = None
    try:
        while True:
            if getter is None:
                getter = asyncio.ensure_future(queue.get())
            try:
                # shield：超时只用来轮询断连，不能把已取到的队列项丢掉
                event = await asyncio.wait_for(
                    asyncio.shield(getter), timeout=DISCONNECT_POLL_SECONDS
                )
                getter = None
            except asyncio.TimeoutError:
                if await request.is_disconnected():
                    getter.cancel()
                    break
                continue
            if event is None:
                yield sse_done()
                break
            yield sse_event(event)
    finally:
        if getter is not None and not getter.done():
            getter.cancel()
        task.cancel()
        try:
            await task
        except BaseException:  # noqa: BLE001 - 取消/断连是预期路径，不再上抛
            pass

