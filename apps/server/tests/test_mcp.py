"""MCP 服务（stdio JSON-RPC）：空库 / 新 clone 直接调用不能撞 no such table。"""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]


def _load_server():
    path = SERVER_ROOT / "mcp" / "server.py"
    spec = importlib.util.spec_from_file_location("shiguang_mcp_server", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _call(server, request_id: int, name: str, arguments: dict) -> dict:
    return server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )


def test_get_shelf_life_works_on_empty_database(tmp_path, monkeypatch):
    """新库（无表、无种子）下调用 get_shelf_life：先 init_db，再正常返回。"""
    monkeypatch.setenv("SHIGUANG_DB_PATH", str(tmp_path / "mcp-empty.db"))

    server = _load_server()
    response = _call(server, 1, "get_shelf_life", {"name": "西兰花"})

    assert "error" not in response
    result = response["result"]
    assert result["isError"] is False
    payload = json.loads(result["content"][0]["text"])
    assert payload["matched"] is True
    assert payload["shelf_life_days"] == 5


def test_serve_initializes_database_before_handling(tmp_path, monkeypatch):
    """stdio 启动流程也要先建库：serve 处理 tools/call 不报错。"""
    monkeypatch.setenv("SHIGUANG_DB_PATH", str(tmp_path / "mcp-serve.db"))

    server = _load_server()
    request = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {"name": "get_shelf_life", "arguments": {"name": "鸡蛋"}},
    }
    stdout = io.StringIO()

    exit_code = server.serve(stdin=io.StringIO(json.dumps(request) + "\n"), stdout=stdout)

    assert exit_code == 0
    response = json.loads(stdout.getvalue().strip())
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["matched"] is True
