from __future__ import annotations

import asyncio
import json
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


class AsyncDrawStreamClient(Protocol):
    async def stream(
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
        http_client: AsyncDrawStreamClient | None = None,
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
        text_parts: list[str] = []
        image_url = ""
        async for line in self._stream(
            f"{self.base_url}/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=self.timeout_seconds,
        ):
            event = _parse_sse_data(line)
            if event is None:
                continue
            if event == "[DONE]":
                break
            data = json.loads(event)
            for extracted in _extract_strings(data):
                if extracted:
                    text_parts.append(extracted)
                if not image_url:
                    image_url = _extract_image_url(extracted)
            if not image_url:
                image_url = _extract_image_url_from_object(data)

        text = "".join(text_parts).strip()
        if not image_url:
            image_url = _extract_image_url(text)
        if not image_url:
            raise RuntimeError("RightCodes 生图没有返回图片 URL")
        return RightCodesDrawResult(
            image_url=image_url,
            text=text,
            total_seconds=time.perf_counter() - started,
        )

    def _build_payload(self, request: RightCodesDrawRequest) -> dict[str, object]:
        content: str | list[dict[str, object]]
        prompt = (
            "请根据用户提示生成图片。生成完成后只返回最终图片直链，不要解释。\n"
            f"用户提示：{request.prompt}"
        )
        if request.image_urls:
            content = [{"type": "text", "text": prompt}]
            content.extend(
                {"type": "image_url", "image_url": {"url": image_url}}
                for image_url in request.image_urls
            )
        else:
            content = prompt
        return {
            "model": request.model,
            "stream": True,
            "messages": [{"role": "user", "content": content}],
        }

    async def _stream(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> Any:
        if self.http_client is not None:
            async for line in self.http_client.stream(
                url,
                headers=headers,
                json=json,
                timeout=timeout,
            ):
                yield line
            return

        iterator = _stream_json_lines(url, headers, json, timeout)
        while True:
            line = await asyncio.to_thread(_next_line, iterator)
            if line is None:
                break
            yield line


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
    command_match = re.match(r"^(?:棉花糖|棉花)\s*生图\s+(.+)$", text)
    if command_match is not None:
        return command_match.group(1).strip()
    natural_match = re.match(r"^生成\s*(.+?)(?:的)?(?:图片|图像|图)\s*$", text)
    if natural_match is not None:
        return natural_match.group(1).strip()
    return None


def _stream_json_lines(
    url: str,
    headers: dict[str, str],
    payload: dict[str, object],
    timeout: float,
):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=body, headers=headers, method="POST")
    with urlopen(request, timeout=timeout) as response:
        status = int(getattr(response, "status", 200))
        if status >= 400:
            raise RuntimeError(f"RightCodes draw request failed: {status}")
        for raw_line in response:
            yield raw_line.decode("utf-8").strip()


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


def _next_line(iterator) -> str | None:
    try:
        return next(iterator)
    except StopIteration:
        return None


def _parse_sse_data(line: str) -> str | None:
    normalized = line.strip()
    if not normalized or not normalized.startswith("data:"):
        return None
    return normalized.removeprefix("data:").strip()


def _extract_strings(data: object) -> tuple[str, ...]:
    strings: list[str] = []
    _walk_strings(data, strings)
    return tuple(strings)


def _walk_strings(value: object, strings: list[str]) -> None:
    if isinstance(value, str):
        strings.append(value)
    elif isinstance(value, dict):
        for child in value.values():
            _walk_strings(child, strings)
    elif isinstance(value, list):
        for child in value:
            _walk_strings(child, strings)


def _extract_image_url_from_object(data: object) -> str:
    if isinstance(data, dict):
        for key in ("url", "b64_json"):
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
