"""公网部署用的三个中间件（契约 §10；全部默认关闭，本地开发行为不变）。

1. Basic 认证：``SHIGUANG_BASIC_AUTH=user:pass`` 时才校验
2. 限流：每 IP 每 60 秒 N 次，``SHIGUANG_RATE_LIMIT_PER_MIN>0`` 时生效
3. 上传上限：Content-Length 超过 ``config.MAX_UPLOAD_BYTES`` 直接 413
"""

from __future__ import annotations

import base64
import binascii
import hmac
import logging
import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app import config

LOGGER = logging.getLogger(__name__)

AUTH_HEADER = "authorization"
BASIC_PREFIX = "basic "
RATE_LIMIT_EXEMPT_PATHS = config.RATE_LIMIT_EXEMPT_PATHS
AUTH_EXEMPT_PATHS = ("/api/health",)  # 健康检查免认证：只返回 ok/provider/db，不含敏感信息
BUCKET_CLEANUP_EVERY = 500  # 每 N 次请求清理一次空桶，避免长期运行内存只增不减


def _unauthorized(message: str) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"code": "unauthorized", "message": message},
        headers={"WWW-Authenticate": 'Basic realm="shiguang"'},
    )


class SecurityMiddleware(BaseHTTPMiddleware):
    """认证 + 限流 + 上传大小，三件事一个中间件，避免多层开销。"""

    def __init__(self, app) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.auth: tuple[str, str] | None = None
        if config.BASIC_AUTH_SPEC:
            user, _, password = config.BASIC_AUTH_SPEC.partition(":")
            if user and password:
                self.auth = (user, password)
            else:
                LOGGER.warning("SHIGUANG_BASIC_AUTH 格式错误（应为 user:pass），已忽略")
        self.limit = max(config.RATE_LIMIT_PER_MIN, 0)
        self.window = config.RATE_LIMIT_WINDOW_SECONDS
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self._served = 0

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if self.auth is not None and path not in AUTH_EXEMPT_PATHS and not self._check_auth(request):
            return _unauthorized("需要登录后访问演示站")

        if self.limit and path not in RATE_LIMIT_EXEMPT_PATHS and not self._allow(request):
            return JSONResponse(
                status_code=429,
                content={"code": "rate_limited", "message": "请求过于频繁，请稍后再试"},
                headers={"Retry-After": str(int(self.window))},
            )

        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > config.MAX_UPLOAD_BYTES:
            megabytes = config.MAX_UPLOAD_BYTES // (1024 * 1024)
            return JSONResponse(
                status_code=413,
                content={"code": "payload_too_large", "message": f"文件超过 {megabytes} MB 限制"},
            )

        response = await call_next(request)
        self._served += 1
        if self._served % BUCKET_CLEANUP_EVERY == 0:
            self._prune(now=time.monotonic())
        return response

    def _prune(self, now: float) -> None:
        stale = [ip for ip, bucket in self.hits.items() if not bucket or now - bucket[-1] > self.window]
        for ip in stale:
            self.hits.pop(ip, None)

    def _check_auth(self, request: Request) -> bool:
        assert self.auth is not None
        header = request.headers.get(AUTH_HEADER, "")
        if not header.lower().startswith(BASIC_PREFIX):
            return False
        try:
            raw = base64.b64decode(header[len(BASIC_PREFIX) :], validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            return False
        user, _, password = raw.partition(":")
        expected_user, expected_password = self.auth
        # 常量时间比较，避免口令泄露时序
        return hmac.compare_digest(user, expected_user) and hmac.compare_digest(
            password, expected_password
        )

    def _allow(self, request: Request) -> bool:
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        bucket = self.hits[client]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return False
        bucket.append(now)
        return True
