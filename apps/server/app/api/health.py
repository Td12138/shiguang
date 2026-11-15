"""健康检查（契约 §6.1）：``GET /api/health`` → ``{"ok","provider","db"}``。

不依赖 B 层是否已就绪：``db`` 会返回 ok / missing / error，服务本身永远可应答。
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

from fastapi import APIRouter

from app.core.provider import get_provider

LOGGER = logging.getLogger(__name__)

DB_OK = "ok"
DB_MISSING = "missing"
DB_ERROR = "error"

router = APIRouter(tags=["health"])


def _db_status() -> str:
    """探测 B 层的 app/db/conn.py 是否可用（import 不到就是尚未交付）。"""
    try:
        module = importlib.import_module("app.db.conn")
    except ImportError:
        return DB_MISSING
    connection = None
    try:
        connection = module.get_conn()
        connection.execute("SELECT 1").fetchone()
    except Exception:  # 初始化未完成 / 表缺失 都只降级不抛
        LOGGER.warning("健康检查：数据库不可用", exc_info=True)
        return DB_ERROR
    finally:
        if connection is not None:
            connection.close()
    return DB_OK


@router.get("/health")
async def health() -> dict[str, Any]:
    db = _db_status()
    return {
        "ok": db == DB_OK,
        "provider": get_provider().name,
        "db": db,
    }
