#!/usr/bin/env python3
"""食光 MCP Server（stdio JSON-RPC 2.0，纯标准库）。

启动：
    cd apps/server
    python mcp/server.py

支持方法：initialize / tools/list / tools/call / ping
暴露工具：search_recipes（混合检索菜谱）、get_shelf_life（查保质期与保存建议）

手工调用示例（Git Bash / PowerShell 管道）：
    echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python mcp/server.py
    echo '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_shelf_life","arguments":{"name":"西兰花"}}}' | python mcp/server.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

# apps/server（保证 `python mcp/server.py` 直接能 import app.*）
SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

SERVER_NAME = "shiguang-mcp"
SERVER_VERSION = "0.1.0"
PROTOCOL_VERSION = "2024-11-05"
JSONRPC_VERSION = "2.0"

ERROR_PARSE = -32700
ERROR_INVALID_REQUEST = -32600
ERROR_METHOD_NOT_FOUND = -32601
ERROR_INVALID_PARAMS = -32602
ERROR_INTERNAL = -32603

TOOLS: list[dict] = [
    {
        "name": "search_recipes",
        "description": "按现有食材与最大耗时检索菜谱（BM25 + 可选向量混合检索，返回带引用的结果）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ingredients": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "冰箱里现有的食材名，如 [\"西兰花\",\"鸡蛋\"]",
                },
                "max_minutes": {"type": "integer", "description": "最大耗时（分钟），默认 30"},
                "limit": {"type": "integer", "description": "返回条数，默认 3"},
            },
            "required": ["ingredients"],
        },
    },
    {
        "name": "get_shelf_life",
        "description": "查询食材的保质期天数、保存建议与碳因子（食材库没有则明确说没有，不编造）",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "食材中文名，如 西兰花"}},
            "required": ["name"],
        },
    },
]

TOOL_PARAMS = {
    "search_recipes": ("ingredients", "max_minutes", "limit"),
    "get_shelf_life": ("name",),
}


def _ok(request_id: Any, result: dict) -> dict:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def _err(request_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "error": {"code": code, "message": message}}


def _text_content(payload: Any) -> dict:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
        "isError": False,
    }


def _normalize_ingredients(value: Any) -> list[str]:
    if isinstance(value, str):
        for sep in ("，", ",", "、", " ", "/"):
            value = value.replace(sep, " ")
        return [part for part in value.split(" ") if part]
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _tool_search_recipes(arguments: dict) -> dict:
    from app.domain.tools_registry import find_recipes

    ingredients = _normalize_ingredients(arguments.get("ingredients"))
    try:
        max_minutes = int(arguments.get("max_minutes") or 30)
    except (TypeError, ValueError):
        max_minutes = 30
    try:
        limit = int(arguments.get("limit") or 3)
    except (TypeError, ValueError):
        limit = 3

    result = find_recipes(ingredients=ingredients, max_minutes=max_minutes, limit=max(1, min(limit, 10)))
    recommendations = [
        {
            "recipe_id": item["recipe_id"],
            "title": item["title"],
            "minutes": item["minutes"],
            "missing": item.get("missing", []),
            "citation": {"source": item["source"], "locator": item["locator"]},
            "score": item.get("score"),
        }
        for item in result["items"]
    ]
    return {
        "query": result["query"],
        "count": len(recommendations),
        "recommendations": recommendations,
        "message": "" if recommendations else "菜谱库里没有匹配的菜谱，不编造结果",
    }


def _tool_get_shelf_life(arguments: dict) -> dict:
    from app.domain.tools_registry import get_shelf_life

    name = str(arguments.get("name") or "").strip()
    if not name:
        raise ValueError("缺少参数 name")
    return get_shelf_life(name)


TOOL_HANDLERS: dict[str, Callable[[dict], dict]] = {
    "search_recipes": _tool_search_recipes,
    "get_shelf_life": _tool_get_shelf_life,
}


def handle_request(request: Any) -> dict | None:
    """处理单条 JSON-RPC 请求；通知（无 id）返回 None。"""
    if not isinstance(request, dict):
        return _err(None, ERROR_INVALID_REQUEST, "请求必须是 JSON 对象")

    method = request.get("method")
    request_id = request.get("id")
    params = request.get("params") or {}
    is_notification = request_id is None

    if request.get("jsonrpc") != JSONRPC_VERSION or not isinstance(method, str):
        return None if is_notification else _err(request_id, ERROR_INVALID_REQUEST, "非法 JSON-RPC 请求")

    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": "食光剩食管家工具：search_recipes 按食材找菜谱，get_shelf_life 查保质期。",
        }
        return None if is_notification else _ok(request_id, result)

    if method in ("notifications/initialized", "initialized"):
        return None

    if method == "ping":
        return None if is_notification else _ok(request_id, {})

    if method == "tools/list":
        return None if is_notification else _ok(request_id, {"tools": TOOLS})

    if method == "tools/call":
        if not isinstance(params, dict):
            return _err(request_id, ERROR_INVALID_PARAMS, "params 必须是对象")
        name = params.get("name")
        arguments = params.get("arguments") or {}
        handler = TOOL_HANDLERS.get(str(name))
        if handler is None:
            return _err(request_id, ERROR_INVALID_PARAMS, f"未知工具：{name}")
        if not isinstance(arguments, dict):
            return _err(request_id, ERROR_INVALID_PARAMS, "arguments 必须是对象")
        allowed = TOOL_PARAMS.get(str(name), ())
        filtered = {key: value for key, value in arguments.items() if key in allowed}
        try:
            return _ok(request_id, _text_content(handler(filtered)))
        except Exception as exc:  # 工具异常按 MCP 约定返回 isError
            payload = {"error": type(exc).__name__, "message": str(exc)}
            return _ok(
                request_id,
                {
                    "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
                    "isError": True,
                },
            )

    if is_notification:
        return None
    return _err(request_id, ERROR_METHOD_NOT_FOUND, f"不支持的方法：{method}")


def serve(stdin=None, stdout=None) -> int:
    """逐行读取 JSON-RPC 请求，逐行写回响应（stdio 传输）。"""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            response: dict | None = _err(None, ERROR_PARSE, f"JSON 解析失败：{exc}")
        else:
            if isinstance(request, list):  # 批量请求
                responses = [handle_request(item) for item in request]
                response = [item for item in responses if item is not None] or None
            else:
                response = handle_request(request)
        if response is None:
            continue
        stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        stdout.flush()
    return 0


def main() -> int:
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
