"""SQLite 连接与建表（契约 §5 / §7.1）。

对外暴露：`get_conn()` / `transaction()` / `init_db(force=False)`。
数据库路径默认 `apps/server/data/app.db`，可用环境变量 `SHIGUANG_DB_PATH` 覆盖（测试用）。

`transaction()` 提供跨业务域的单事务能力：块内所有 `get_conn()` 返回同一个连接的代理，
`inventory.consume/discard/add_items` 等自带 `commit()` 的域函数因此并入同一事务，
整批要么全成功要么全回滚（契约 §6.13 对账 apply 必须原子）。
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
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

# 老库补列清单：`CREATE TABLE IF NOT EXISTS` 不会给已存在的表加列，
# 新增列必须在 schema.sql 与这里各登记一次（键=表名，值=(列名, 类型)）。
MIGRATION_COLUMNS: dict[str, tuple[tuple[str, str], ...]] = {
    # 契约 §6.14：数据新鲜度
    "inventory": (("verified_at", "TEXT"),),
    # 契约 §6.13 规则 4：幂等台账按 request_id 分组（老库需要补列）
    "reconcile_applied": (("request_id", "TEXT"),),
}

# 依赖补列的新索引：必须在列补上之后再建（键=索引名，值=(表, 列)）
MIGRATION_INDEXES: dict[str, tuple[str, str]] = {
    "idx_reconcile_request": ("reconcile_applied", "request_id"),
}

# 只接受能被 SQLite 解析的时间；解析不出来的一律视为「没有核验时间」
INVALID_VERIFIED_AT_SQL = "verified_at IS NOT NULL AND date(verified_at) IS NULL"

# 事务作用域内复用的连接（线程内可见：FastAPI 同步端点跑在线程池）
_AMBIENT = threading.local()


class _AmbientConnection:
    """事务内的连接代理：`commit/rollback/close` 交给外层 `transaction()` 统一处理。

    这样 `inventory.consume` 这类自带提交的域函数在事务块内不会提前落盘，
    也不会把外层连接关掉。
    """

    __slots__ = ("_conn",)

    def __init__(self, conn: sqlite3.Connection) -> None:
        object.__setattr__(self, "_conn", conn)

    def __getattr__(self, name: str):
        return getattr(self._conn, name)

    def commit(self) -> None:  # 由外层事务提交
        return None

    def rollback(self) -> None:  # 由外层事务回滚
        return None

    def close(self) -> None:  # 由外层事务关闭
        return None


def db_path() -> Path:
    """当前生效的数据库文件路径（每次读取环境变量，便于测试切换）。"""
    override = os.getenv(DB_PATH_ENV)
    if override:
        return Path(override).expanduser()
    return DATA_DIR / DEFAULT_DB_NAME


def get_conn() -> sqlite3.Connection:
    """返回一个连接（row_factory=sqlite3.Row），由调用方负责关闭。

    在 `transaction()` 块内返回共享连接的代理：`commit/close` 被忽略，
    所有改动由外层事务一次提交。
    """
    ambient = getattr(_AMBIENT, "conn", None)
    if ambient is not None:
        return _AmbientConnection(ambient)  # type: ignore[return-value]

    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=SQLITE_TIMEOUT_SECONDS, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """整批事务：块内所有 `get_conn()` 共用同一连接，退出时统一提交或回滚。

    用法：
        with transaction() as conn:
            conn.execute(...)        # 或调用自带 commit 的域函数
            ...                      # 抛异常 → 整批回滚，不留下半截数据

    嵌套调用并入外层事务（不做部分提交）。
    """
    current = getattr(_AMBIENT, "conn", None)
    if current is not None:
        yield _AmbientConnection(current)
        return

    conn = get_conn()  # 此时没有 ambient，拿到真实连接
    _AMBIENT.conn = conn
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield _AmbientConnection(conn)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        _AMBIENT.conn = None
        conn.close()


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


def _apply_migrations(conn: sqlite3.Connection) -> list[str]:
    """给已存在的老库补新列（幂等：列已存在就跳过），返回本次补上的 "表.列"。"""
    added: list[str] = []
    for table, columns in MIGRATION_COLUMNS.items():
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if not existing:
            continue  # 表还没建出来：schema.sql 已建好带新列的表，无需补
        for name, decl in columns:
            if name in existing:
                continue
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
            added.append(f"{table}.{name}")
    for index, (table, columns) in MIGRATION_INDEXES.items():
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if not existing or columns not in existing:
            continue  # 表/列还没就绪（schema.sql 已声明新表时这里也会补建索引）
        conn.execute(f"CREATE INDEX IF NOT EXISTS {index} ON {table}({columns})")
    if added:
        logger.info("老库补列完成：%s", ", ".join(added))
    return added


def repair_invalid_times(conn: sqlite3.Connection) -> int:
    """把历史上写进 verified_at 的非法时间清成 NULL（契约 §6.14）。

    清成 NULL 后读取侧退回 `added_at` 计算 stale_days（按最旧处理），
    不会出现「垃圾时间戳 = 刚核验过」的假新鲜。新写入由 schema.sql 的触发器兜住。
    """
    cursor = conn.execute(f"UPDATE inventory SET verified_at = NULL WHERE {INVALID_VERIFIED_AT_SQL}")
    repaired = int(cursor.rowcount or 0)
    if repaired:
        logger.warning("清理非法 verified_at：%d 行改为 NULL（按 added_at 计算新鲜度）", repaired)
    return repaired


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
        _apply_migrations(conn)
        repair_invalid_times(conn)
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
        _apply_migrations(conn)
        repair_invalid_times(conn)
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
