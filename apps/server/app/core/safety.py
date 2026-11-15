"""安全与兜底工具（契约 §10）：脱敏、文本截断、免责声明常量。

纯函数，不依赖其它模块，任何层都可直接引用。
"""

from __future__ import annotations

import re

from app.config import MAX_TEXT_CHARS

# 输出/日志里替换敏感信息后的占位符
REDACTED = "***"

# 免责声明（首页页脚 + 统计页 + 周报末尾共用同一句，避免多处措辞不一致）
DISCLAIMER_CARBON = "碳当量为估算，基于公开因子表"
DISCLAIMER_GENERAL = "AI 结果仅供参考，识别与推荐内容请人工确认"

# 疑似密钥：sk-xxx / Bearer xxx / 长 base64url 串
_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:sk|ak|pk|api[_-]?key|token)[-_:= ]*[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(r"\b[A-Za-z0-9_\-]{32,}\b"),
)
# 超长数字串（手机号、证件号、卡号等）
_LONG_DIGITS = re.compile(r"\d{11,}")
# 一次性把连续空白压掉，避免日志被长表格刷屏
_WHITESPACE = re.compile(r"\s+")


def redact(text: str) -> str:
    """把疑似密钥与超长数字串替换为 ``***``。"""
    if not text:
        return ""
    cleaned = text
    for pattern in _SECRET_PATTERNS:
        cleaned = pattern.sub(REDACTED, cleaned)
    return _LONG_DIGITS.sub(REDACTED, cleaned)


def truncate(text: str, limit: int = MAX_TEXT_CHARS) -> str:
    """按字符截断，超出追加省略号（避免把整段模型输出塞进日志/DB）。"""
    if text is None:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)] + "…"


def clean_text(text: str, limit: int = MAX_TEXT_CHARS) -> str:
    """用户输入 / 模型输出的统一净化：压空白 → 脱敏 → 截断。"""
    return truncate(_WHITESPACE.sub(" ", redact(text or "")).strip(), limit)


def clamp_confidence(value: float) -> float:
    """置信度归一到 0–1（模型偶尔会给 92 这种百分数）。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number > 1.0:
        number = number / 100.0
    return min(max(number, 0.0), 1.0)


def with_disclaimer(text: str) -> str:
    """给面向用户的结论文本补免责声明（已包含则不重复）。"""
    body = text or ""
    if DISCLAIMER_CARBON in body:
        return body
    return f"{body}\n\n> {DISCLAIMER_CARBON}。"
