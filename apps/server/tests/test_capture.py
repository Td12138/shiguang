"""拍照识别（契约 §6.2）：provider warnings 合并、空结果不回填样例、缺数量降置信。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.domain.tools_registry import AppError

FAKE_JPEG = b"\xff\xd8\xff\xe0capture-jpeg"


@pytest.fixture()
def client(app_db):
    from app.api import capture as capture_api

    app = FastAPI()
    app.include_router(capture_api.router)

    @app.exception_handler(AppError)
    async def _handler(_request, exc: AppError):
        return JSONResponse(
            {"code": exc.code, "message": exc.message, "detail": exc.detail},
            status_code=exc.status,
        )

    return TestClient(app)


@pytest.fixture()
def capture_env(monkeypatch, tmp_path):
    from app.api import capture as capture_api

    monkeypatch.setattr(capture_api, "UPLOAD_DIR", tmp_path / "upload")

    def _setup(provider):
        monkeypatch.setattr(
            capture_api, "resolve_provider", lambda provider=None, _p=provider: provider or _p
        )
        return capture_api

    return _setup


def _post(client):
    return client.post(
        "/api/capture/recognize",
        files={"file": ("fridge.jpg", FAKE_JPEG, "image/jpeg")},
    )


def test_mock_provider_warning_is_visible(client, capture_env):
    """mock 回放在识别卡上必须明确标出来（视频里不能把样例说成真实识别）。"""
    from app.core.mock import MockProvider

    capture_env(MockProvider())

    body = _post(client).json()

    assert body["items"], "mock fixture 应有可演示的识别结果"
    assert any("mock 回放数据" in warning for warning in body["warnings"])


def test_provider_empty_result_does_not_backfill_fixture(
    client, add_item, capture_env, fake_provider
):
    """provider 成功但 items=[]：返回空列表 + 重拍提示，不能把内置样例当识别结果。"""
    add_item("西兰花", avg_grams=300.0, shelf_life_days=5)
    capture_env(fake_provider(vision={"items": []}))

    response = _post(client)

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == [], "provider 正常空结果不得回填 fixture"
    assert any("未识别到食材" in warning for warning in body["warnings"])
    assert any("重拍" in warning for warning in body["warnings"])


def test_provider_warnings_are_merged(client, add_item, capture_env, fake_provider):
    """provider 自带 warnings（mock 回放提示）必须透传到响应。"""
    add_item("西兰花", avg_grams=300.0)
    mock_warning = "当前为 mock 回放数据（未调用真实视觉模型），识别结果请人工确认"
    capture_env(
        fake_provider(
            vision={
                "items": [{"name": "西兰花", "qty": 1, "unit": "颗", "confidence": 0.9}],
                "warnings": [mock_warning, "", 123],
            }
        )
    )

    body = _post(client).json()

    assert body["warnings"][0] == mock_warning, "provider warnings 要排在服务端 warnings 之前"
    assert len(body["items"]) == 1


@pytest.mark.parametrize("raw_qty", [None, "missing"])
def test_missing_qty_is_not_silently_one(
    client, add_item, capture_env, fake_provider, raw_qty
):
    """qty=null / 缺失：保留 1 但必须 warning + 置信度下调，不能静默当 1.0。"""
    add_item("西兰花", avg_grams=300.0)
    item = {"name": "西兰花", "unit": "颗", "confidence": 0.95}
    if raw_qty != "missing":
        item["qty"] = raw_qty
    capture_env(fake_provider(vision={"items": [item]}))

    body = _post(client).json()

    first = body["items"][0]
    assert first["qty"] == 1.0
    assert first["confidence"] <= 0.5, "缺数量要下调置信度，避免看起来像确定识别"
    assert any("没有识别到数量" in warning for warning in body["warnings"])
    assert any("请核对" in warning for warning in body["warnings"])


def test_ketchup_is_not_matched_to_tomato(client, add_item, capture_env, fake_provider):
    """识别「番茄酱」不能命中食材库「番茄」：应标 matched:false，而不是套用番茄数据。"""
    add_item("番茄", avg_grams=150.0)
    capture_env(
        fake_provider(
            vision={
                "items": [
                    {"name": "番茄酱", "qty": 1, "unit": "瓶", "confidence": 0.9}
                ]
            }
        )
    )

    body = _post(client).json()

    first = body["items"][0]
    assert first["name"] == "番茄酱"
    assert first["matched"] is False
    assert first["item_id"] is None


def test_non_numeric_qty_is_treated_as_missing(client, add_item, capture_env, fake_provider):
    add_item("西兰花", avg_grams=300.0)
    capture_env(
        fake_provider(
            vision={
                "items": [
                    {"name": "西兰花", "qty": "一把", "unit": "颗", "confidence": 0.9}
                ]
            }
        )
    )

    body = _post(client).json()

    assert body["items"][0]["qty"] == 1.0
    assert any("没有识别到数量" in warning for warning in body["warnings"])
