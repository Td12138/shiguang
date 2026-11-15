"""统一错误类型（契约 §7.1）。

所有对外错误体统一为 ``{"code","message","detail"?}``；由 ``main.py`` 的异常处理器转 JSON。
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """业务/上游错误。``status`` 直接作为 HTTP 状态码（模型侧异常统一 502）。"""

    def __init__(
        self,
        code: str,
        message: str,
        status: int = 400,
        detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.detail:
            body["detail"] = self.detail
        return body

    def __str__(self) -> str:  # 日志友好，不带栈
        suffix = f" detail={self.detail}" if self.detail else ""
        return f"[{self.status}] {self.code}: {self.message}{suffix}"
