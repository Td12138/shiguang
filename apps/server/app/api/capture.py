"""拍照识别（契约 §6.2）。

- 图片落盘到 `apps/server/data/upload/{uuid}.{ext}`（目录自建）
- 识别结果**不入库**，只写 `images` 表留痕，必须经 `/api/inventory` 人工确认
- 置信度 < 0.7、未匹配到食材库的项写入 `warnings`
"""

from __future__ import annotations

import base64
import json
import logging
import uuid
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, File, UploadFile

from app import config
from app.db.conn import get_conn
from app.domain.inventory import DEFAULT_SHELF_LIFE_DAYS, find_item, now_iso, today
from app.domain.tools_registry import AppError, resolve_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/capture", tags=["capture"])

SERVER_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_DIR = SERVER_ROOT / "data" / "upload"
FIXTURE_FILE = SERVER_ROOT / "app" / "data" / "fixtures" / "recognize.json"
FIXTURES_DIR = SERVER_ROOT / "app" / "data" / "fixtures"

LOW_CONFIDENCE = 0.7
DEFAULT_CONFIDENCE = 0.6
DEFAULT_QTY = 1.0
EXT_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/bmp": ".bmp",
}
VISION_PROMPT = (
    "你是冰箱食材识别助手。请识别图片里所有可食用食材，输出 JSON："
    '{"items":[{"name":"西兰花","qty":1,"unit":"颗","confidence":0.92}]}。'
    "name 用常见中文名；qty 是数量（看不清就给 null，不要编）。"
    "confidence 请保守估计：完整清晰可见给 0.85-0.95；被遮挡或只看到一角给 0.5-0.7；"
    "看不清、靠猜给 0.3 以下。宁可标低，也不要一律给 1.0。"
)


def _extract_items(data: object) -> list[dict]:
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("items", "ingredients", "foods", "result"):
        value = data.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    if data.get("name"):
        return [data]
    return []


def _flatten(raw: dict) -> list[dict]:
    """兼容 {"食材": [...], ...} 这类中文字段名。"""
    items = _extract_items(raw)
    if items:
        return items
    return _extract_items(raw.get("食材"))


def _fixture_path() -> Path | None:
    """D 层 fixture 命名可能是 recognize*.json，按优先级找一个。"""
    if FIXTURE_FILE.exists():
        return FIXTURE_FILE
    for candidate in sorted(FIXTURES_DIR.glob("recognize*.json")):
        return candidate
    return None


def _load_fixture() -> list[dict]:
    path = _fixture_path()
    if path is None:
        return []
    try:
        return _flatten(json.loads(path.read_text(encoding="utf-8-sig")))
    except (json.JSONDecodeError, OSError):
        logger.warning("识别 fixture 读取失败：%s", path)
        return []


def _normalize(raw: dict) -> dict:
    try:
        confidence = float(raw.get("confidence", DEFAULT_CONFIDENCE))
    except (TypeError, ValueError):
        confidence = DEFAULT_CONFIDENCE
    try:
        qty = float(raw.get("qty", DEFAULT_QTY))
    except (TypeError, ValueError):
        qty = DEFAULT_QTY
    return {
        "name": str(raw.get("name") or raw.get("食材") or "").strip(),
        "qty": qty,
        "unit": str(raw.get("unit") or "").strip(),
        "confidence": round(max(0.0, min(confidence, 1.0)), 3),
    }


def _stored_path(path: Path) -> str:
    """库内只存相对项目根的路径，避免把盘符写进数据（测试目录用绝对路径兜底）。"""
    try:
        return str(path.relative_to(SERVER_ROOT))
    except ValueError:
        return str(path)


def _upload_limit_label() -> str:
    """用配置常量拼出人类可读上限（不写死数字）。"""
    limit = config.MAX_UPLOAD_BYTES
    if limit >= 1024 * 1024:
        return f"{limit // (1024 * 1024)}MB"
    if limit >= 1024:
        return f"{limit // 1024}KB"
    return f"{limit} 字节"


@router.post("/recognize")
async def recognize(file: UploadFile = File(...)) -> dict:
    content = await file.read()
    if not content:
        raise AppError("empty_file", "上传的图片为空", 400)
    if len(content) > config.MAX_UPLOAD_BYTES:
        raise AppError(
            "payload_too_large",
            f"图片超过 {_upload_limit_label()}，请压缩后再传",
            413,
        )

    mime = (file.content_type or "image/jpeg").lower()
    ext = EXT_BY_MIME.get(mime) or Path(file.filename or "").suffix or ".jpg"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    image_id = f"img_{uuid.uuid4().hex[:12]}"
    saved = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    saved.write_bytes(content)

    warnings: list[str] = []
    provider = resolve_provider(None)
    raw_items: list[dict] = []
    used_fixture = False

    if provider is not None:
        try:
            encoded = base64.b64encode(content).decode("ascii")
            data = await provider.chat_vision(encoded, mime, VISION_PROMPT)
            raw_items = _flatten(data)
        except Exception as exc:
            logger.warning("视觉识别失败：%s", exc)
            warnings.append("已降级：视觉模型不可用，返回内置样例，请务必人工核对")

    if not raw_items:
        raw_items = _load_fixture()
        used_fixture = bool(raw_items)
        if raw_items and not any("已降级" in item for item in warnings):
            warnings.append("已降级：视觉模型不可用，返回内置样例，请务必人工核对")
        if not raw_items:
            raise AppError("vision_unavailable", "视觉识别服务不可用，请稍后重试", 502)

    items: list[dict] = []
    conn = get_conn()
    try:
        for index, raw in enumerate(raw_items, start=1):
            normalized = _normalize(raw)
            if not normalized["name"]:
                continue
            item = find_item(conn, normalized["name"])
            shelf = int(item["shelf_life_days"] or DEFAULT_SHELF_LIFE_DAYS) if item else DEFAULT_SHELF_LIFE_DAYS
            expires_at = (today() + timedelta(days=shelf)).isoformat()
            unit = normalized["unit"] or (item["unit"] if item and item["unit"] else "份")
            confidence = normalized["confidence"]

            items.append(
                {
                    "name": normalized["name"],
                    "qty": normalized["qty"],
                    "unit": unit,
                    "confidence": confidence,
                    "item_id": item["id"] if item else None,
                    "shelf_life_days": shelf,
                    "expires_at": expires_at,
                    "matched": bool(item),
                }
            )
            if confidence < LOW_CONFIDENCE:
                warnings.append(
                    f"第 {index} 项「{normalized['name']}」识别置信度较低（{confidence}），请确认"
                )
            if not item:
                warnings.append(f"「{normalized['name']}」不在食材库，已标记未匹配（不计入碳账）")

        conn.execute(
            "INSERT INTO images(id,path,created_at,recognized) VALUES(?,?,?,?)",
            (
                image_id,
                _stored_path(saved),
                now_iso(),
                json.dumps({"items": items, "warnings": warnings}, ensure_ascii=False),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    if used_fixture and not items:
        raise AppError("vision_unavailable", "没有识别出任何食材，请换一张更清晰的照片", 422)

    return {"image_id": image_id, "items": items, "warnings": warnings}


# 小票识别（契约 §6.11）挂在同一棵 capture router 上：路径 /api/capture/receipt。
# 新文件里用延迟导入复用本模块的视觉链路，不引入循环引用，也不用改 main.py。
from app.api import receipt as receipt_api  # noqa: E402

router.include_router(receipt_api.router)
