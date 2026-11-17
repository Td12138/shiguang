"""前端构建产物的静态文件解析（SPA 回退与限流豁免共用这一处，避免两套判断）。

背景：Vite 会把 `apps/web/public/` 原样拷到 `dist/` 根（logo.svg、hero-kitchen.jpg）。
FastAPI 只挂了 `/assets`，其余路径一律回退 index.html，于是 `/logo.svg` 拿到的是 HTML，
浏览器按图片解码失败 → 侧栏 logo 碎图、首页 hero 背景丢失。这里把「dist 里真实存在的文件」
挑出来直接回文件，其余仍走 SPA 回退。
"""

from __future__ import annotations

from pathlib import Path

from app import config

# 带内容 hash 的产物可以长缓存；根目录公共文件（logo/hero）改一次要能较快生效
ASSET_PREFIX = "assets/"
ASSET_CACHE_CONTROL = "public, max-age=31536000, immutable"
PUBLIC_CACHE_CONTROL = "public, max-age=3600"
INDEX_CACHE_CONTROL = "no-cache"


def static_file(path: str) -> Path | None:
    """URL 路径 → dist 内真实文件；不存在、是目录或越出 dist 一律 None。"""
    relative = path.lstrip("/")
    if not relative or relative.startswith("api/"):
        return None
    root = config.WEB_DIST_DIR.resolve()
    try:
        target = (root / relative).resolve()
    except (OSError, ValueError):
        return None
    if not target.is_relative_to(root) or not target.is_file():
        return None
    return target


def cache_control(path: str) -> str:
    """真实文件的缓存头：hash 产物 immutable，其余公共文件 1 小时。"""
    return ASSET_CACHE_CONTROL if path.lstrip("/").startswith(ASSET_PREFIX) else PUBLIC_CACHE_CONTROL
