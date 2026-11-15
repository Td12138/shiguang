"""小票识别（契约 §6.11）：价格缺失为 null、别名匹配、warnings、不入库。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.domain import inventory as inv
from app.domain.tools_registry import AppError

FAKE_JPEG = b"\xff\xd8\xff\xe0fakejpeg"


@pytest.fixture()
def client(app_db):
    from app.api import capture
    from app.api import inventory as inventory_api

    app = FastAPI()
    for module in (capture, inventory_api):
        app.include_router(module.router)

    @app.exception_handler(AppError)
    async def _handler(_request, exc: AppError):
        return JSONResponse(
            {"code": exc.code, "message": exc.message, "detail": exc.detail},
            status_code=exc.status,
        )

    return TestClient(app)


@pytest.fixture()
def receipt_env(monkeypatch, tmp_path):
    """把上传目录指向临时目录，并按测试注入 provider。"""
    from app.api import receipt as receipt_api

    monkeypatch.setattr(receipt_api, "UPLOAD_DIR", tmp_path / "upload")

    def _setup(provider):
        monkeypatch.setattr(
            receipt_api, "resolve_provider", lambda provider=None, _p=provider: provider or _p
        )
        return receipt_api

    return _setup


def _post(client):
    return client.post(
        "/api/capture/receipt",
        files={"file": ("receipt.jpg", FAKE_JPEG, "image/jpeg")},
    )


def test_receipt_items_price_alias_and_warnings(
    client, add_item, fake_provider, receipt_env, tmp_path
):
    add_item("西兰花", avg_grams=300.0, shelf_life_days=5, unit="颗")
    add_item("番茄", avg_grams=200.0, shelf_life_days=7, unit="个")
    provider = fake_provider(
        vision={
            "items": [
                {"name": "西兰花", "qty": 1, "unit": "颗", "price": 6.5, "confidence": 0.9},
                {"name": "西红柿", "qty": 2, "unit": "个", "price": "￥3.20", "confidence": 0.82},
                {"name": "火星野菜", "qty": 1, "unit": "把", "confidence": 0.55},
            ],
            "purchased_at": "2026-11-15",
            "total_price": 23.6,
        }
    )
    receipt_env(provider)

    response = _post(client)
    assert response.status_code == 200
    body = response.json()

    assert body["image_id"].startswith("img_")
    assert {"image_id", "items", "purchased_at", "total_price", "warnings"} <= set(body)
    assert body["purchased_at"] == "2026-11-15"
    assert body["total_price"] == pytest.approx(23.6)

    broccoli, tomato, unknown = body["items"]
    assert broccoli["name"] == "西兰花"
    assert broccoli["price"] == pytest.approx(6.5)
    assert broccoli["matched"] is True and broccoli["item_id"]
    # 小票日期 + 保质期 = 到期日
    assert broccoli["expires_at"] == "2026-11-20"

    assert tomato["name"] == "番茄", "别名表要把「西红柿」折成「番茄」"
    assert tomato["matched"] is True
    assert tomato["price"] == pytest.approx(3.2)

    assert unknown["price"] is None, "价格认不出必须为 null，不得编造"
    assert unknown["matched"] is False

    warnings = body["warnings"]
    assert any("价格" in warning for warning in warnings)
    assert any("置信度较低" in warning for warning in warnings)
    assert any("未匹配" in warning for warning in warnings)

    # 识别结果不入库
    assert inv.list_inventory("active") == []
    assert list((tmp_path / "upload").glob("*.jpg")), "上传的小票图片应落盘"


def test_receipt_missing_total_and_bad_date(client, add_item, fake_provider, receipt_env):
    add_item("西兰花", shelf_life_days=5)
    provider = fake_provider(
        vision={
            "items": [{"name": "西兰花", "qty": 1, "unit": "颗", "confidence": 0.93}],
            "purchased_at": "看不清",
            "total_price": "--",
        }
    )
    receipt_env(provider)

    body = _post(client).json()

    assert body["total_price"] is None, "小票没有合计时不得编造 total_price"
    assert body["purchased_at"] is None
    assert body["items"][0]["price"] is None
    warnings = body["warnings"]
    assert any("合计" in warning for warning in warnings)
    assert any("日期" in warning for warning in warnings)
    assert any("价格" in warning for warning in warnings)


def test_receipt_with_mock_provider_returns_null_prices(client, add_item, receipt_env):
    """mock 必须能跑通全链路：内置样例没有价格，于是全部 price=null 并给 warnings。"""
    from app.core.mock import MockProvider

    add_item("西兰花", shelf_life_days=5)
    receipt_env(MockProvider())

    response = _post(client)
    assert response.status_code == 200
    body = response.json()

    assert body["items"], "mock 下也要返回 items"
    assert all(item["price"] is None for item in body["items"])
    assert body["warnings"]


def test_receipt_to_inventory_uses_purchased_at(client, add_item, fake_provider, receipt_env):
    """契约 §6.11：确认入库时 added_at 用小票日期。"""
    add_item("西兰花", shelf_life_days=5)
    receipt_env(
        fake_provider(
            vision={
                "items": [
                    {"name": "西兰花", "qty": 1, "unit": "颗", "price": 6.5, "confidence": 0.9}
                ],
                "purchased_at": "2026-11-15",
                "total_price": 6.5,
            }
        )
    )
    body = _post(client).json()

    created = client.post(
        "/api/inventory",
        json={
            "image_id": body["image_id"],
            "added_at": body["purchased_at"],
            "items": [
                {
                    "name": body["items"][0]["name"],
                    "qty": 1,
                    "unit": "颗",
                    "expires_at": body["items"][0]["expires_at"],
                }
            ],
        },
    )
    assert created.status_code == 200
    assert created.json()["added"] == 1

    listed = inv.list_inventory("active")
    assert listed[0]["added_at"].startswith("2026-11-15")


def test_receipt_empty_file(client, receipt_env, fake_provider):
    receipt_env(fake_provider())
    response = client.post(
        "/api/capture/receipt", files={"file": ("empty.jpg", b"", "image/jpeg")}
    )
    assert response.status_code == 400
    assert response.json()["code"] == "empty_file"
