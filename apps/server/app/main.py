"""FastAPI 装配层（契约 §4：main.py 只做装配，业务全在 api/ 与 domain/）。

并行开发要点：B 的路由模块若尚未交付，``ImportError`` 一律跳过并打日志，
保证 A 单干时服务也能起、``/api/health`` 可访问。
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import config
from app.api import health
from app.core.errors import AppError
from app.core.security import SecurityMiddleware

LOGGER = logging.getLogger(__name__)

SERVICE_TITLE = "食光 · 剩食管家 API"
SERVICE_VERSION = "0.1.0"
# B 层路由模块名（对应 app/api/<name>.py），按契约 §6 顺序挂载
BUSINESS_ROUTERS: tuple[str, ...] = ("capture", "inventory", "recipes", "plan", "stats", "report")


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )


def _init_db() -> None:
    """B 的 app/db/conn.py 可能还不存在；初始化失败不阻塞启动（健康检查会显示 db 状态）。"""
    try:
        module = importlib.import_module("app.db.conn")
    except ImportError:
        LOGGER.warning("app.db.conn 尚未交付，跳过数据库初始化")
        return
    try:
        module.init_db()
    except Exception:
        LOGGER.exception("数据库初始化失败（服务继续启动，相关接口会报错）")
    else:
        LOGGER.info("数据库初始化完成")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    LOGGER.info("食光后端启动，生效配置：%s", config.describe())
    _init_db()
    yield
    LOGGER.info("食光后端退出")


def _mount(app: FastAPI, module_name: str) -> None:
    """挂载 app.api.<module_name>.router；已自带 /api 前缀的不重复叠加。"""
    try:
        module = importlib.import_module(f"app.api.{module_name}")
    except ImportError as exc:
        LOGGER.warning("路由 %s 未就绪，跳过（%s）", module_name, exc)
        return
    router = getattr(module, "router", None)
    if router is None:
        LOGGER.warning("路由 %s 未暴露 router 变量，跳过", module_name)
        return
    prefix = "" if str(getattr(router, "prefix", "")).startswith(config.API_PREFIX) else config.API_PREFIX
    app.include_router(router, prefix=prefix)
    LOGGER.info("已挂载路由 %s%s", prefix, getattr(router, "prefix", ""))


def _error_handler(_request: Request, exc: Exception) -> JSONResponse:
    error = exc if isinstance(exc, AppError) else AppError("internal_error", "服务内部错误", status=500)
    LOGGER.warning("返回错误响应：%s", error)
    body = {"code": error.code, "message": error.message}
    # 上游响应体等 detail 只进日志，不回给前端（避免泄露网关/供应商内部信息）
    if error.detail and error.status < 500:
        body["detail"] = error.detail
    return JSONResponse(status_code=error.status, content=body)


def _http_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    status = getattr(exc, "status_code", 500)
    detail = str(getattr(exc, "detail", "") or "")
    code = {404: "not_found", 405: "method_not_allowed"}.get(status, "http_error")
    return JSONResponse(status_code=status, content={"code": code, "message": detail or "请求失败"})


def _unhandled_handler(_request: Request, exc: Exception) -> JSONResponse:
    LOGGER.exception("未处理异常：%s", type(exc).__name__)
    return JSONResponse(status_code=500, content={"code": "internal_error", "message": "服务内部错误"})


def _validation_handler(_request: Request, exc: Exception) -> JSONResponse:
    """把 FastAPI 默认的 422 结构统一成 {code,message,detail}（契约 §6）。"""
    errors = getattr(exc, "errors", lambda: [])()
    fields = [
        {"loc": ".".join(str(part) for part in item.get("loc", [])), "msg": item.get("msg", "")}
        for item in errors
    ]
    LOGGER.info("请求参数校验失败：%s", fields)
    return JSONResponse(
        status_code=422,
        content={"code": "invalid_request", "message": "请求参数不合法", "detail": fields},
    )


class SPAStaticFiles(StaticFiles):
    """仅用于 /assets 等静态目录（SPA 路由回退由 catch-all 路由负责）。"""


def create_app() -> FastAPI:
    app = FastAPI(
        title=SERVICE_TITLE,
        version=SERVICE_VERSION,
        description="拍一张冰箱照片，三秒知道什么快坏了、今天做什么吃。",
        lifespan=lifespan,
        docs_url=None if config.BASIC_AUTH_SPEC else "/docs",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.CORS_ORIGINS),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # 无条件挂载：漏配环境变量不等于零防护（上传上限始终生效，auth/限流各自按开关）
    app.add_middleware(SecurityMiddleware)
    LOGGER.info(
        "演示站防护：auth=%s rate_limit=%s/min upload_limit=%sMB",
        "on" if config.BASIC_AUTH_SPEC else "off",
        config.RATE_LIMIT_PER_MIN or "off",
        config.MAX_UPLOAD_BYTES // (1024 * 1024),
    )
    app.add_exception_handler(AppError, _error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_handler)
    app.include_router(health.router, prefix=config.API_PREFIX)
    for module_name in BUSINESS_ROUTERS:
        _mount(app, module_name)

    if (config.WEB_DIST_DIR / "index.html").is_file():
        assets = config.WEB_DIST_DIR / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str) -> FileResponse:
            """前端路由回退：非 /api 路径一律返回 index.html。"""
            if full_path.startswith("api/"):
                raise StarletteHTTPException(404, "接口不存在")
            return FileResponse(config.WEB_DIST_DIR / "index.html")

        LOGGER.info("已挂载前端构建产物：%s", config.WEB_DIST_DIR)
        return app

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, Any]:
        return {
            "service": config.SERVICE_NAME,
            "version": SERVICE_VERSION,
            "docs": "/docs",
            "health": f"{config.API_PREFIX}/health",
            "hint": "前端未构建：cd apps/web && pnpm build；或 pnpm dev 访问 5274",
        }

    return app


app: FastAPI = create_app()
