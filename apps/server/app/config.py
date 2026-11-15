"""食光 · 剩食管家 —— 全局配置（A 层）。

约定（契约 §11）：
- 端口 / URL / 模型名 / 阈值一律集中为本文件顶部的全大写常量
- 路径一律由 ``Path(__file__)`` 推导，禁止硬编码盘符
- 密钥只从 ``apps/server/.env`` 或进程环境变量读取，永不入库、永不打日志
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

LOGGER = logging.getLogger(__name__)

# --------------------------------------------------------------------- 路径
APP_DIR = Path(__file__).resolve().parent
SERVER_DIR = APP_DIR.parent
PROJECT_DIR = SERVER_DIR.parent.parent
ENV_FILE = SERVER_DIR / ".env"
DATA_DIR = APP_DIR / "data"
FIXTURES_DIR = DATA_DIR / "fixtures"
RUNTIME_DIR = SERVER_DIR / "data"
# 上传目录必须可覆盖：发布目录每次切换软链，写进 releases/ 的图会随版本孤立
UPLOAD_DIR = Path(env_str("SHIGUANG_UPLOAD_DIR", str(RUNTIME_DIR / "upload")))


def load_env_file(path: Path) -> dict[str, str]:
    """极简 .env 解析：``KEY=VALUE``，支持 # 注释、引号、export 前缀（不引 python-dotenv）。"""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].strip()
        values[key.strip()] = value
    return values


ENV_DOTENV = load_env_file(ENV_FILE)


def env_str(key: str, default: str = "") -> str:
    """进程环境变量优先，其次 .env，最后默认值。"""
    return os.environ.get(key) or ENV_DOTENV.get(key) or default


def env_int(key: str, default: int) -> int:
    try:
        return int(env_str(key, ""))
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------- 服务
SERVICE_NAME = "shiguang-server"
API_PREFIX = "/api"
HOST = env_str("SHIGUANG_HOST", "127.0.0.1")
PORT = env_int("SHIGUANG_PORT", 8720)
WEB_DEV_ORIGINS = ("http://127.0.0.1:5274", "http://localhost:5274")
CORS_ORIGINS = tuple(
    origin.strip()
    for origin in env_str("SHIGUANG_CORS_ORIGINS", "").split(",")
    if origin.strip()
) or WEB_DEV_ORIGINS
LOG_LEVEL = env_str("SHIGUANG_LOG_LEVEL", "INFO").upper()

# 运行期数据（不入库）：B 的 app/db/conn.py 也认 SHIGUANG_DB_PATH，两边共用同一路径
_DB_PATH_OVERRIDE = env_str("SHIGUANG_DB_PATH", "")
DB_PATH = (SERVER_DIR / _DB_PATH_OVERRIDE).resolve() if _DB_PATH_OVERRIDE else RUNTIME_DIR / "app.db"

# --------------------------------------------------------------------- Provider 预设
DEFAULT_PROVIDER = "mock"
PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "mock": {"base_url": "", "model": "mock-chat", "vision_model": "mock-vision"},
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
        "vision_model": "glm-4v-flash",
    },
    "dashscope": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "vision_model": "qwen-vl-plus",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "vision_model": "gpt-4o-mini",
    },
    "local": {
        "base_url": "http://127.0.0.1:8080/v1",
        "model": "local-model",
        "vision_model": "local-vl",
    },
}


def _resolve_provider(raw: str) -> str:
    name = (raw or DEFAULT_PROVIDER).strip().lower()
    if name not in PROVIDER_PRESETS:
        LOGGER.warning("未知 provider=%s，回退 mock（可选：%s）", raw, ", ".join(PROVIDER_PRESETS))
        return DEFAULT_PROVIDER
    return name


LLM_PROVIDER = _resolve_provider(env_str("SHIGUANG_LLM_PROVIDER", DEFAULT_PROVIDER))
_PRESET = PROVIDER_PRESETS[LLM_PROVIDER]
LLM_BASE_URL = env_str("SHIGUANG_LLM_BASE_URL", _PRESET["base_url"]).rstrip("/")
# 密钥来源优先级：.env 里的 SHIGUANG_LLM_API_KEY → 用户环境变量 ZHIPU_API（不复制进文件、不入库）
LLM_API_KEY = env_str("SHIGUANG_LLM_API_KEY", "") or os.environ.get("ZHIPU_API", "").strip()
LLM_MODEL = env_str("SHIGUANG_LLM_MODEL", _PRESET["model"])
VLM_MODEL = env_str("SHIGUANG_VLM_MODEL", _PRESET["vision_model"])
EMBEDDING_PROVIDER = env_str("SHIGUANG_EMBEDDING_PROVIDER", "none").strip().lower()
EMBEDDING_BASE_URL = env_str("SHIGUANG_EMBEDDING_BASE_URL", "http://127.0.0.1:8848").rstrip("/")
EMBEDDING_MODEL = env_str("SHIGUANG_EMBEDDING_MODEL", "bge-m3")

# --------------------------------------------------------------------- LLM 调用参数
CHAT_COMPLETIONS_PATH = "/chat/completions"
LLM_TIMEOUT_SECONDS = 60.0
LLM_VISION_TIMEOUT_SECONDS = 90.0
LLM_CONNECT_TIMEOUT_SECONDS = 10.0
LLM_RETRY_TIMES = 1  # 结构化输出解析失败后的额外重试次数（契约 §7）
SSL_VERIFY = env_str("SHIGUANG_SSL_VERIFY", "os").strip().lower()  # os=系统信任库（可穿越本地 TLS 代理），strict=certifi
LLM_TEMPERATURE = 0.2
LLM_MAX_TOKENS = 1024
VLM_MAX_TOKENS = 1024

# --------------------------------------------------------------------- Mock 回放
MOCK_STREAM_CHUNK_SIZES = (3, 2, 4)
MOCK_STREAM_DELAY_SECONDS = 0.02

# --------------------------------------------------------------------- 业务阈值（前后端共用口径）
CONFIDENCE_WARN_THRESHOLD = 0.7
FRESH_MIN_DAYS = 4  # days_left >= 4 → fresh
SOON_MIN_DAYS = 2  # 2–3 → soon
URGENT_MIN_DAYS = 0  # 0–1 → urgent，< 0 → expired
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_TEXT_CHARS = 2000

# --------------------------------------------------------------------- 发布形态（默认关闭 = 本地开发行为不变）
WEB_DIST_DIR = Path(env_str("SHIGUANG_WEB_DIST", str(PROJECT_DIR / "apps" / "web" / "dist")))
BASIC_AUTH_SPEC = env_str("SHIGUANG_BASIC_AUTH", "").strip()  # 形如 "demo:口令"；空 = 不启用
RATE_LIMIT_PER_MIN = env_int("SHIGUANG_RATE_LIMIT_PER_MIN", 0)  # 0 = 不启用
RATE_LIMIT_WINDOW_SECONDS = 60.0
RATE_LIMIT_EXEMPT_PATHS = ("/api/health",)


def mask_secret(value: str) -> str:
    """日志用脱敏：只保留长度提示与末 4 位，空值返回 ``<empty>``。"""
    if not value:
        return "<empty>"
    if len(value) <= 8:
        return "***"
    return f"***{value[-4:]}"


def describe() -> dict[str, object]:
    """启动日志用的生效配置（不含密钥明文）。"""
    return {
        "provider": LLM_PROVIDER,
        "base_url": LLM_BASE_URL or "<preset:none>",
        "api_key": mask_secret(LLM_API_KEY),
        "model": LLM_MODEL,
        "vision_model": VLM_MODEL,
        "embedding_provider": EMBEDDING_PROVIDER,
        "host": HOST,
        "port": PORT,
        "cors_origins": list(CORS_ORIGINS),
        "db_path": str(DB_PATH),
        "env_file": str(ENV_FILE),
        "env_file_exists": ENV_FILE.is_file(),
    }
