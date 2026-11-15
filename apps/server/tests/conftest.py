"""pytest 公共夹具：临时数据库、参考数据工厂、FakeProvider（不依赖真实 LLM）。"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))


def _short_id(name: str) -> str:
    return hashlib.sha1(name.encode("utf-8")).hexdigest()[:6]


@pytest.fixture()
def app_db(tmp_path, monkeypatch):
    """每个测试独立 sqlite 文件（SHIGUANG_DB_PATH 指向 tmp_path）。"""
    db_file = tmp_path / "app.db"
    monkeypatch.setenv("SHIGUANG_DB_PATH", str(db_file))
    monkeypatch.delenv("SHIGUANG_EMBEDDING_PROVIDER", raising=False)

    # 测试与 D 层真实语料隔离：种子文件指向不存在的临时路径（缺失时只警告不崩）
    from app.db import seed as seed_module

    missing = tmp_path / "no_seed"
    monkeypatch.setattr(seed_module, "ITEMS_FILE", missing / "items.json")
    monkeypatch.setattr(seed_module, "RECIPES_FILE", missing / "recipes.json")
    monkeypatch.setattr(seed_module, "TIPS_FILE", missing / "tips.md")

    from app.db.conn import init_db

    init_db(force=True)
    return db_file


@pytest.fixture()
def add_item(app_db):
    """往食材库插一条（默认西兰花：300g/颗、碳 2.5、价 10）。"""

    def _add(name: str = "西兰花", **kwargs) -> str:
        from app.db.conn import get_conn

        item_id = kwargs.pop("item_id", None) or f"i_{_short_id(name)}"
        row = {
            "id": item_id,
            "name": name,
            "category": kwargs.pop("category", "蔬菜"),
            "shelf_life_days": kwargs.pop("shelf_life_days", 5),
            "carbon_kg_per_kg": kwargs.pop("carbon_kg_per_kg", 2.5),
            "price_per_kg": kwargs.pop("price_per_kg", 10.0),
            "avg_grams": kwargs.pop("avg_grams", 300.0),
            "storage_tip": kwargs.pop("storage_tip", "冷藏，别洗"),
            "unit": kwargs.pop("unit", "颗"),
        }
        conn = get_conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO items(id,name,category,shelf_life_days,"
                "carbon_kg_per_kg,price_per_kg,avg_grams,storage_tip,unit)"
                " VALUES(:id,:name,:category,:shelf_life_days,:carbon_kg_per_kg,"
                ":price_per_kg,:avg_grams,:storage_tip,:unit)",
                row,
            )
            conn.commit()
        finally:
            conn.close()
        return item_id

    return _add


@pytest.fixture()
def add_recipe(app_db):
    """往菜谱表插一条并重建 RAG 索引。"""

    def _add(
        recipe_id: str = "r_1",
        title: str = "蒜蓉西兰花",
        ingredients: list | None = None,
        steps: list | None = None,
        minutes: int = 15,
        servings: int = 1,
        tags: str = "快手",
        difficulty: str = "简单",
    ) -> str:
        from app.db.conn import get_conn
        from app.rag.index import rebuild_index

        ingredients = ingredients or [
            {"name": "西兰花", "qty": 1, "unit": "颗", "optional": False},
            {"name": "大蒜", "qty": 2, "unit": "瓣", "optional": False},
        ]
        steps = steps or ["西兰花切小朵洗净", "大蒜切末", "热油爆香蒜末", "下西兰花翻炒调味"]
        conn = get_conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO recipes(id,title,ingredients,steps,minutes,servings,tags,difficulty)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (
                    recipe_id,
                    title,
                    json.dumps(ingredients, ensure_ascii=False),
                    json.dumps(steps, ensure_ascii=False),
                    minutes,
                    servings,
                    tags,
                    difficulty,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        rebuild_index()
        return recipe_id

    return _add


class FakeProvider:
    """按 system prompt 里的「阶段：xxx」标记分发，模拟 core 的 provider 行为。"""

    name = "fake"

    def __init__(
        self,
        *,
        understand: dict | None = None,
        compose: dict | list | None = None,
        fail_compose: bool = False,
        fail_understand: bool = False,
        vision: dict | None = None,
        stream_chunks: list[str] | None = None,
        fail_stream: bool = False,
    ) -> None:
        self.understand = understand if understand is not None else {"max_minutes": 30, "servings": 1}
        self.compose = compose if compose is not None else {"recommendations": []}
        self.fail_compose = fail_compose
        self.fail_understand = fail_understand
        self.vision = vision or {"items": []}
        self.stream_chunks = stream_chunks or ["本周", "成绩不错。"]
        self.fail_stream = fail_stream
        self.calls: list[str] = []
        self._compose_index = 0

    @staticmethod
    def _stage(messages: list[dict]) -> str:
        for message in messages:
            if message.get("role") == "system":
                system = str(message.get("content") or "")
                if "阶段：understand" in system:
                    return "understand"
                if "阶段：compose" in system:
                    return "compose"
                if "阶段：report" in system:
                    return "report"
        return ""

    async def chat_json(self, messages, *, schema=None, timeout: float = 60) -> dict:
        stage = self._stage(messages)
        self.calls.append(stage)
        if stage == "understand":
            if self.fail_understand:
                raise RuntimeError("understand boom")
            return self.understand
        if stage == "compose":
            if self.fail_compose:
                raise RuntimeError("compose boom")
            if isinstance(self.compose, list):
                index = min(self._compose_index, len(self.compose) - 1)
                self._compose_index += 1
                return self.compose[index]
            return self.compose
        return {}

    async def chat_text(self, messages, *, timeout: float = 60) -> str:
        return "（fake text）"

    async def chat_vision(self, image_b64: str, mime: str, prompt: str, *, timeout: float = 90) -> dict:
        return self.vision

    def stream_chat(self, messages):
        async def _gen():
            if self.fail_stream:
                raise RuntimeError("stream boom")
            for chunk in self.stream_chunks:
                yield chunk

        return _gen()


@pytest.fixture()
def fake_provider():
    return FakeProvider


@pytest.fixture()
def no_llm(monkeypatch):
    """强制业务层拿到 None provider（模拟无 key，走降级路径）。"""
    from app.domain import plan as plan_module
    from app.domain import recipes as recipes_module
    from app.domain import report as report_module

    for module in (recipes_module, report_module, plan_module):
        monkeypatch.setattr(module, "resolve_provider", lambda provider=None: None)
    return None
