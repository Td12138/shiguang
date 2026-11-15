"""SQLite 连接与建表（契约 §5 / §7.1）。

对外只暴露两个函数：`get_conn()` 与 `init_db(force=False)`，签名不得改。
数据库路径默认 `apps/server/data/app.db`，可用环境变量 `SHIGUANG_DB_PATH` 覆盖（测试用）。
"""

from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

# apps/server/app/db/conn.py -> apps/server
SERVER_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = SERVER_ROOT / "data"
DEFAULT_DB_NAME = "app.db"
DB_PATH_ENV = "SHIGUANG_DB_PATH"
SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"
SQLITE_TIMEOUT_SECONDS = 30.0

# 进程内已确认建表完成的库路径（init_db / ensure_schema 都维护它）
_SCHEMA_READY: set[str] = set()


def db_path() -> Path:
    """当前生效的数据库文件路径（每次读取环境变量，便于测试切换）。"""
    override = os.getenv(DB_PATH_ENV)
    if override:
        return Path(override).expanduser()
    return DATA_DIR / DEFAULT_DB_NAME


def get_conn() -> sqlite3.Connection:
    """返回一个新的连接，row_factory=sqlite3.Row，由调用方负责关闭。"""
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=SQLITE_TIMEOUT_SECONDS, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    """with 语句版连接：正常提交、异常回滚、始终关闭。"""
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _remove_db_files() -> None:
    path = db_path()
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(path) + suffix)
        if candidate.exists():
            candidate.unlink()


def ensure_schema() -> None:
    """幂等建表（每个库路径每进程只跑一次）。

    正常启动由 `init_db()` 建表；测试或不跑 lifespan 的场景（例如
    `TestClient(app)` 直接发请求）由业务层调这里兜底，避免「老库缺新表」。
    """
    key = str(db_path())
    if key in _SCHEMA_READY:
        return
    conn = get_conn()
    try:
        conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()
    _SCHEMA_READY.add(key)


def init_db(force: bool = False) -> None:
    """建表；items 为空时从 app/data 灌种子。force=True 会删库重建。"""
    if force:
        _remove_db_files()
        _SCHEMA_READY.discard(str(db_path()))

    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = get_conn()
    try:
        conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
        conn.commit()
        _SCHEMA_READY.add(str(path))
        item_count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    finally:
        conn.close()

    if item_count == 0:
        # 延迟导入，避免 conn <-> seed 循环引用
        from app.db import seed

        try:
            seed.seed_all()
        except Exception:  # 种子失败不能让服务起不来
            logger.exception("灌种子失败，跳过（服务仍可启动）")


def table_names() -> list[str]:
    """调试/测试辅助：当前库里的表名。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        return [row["name"] for row in rows]
    finally:
        conn.close()
