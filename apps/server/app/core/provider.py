"""LLM Provider 抽象（契约 §7 / §7.1）。

- 全部走 OpenAI 兼容 ``POST {base_url}/chat/completions``
- 结构化输出：``response_format={"type":"json_object"}`` + pydantic 校验 + 失败重试 1 次
- 视觉：``image_url`` + base64 data URI
- 超时 60 s（视觉 90 s），失败统一转 502 的 ``AppError``，不向前端抛栈
- 密钥只从配置读，日志里只出现 provider 名与模型名
"""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
import warnings
from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

import httpx
from pydantic import BaseModel, ValidationError

from app import config
from app.core.errors import AppError
from app.core.mock import MockProvider
from app.core.safety import truncate

LOGGER = logging.getLogger(__name__)


def ssl_verify() -> object:
    """TLS 校验策略。

    - ``os``（默认）：系统信任库，可穿越本地 TLS 代理
    - ``strict``：certifi，标准校验
    - ``off``：仅本地开发用——本机代理会替换证书链，OpenSSL 校验间歇失败；
      服务器部署请保持 os/strict，不要用 off
    """
    mode = config.SSL_VERIFY
    if mode == "strict":
        return True
    if mode == "off":
        warnings.filterwarnings("ignore", message="Unverified HTTPS request")
        return False
    return ssl.create_default_context()

JSON_MODE: dict[str, str] = {"type": "json_object"}
_JSON_MODE_UNSUPPORTED = "response_format"  # 上游报错里出现即视为不支持 JSON mode
_CODE_VERSION = "1"
CONNECT_ATTEMPTS = 2
CONNECT_RETRY_DELAY_SECONDS = 0.8


@runtime_checkable
class LLMProvider(Protocol):
    """契约 §7.1：B 层只依赖此协议，不关心具体厂商。"""

    name: str

    async def chat_json(
        self,
        messages: list[dict],
        *,
        schema: type[BaseModel] | None = None,
        timeout: float = config.LLM_TIMEOUT_SECONDS,
    ) -> dict: ...

    async def chat_text(self, messages: list[dict], *, timeout: float = config.LLM_TIMEOUT_SECONDS) -> str: ...

    async def chat_vision(
        self,
        image_b64: str,
        mime: str,
        prompt: str,
        *,
        timeout: float = config.LLM_VISION_TIMEOUT_SECONDS,
    ) -> dict: ...

    def stream_chat(self, messages: list[dict]) -> AsyncIterator[str]: ...


def extract_json(text: str) -> Any:
    """从模型输出里抠出 JSON：容忍 ```json 围栏、前后寒暄、尾随逗号。"""
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1] if raw.count("```") >= 2 else raw.lstrip("`")
        raw = raw.removeprefix("json").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        return json.loads(raw[start : end + 1])
    raise ValueError("no json object in model output")


def _flatten_vision_items(items: list[Any]) -> list[dict[str, Any]]:
    """递归拆掉套娃：``[{"items":[...]}, ...]`` → 真正的食材条目列表。"""
    flat: list[dict[str, Any]] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        inner = row.get("items")
        if isinstance(inner, list):
            flat.extend(_flatten_vision_items(inner))
        else:
            flat.append(row)
    return flat


def _normalize_vision_payload(data: Any) -> dict[str, Any] | None:
    """把视觉模型的各种返回姿势统一成 ``{"items": [...]}``。

    实测（zhipu glm-4v-flash）至少三种：裸数组、``{"items":[...]}``、
    ``{"items":[{"items":[...]}]}`` 套娃，甚至同时出现，这里递归收口。
    """
    if isinstance(data, list):
        return {
            "items": _flatten_vision_items(data),
            "warnings": ["模型未按要求包裹 items 字段，已自动兼容"],
        }
    if not isinstance(data, dict):
        return None
    items = data.get("items")
    if isinstance(items, list):
        payload: dict[str, Any] = {
            "items": _flatten_vision_items(items),
            "warnings": [str(x) for x in data.get("warnings", []) if isinstance(x, str)],
        }
        # 小票链路还要用这两个顶层字段，不能在归一化时丢掉
        for key in ("purchased_at", "total_price"):
            if key in data:
                payload[key] = data[key]
        return payload
    return None


class OpenAICompatibleProvider:
    """zhipu / dashscope / openai / local 共用实现。"""

    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str,
        model: str,
        vision_model: str,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.model = model
        self.vision_model = vision_model

    # ---------------------------------------------------------------- HTTP
    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "User-Agent": f"{config.SERVICE_NAME}/{_CODE_VERSION}"}
        if self._api_key:  # local 常常没有 key
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _url(self) -> str:
        return f"{self.base_url}{config.CHAT_COMPLETIONS_PATH}"

    def _timeout(self, timeout: float) -> httpx.Timeout:
        return httpx.Timeout(timeout, connect=config.LLM_CONNECT_TIMEOUT_SECONDS)

    async def _post(self, payload: dict[str, Any], timeout: float) -> str:
        """发一次请求，返回 ``choices[0].message.content``。异常统一转 AppError(502)。

        ConnectError 重试一次：Windows 上首次 TLS 握手偶发
        `Missing Authority Key Identifier`，第二次即正常（Linux 服务端不受影响）。
        """
        response: httpx.Response | None = None
        for attempt in range(CONNECT_ATTEMPTS):
            try:
                async with httpx.AsyncClient(
                    timeout=self._timeout(timeout), verify=ssl_verify()
                ) as client:
                    response = await client.post(self._url(), json=payload, headers=self._headers())
                break
            except httpx.TimeoutException as exc:
                LOGGER.warning("provider=%s 超时 %.0fs", self.name, timeout)
                raise AppError("llm_timeout", f"模型服务超时（{self.name}）", status=502) from exc
            except httpx.ConnectError as exc:
                if attempt + 1 < CONNECT_ATTEMPTS:
                    LOGGER.warning(
                        "provider=%s 首次连接失败，%s 后重试", self.name, CONNECT_RETRY_DELAY_SECONDS
                    )
                    await asyncio.sleep(CONNECT_RETRY_DELAY_SECONDS)
                    continue
                LOGGER.warning("provider=%s 连接失败 %s", self.name, type(exc).__name__)
                raise AppError("llm_unreachable", f"模型服务连接失败（{self.name}）", status=502) from exc
            except httpx.HTTPError as exc:
                LOGGER.warning("provider=%s 连接失败 %s", self.name, type(exc).__name__)
                raise AppError("llm_unreachable", f"模型服务连接失败（{self.name}）", status=502) from exc

        assert response is not None
        if response.status_code >= 400:
            body = truncate(response.text, 300)
            LOGGER.warning("provider=%s HTTP %s：%s", self.name, response.status_code, body)
            raise AppError(
                "llm_http_error",
                f"模型服务返回 {response.status_code}（{self.name}）",
                status=502,
                detail=body,
            )

        try:
            data = response.json()
            return data["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            LOGGER.warning("provider=%s 响应结构异常", self.name)
            raise AppError("llm_bad_response", f"模型响应结构异常（{self.name}）", status=502) from exc

    async def _complete(
        self,
        messages: list[dict],
        *,
        model: str,
        timeout: float,
        max_tokens: int,
        json_mode: bool,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": config.LLM_TEMPERATURE,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = dict(JSON_MODE)
        try:
            return await self._post(payload, timeout)
        except AppError as exc:
            # 部分网关（自建 vLLM / 老版本）不支持 response_format，去掉后重试一次
            if json_mode and exc.code == "llm_http_error" and _JSON_MODE_UNSUPPORTED in (exc.detail or "").lower():
                LOGGER.warning("provider=%s 不支持 response_format，降级为纯提示词模式", self.name)
                payload.pop("response_format", None)
                return await self._post(payload, timeout)
            raise

    # ---------------------------------------------------------------- 接口
    async def chat_text(
        self,
        messages: list[dict],
        *,
        timeout: float = config.LLM_TIMEOUT_SECONDS,
    ) -> str:
        return await self._complete(
            messages, model=self.model, timeout=timeout, max_tokens=config.LLM_MAX_TOKENS, json_mode=False
        )

    async def chat_json(
        self,
        messages: list[dict],
        *,
        schema: type[BaseModel] | None = None,
        timeout: float = config.LLM_TIMEOUT_SECONDS,
    ) -> dict:
        attempts = 1 + config.LLM_RETRY_TIMES
        last_error = ""
        for attempt in range(attempts):
            content = await self._complete(
                messages, model=self.model, timeout=timeout, max_tokens=config.LLM_MAX_TOKENS, json_mode=True
            )
            try:
                data = extract_json(content)
            except ValueError:
                last_error = "no_json"
                LOGGER.warning("provider=%s 第 %d 次返回非 JSON：%s", self.name, attempt + 1, truncate(content, 120))
                continue
            if schema is None:
                if isinstance(data, dict):
                    return data
                if isinstance(data, list):
                    # 真实模型经常直接给数组，统一收口成 items，调用方按需取
                    return {"items": [row for row in data if isinstance(row, dict)]}
                last_error = "not_object"
                continue
            try:
                return schema.model_validate(data).model_dump()
            except ValidationError as exc:
                last_error = f"schema:{len(exc.errors())}errors"
                LOGGER.warning("provider=%s 第 %d 次 JSON 不符合 %s", self.name, attempt + 1, schema.__name__)
        raise AppError(
            "llm_invalid_json",
            "模型未返回可解析的结构化结果，请稍后重试",
            status=502,
            detail=last_error,
        )

    async def chat_vision(
        self,
        image_b64: str,
        mime: str,
        prompt: str,
        *,
        timeout: float = config.LLM_VISION_TIMEOUT_SECONDS,
    ) -> dict:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{image_b64}"},
                    },
                ],
            }
        ]
        # 视觉模型多数不支持 response_format，靠提示词约束 + 本地解析
        attempts = 1 + config.LLM_RETRY_TIMES
        last_error = ""
        for attempt in range(attempts):
            content = await self._complete(
                messages,
                model=self.vision_model,
                timeout=timeout,
                max_tokens=config.VLM_MAX_TOKENS,
                json_mode=False,
            )
            try:
                data = extract_json(content)
            except ValueError:
                last_error = "no_json"
                LOGGER.warning("provider=%s 视觉第 %d 次返回非 JSON", self.name, attempt + 1)
                continue
            normalized = _normalize_vision_payload(data)
            if normalized is not None:
                return normalized
            last_error = "not_object"
        raise AppError("llm_invalid_json", "视觉模型未返回可解析的结构化结果", status=502, detail=last_error)

    async def stream_chat(self, messages: list[dict]) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": config.LLM_TEMPERATURE,
            "max_tokens": config.LLM_MAX_TOKENS,
            "stream": True,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout(config.LLM_TIMEOUT_SECONDS), verify=ssl_verify()) as client:
                async with client.stream(
                    "POST", self._url(), json=payload, headers=self._headers()
                ) as response:
                    if response.status_code >= 400:
                        body = truncate(await response.aread(), 300)
                        LOGGER.warning("provider=%s 流式 HTTP %s", self.name, response.status_code)
                        raise AppError(
                            "llm_http_error",
                            f"模型服务返回 {response.status_code}（{self.name}）",
                            status=502,
                            detail=str(body),
                        )
                    async for line in response.aiter_lines():
                        chunk = _parse_stream_line(line)
                        if chunk is _STREAM_END:
                            break
                        if chunk:
                            yield chunk
        except httpx.HTTPError as exc:
            LOGGER.warning("provider=%s 流式中断 %s", self.name, type(exc).__name__)
            raise AppError("llm_unreachable", f"模型服务连接中断（{self.name}）", status=502) from exc


_STREAM_END = object()


def _parse_stream_line(line: str) -> str | None | object:
    """解析一行 SSE：返回增量文本 / None（跳过）/ _STREAM_END（结束）。"""
    text = (line or "").strip()
    if not text or text.startswith(":"):
        return None
    if not text.startswith("data:"):
        return None
    data = text[len("data:") :].strip()
    if data in ("[DONE]", "DONE"):
        return _STREAM_END
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return None
    choices = payload.get("choices") or []
    if not choices:
        return None
    delta = choices[0].get("delta") or {}
    content = delta.get("content") or choices[0].get("message", {}).get("content")
    return content or None


# ---------------------------------------------------------------- 工厂
_PROVIDER: LLMProvider | None = None


def build_provider() -> LLMProvider:
    """按配置构建 provider（每次读 config 属性，测试可 monkeypatch 后 reset）。"""
    name = config.LLM_PROVIDER
    if name == "mock" or not (config.LLM_BASE_URL and config.LLM_BASE_URL.startswith("http")):
        if name != "mock":
            LOGGER.warning("provider=%s 缺少可用 base_url，回退 mock", name)
        return MockProvider()
    # 审查缺陷：非本地 provider 且 key 为空时必须降级，否则每个请求都带空 Authorization 真发出去 → 全链路 502
    if name != "local" and not config.LLM_API_KEY:
        LOGGER.warning("provider=%s 未配置 SHIGUANG_LLM_API_KEY，已回退 mock（否则请求会被上游 401）", name)
        return MockProvider()
    LOGGER.info("provider=%s base_url=%s model=%s vision=%s", name, config.LLM_BASE_URL, config.LLM_MODEL, config.VLM_MODEL)
    return OpenAICompatibleProvider(
        name=name,
        base_url=config.LLM_BASE_URL,
        api_key=config.LLM_API_KEY,
        model=config.LLM_MODEL,
        vision_model=config.VLM_MODEL,
    )


def get_provider() -> LLMProvider:
    """进程内单例（契约 §7.1）。"""
    global _PROVIDER
    if _PROVIDER is None:
        _PROVIDER = build_provider()
    return _PROVIDER


def reset_provider() -> None:
    """测试/热切换用：丢弃单例，下次调用重建。"""
    global _PROVIDER
    _PROVIDER = None
