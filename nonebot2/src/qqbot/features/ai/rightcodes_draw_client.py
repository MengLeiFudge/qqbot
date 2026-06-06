from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from urllib.error import HTTPError
from typing import Any, Protocol
from urllib.request import Request, urlopen


RIGHTCODES_DRAW_BASE_URL = "https://www.right.codes/draw"
RIGHTCODES_DRAW_DEFAULT_MODEL = "gpt-image-2"
RIGHTCODES_DRAW_MODELS = {
    "gpt-image-2-vip",
    "gpt-image-2",
    "nano-banana",
    "nano-banana-2",
    "nano-banana-pro",
}
RIGHTCODES_DRAW_MODEL_DESCRIPTIONS = {
    "gpt-image-2": ("OpenAI 最新的画图模型，特价版，支持分辨率：1K", "0.04r"),
    "gpt-image-2-vip": ("OpenAI 最新的画图模型，官方直连，支持分辨率：1K、2K、4K", "0.13r"),
    "nano-banana": ("由 gemini-2.5-flash-image 模型封装而来", "0.14r"),
    "nano-banana-2": ("nano banana 第二代绘图模型，综合效果远超上一代，支持分辨率：1K、2K、4K", "0.12r"),
    "nano-banana-pro": ("nano banana 第二代绘图模型，综合效果远超上一代，支持分辨率：1K、2K、4K", "0.18r"),
}
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RightCodesDrawRequest:
    prompt: str
    model: str = RIGHTCODES_DRAW_DEFAULT_MODEL
    image_urls: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RightCodesDrawResult:
    image_url: str
    text: str
    total_seconds: float


class AsyncDrawHttpClient(Protocol):
    async def post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> Any:
        ...


class RightCodesDrawClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = RIGHTCODES_DRAW_BASE_URL,
        timeout_seconds: float = 180.0,
        http_client: AsyncDrawHttpClient | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.http_client = http_client

    async def draw(self, request: RightCodesDrawRequest) -> RightCodesDrawResult:
        if not self.api_key:
            raise ValueError("缺少 RightCodes 生图 API Key")
        payload = self._build_payload(request)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        started = time.perf_counter()
        url = f"{self.base_url}/v1/images/generations"
        logger.info(
            "RightCodes draw request started: model=%s image_count=%s timeout=%.1fs",
            request.model,
            len(request.image_urls),
            self.timeout_seconds,
        )
        try:
            data = await self._post_json(
                url,
                headers=headers,
                json=payload,
                timeout=self.timeout_seconds,
            )
        except Exception:
            logger.exception(
                "RightCodes draw request failed: model=%s elapsed=%.3fs",
                request.model,
                time.perf_counter() - started,
            )
            raise
        image_url = _extract_image_url_from_object(data)
        if not image_url:
            raise RuntimeError("RightCodes 生图没有返回图片 URL")
        total_seconds = time.perf_counter() - started
        logger.info(
            "RightCodes draw request succeeded: model=%s elapsed=%.3fs",
            request.model,
            total_seconds,
        )
        return RightCodesDrawResult(
            image_url=image_url,
            text="",
            total_seconds=total_seconds,
        )

    def _build_payload(self, request: RightCodesDrawRequest) -> dict[str, object]:
        return {
            "model": request.model,
            "prompt": request.prompt,
            "image": list(request.image_urls),
            "size": "1024x1024",
            "response_format": "url",
        }

    async def _post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> object:
        if self.http_client is not None:
            return await self.http_client.post_json(
                url,
                headers=headers,
                json=json,
                timeout=timeout,
            )
        return await _post_json(url, headers, json, timeout)


def parse_rightcodes_draw_command(text: str) -> RightCodesDrawRequest | None:
    normalized = text.strip()
    rest = _extract_rightcodes_draw_prompt(normalized)
    if rest is None:
        return None
    if not rest:
        return None

    model = RIGHTCODES_DRAW_DEFAULT_MODEL
    prompt = rest
    bracket_match = re.match(r"^\[([^\]]+)\]\s*(.+)$", rest)
    if bracket_match is not None:
        candidate = bracket_match.group(1).strip()
        if candidate in RIGHTCODES_DRAW_MODELS:
            model = candidate
            prompt = bracket_match.group(2).strip()
        else:
            return RightCodesDrawRequest(prompt=rest, model=model)
    else:
        parts = rest.split(maxsplit=1)
        if len(parts) == 2 and parts[0] in RIGHTCODES_DRAW_MODELS:
            model = parts[0]
            prompt = parts[1].strip()
    if not prompt:
        return None
    return RightCodesDrawRequest(prompt=prompt, model=model)


def looks_like_rightcodes_draw_command(text: str) -> bool:
    return parse_rightcodes_draw_command(text) is not None


def looks_like_rightcodes_draw_help_command(text: str) -> bool:
    normalized = re.sub(r"\s+", "", text.strip())
    return normalized in {
        "生图模型说明",
        "生图模型",
        "生图价格",
        "画图模型说明",
        "画图模型",
        "画图价格",
        "棉花糖生图模型说明",
        "棉花糖生图模型",
        "棉花糖生图价格",
        "棉花生图模型说明",
        "棉花生图模型",
        "棉花生图价格",
    }


def format_rightcodes_draw_model_help() -> str:
    lines = [
        "棉花糖现在支持这些生图模型喵：",
    ]
    for model in (
        "gpt-image-2",
        "gpt-image-2-vip",
        "nano-banana",
        "nano-banana-2",
        "nano-banana-pro",
    ):
        description, price = RIGHTCODES_DRAW_MODEL_DESCRIPTIONS[model]
        default_mark = "（默认）" if model == RIGHTCODES_DRAW_DEFAULT_MODEL else ""
        lines.append(f"- {model}{default_mark}：{price}/张。{description}")
    lines.extend(
        [
            "",
            "用法：",
            "棉花糖生图 [模型名] 提示词",
            "棉花糖生图 模型名 提示词",
            "不写模型时默认使用 gpt-image-2。",
        ]
    )
    return "\n".join(lines)


def format_rightcodes_draw_success(
    result: RightCodesDrawResult,
    *,
    model: str,
    image_count: int = 1,
) -> str:
    return (
        "✨ 生成成功！\n"
        f"📊 耗时: {result.total_seconds:.2f}s\n"
        f"🖼️ 数量: {image_count}张\n"
        f"🤖 模型: {model}"
    )


def format_rightcodes_draw_failure(exc: Exception) -> str:
    return f"❌ 生成失败: {extract_rightcodes_draw_error_message(exc)}"


def extract_rightcodes_draw_error_message(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        detail = _read_http_error_detail(exc)
        return detail or f"上游返回 HTTP {exc.code}"
    message = str(exc).strip()
    if message:
        return message
    return type(exc).__name__


def _extract_rightcodes_draw_prompt(text: str) -> str | None:
    command_match = re.match(r"^(?:棉花糖|棉花)\s*生图([\s\S]*)$", text)
    if command_match is not None:
        return command_match.group(1).strip()
    natural_match = re.match(r"^生成\s*(.+?)(?:的)?(?:图片|图像|图)\s*$", text)
    if natural_match is not None:
        return natural_match.group(1).strip()
    return None


async def _post_json(
    url: str,
    headers: dict[str, str],
    payload: dict[str, object],
    timeout: float,
) -> object:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=body, headers=headers, method="POST")
    return await _run_urlopen_json(request, timeout)


async def _run_urlopen_json(request: Request, timeout: float) -> object:
    def read_response() -> object:
        with urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
            if status >= 400:
                raise RuntimeError(f"RightCodes draw request failed: {status}")
            body = response.read().decode("utf-8")
        return json.loads(body)

    return await asyncio.to_thread(read_response)


def _read_http_error_detail(exc: HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:
        return ""
    if not body:
        return ""
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return body[:200]
    for path in (
        ("error", "message"),
        ("message",),
        ("detail",),
    ):
        value: object = data
        for key in path:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return body[:200]


def _extract_image_url_from_object(data: object) -> str:
    if isinstance(data, dict):
        value = data.get("b64_json")
        if isinstance(value, str) and value.strip():
            return f"data:image/png;base64,{value.strip()}"
        for key in ("url",):
            value = data.get(key)
            if isinstance(value, str):
                extracted = _extract_image_url(value)
                if extracted:
                    return extracted
        for child in data.values():
            extracted = _extract_image_url_from_object(child)
            if extracted:
                return extracted
    elif isinstance(data, list):
        for child in data:
            extracted = _extract_image_url_from_object(child)
            if extracted:
                return extracted
    return ""


def _extract_image_url(text: str) -> str:
    cleaned = text.strip().strip('"').strip("'")
    data_match = re.search(r"data:image/(?:png|jpeg|jpg|webp);base64,[A-Za-z0-9+/=]+", cleaned)
    if data_match:
        return data_match.group(0)
    url_match = re.search(r"https?://[^\s<>)\"']+\.(?:png|jpg|jpeg|webp)(?:\?[^\s<>)\"']*)?", cleaned, re.IGNORECASE)
    return url_match.group(0) if url_match else ""
