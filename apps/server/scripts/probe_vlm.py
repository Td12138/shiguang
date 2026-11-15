"""VLM 实测探针：拿真实照片跑当前 provider，输出识别条数/耗时/置信度。

用法（apps/server 下）：
    python scripts/probe_vlm.py ../../samples/fridge-1.jpg
    python scripts/probe_vlm.py            # 默认跑 ../../samples/*.jpg

只打印识别结果与耗时，不打印任何密钥。
"""

from __future__ import annotations

import asyncio
import base64
import sys
import time
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.core.provider import get_provider  # noqa: E402

DEFAULT_SAMPLES = SERVER_ROOT.parent.parent / "samples"
# 智谱免费档并发很低，连续请求会 ConnectError；探针一律串行 + 间隔
REQUEST_INTERVAL_SECONDS = 2.0
PROMPT = (
    "这是一张冰箱内部的照片。请列出你能看清的所有食材，输出 JSON："
    '{"items":[{"name":"中文食材名","qty":数字或null,"unit":"颗/把/盒/袋/个",'
    '"confidence":0到1的小数,"note":"位置或状态，可空"}]}'
    "要求：只写你真正看清的；看不清的不要猜；name 用中文常用名。"
)


def _encode(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


async def run(paths: list[Path]) -> None:
    provider = get_provider()
    print(f"provider={provider.name}")
    for index, path in enumerate(paths):
        if index:
            await asyncio.sleep(REQUEST_INTERVAL_SECONDS)
        started = time.perf_counter()
        try:
            data = await provider.chat_vision(_encode(path), "image/jpeg", PROMPT)
        except Exception as exc:  # 探针不隐藏失败
            print(f"{path.name}: 失败 {type(exc).__name__}: {exc}")
            continue
        cost_ms = (time.perf_counter() - started) * 1000
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            print(f"{path.name}: 返回结构异常 keys={list(data) if isinstance(data, dict) else type(data)}")
            continue
        print(f"{path.name}: {cost_ms:.0f} ms, {len(items)} 项")
        if items and not isinstance(items[0], dict):
            print(f"  结构异常：items[0] 类型 {type(items[0]).__name__}，whole={str(data)[:200]}")
        elif items and "name" not in items[0]:
            print(f"  字段异常：keys={list(items[0])}，whole={str(data)[:300]}")
        for item in items:
            if not isinstance(item, dict):
                continue
            print(
                "  - {name} ×{qty}{unit}  conf={conf}".format(
                    name=item.get("name"),
                    qty=item.get("qty"),
                    unit=item.get("unit") or "",
                    conf=item.get("confidence"),
                )
            )


def main() -> int:
    args = sys.argv[1:]
    paths = [Path(arg) for arg in args] if args else sorted(DEFAULT_SAMPLES.glob("*.jpg"))
    if not paths:
        print("没有找到图片：请把冰箱照片放到 samples/ 后重试")
        return 1
    asyncio.run(run(paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
