from __future__ import annotations

import asyncio
import json as json_module
import time
from typing import Any, Protocol
from urllib.request import Request, urlopen

from qqbot.services.ai_gateway import AiClient, AiCompletion, AiMetrics, AiRequest


class IncompleteAiStreamError(RuntimeError):
    pass


class AsyncStreamClient(Protocol):
    async def stream(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> Any:
        ...


class MimoCompatibleClient(AiClient):
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        vision_model: str = "",
        timeout_seconds: float = 45.0,
        supports_vision: bool = False,
        http_client: AsyncStreamClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.vision_model = vision_model.strip() or model
        self.timeout_seconds = timeout_seconds
        self.supports_vision = supports_vision
        self.http_client = http_client

    async def complete(self, request: AiRequest) -> str:
        completion = await self.stream_complete(request)
        return completion.text

    async def stream_complete(self, request: AiRequest) -> AiCompletion:
        payload = self._build_chat_payload(request)
        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }

        start = time.perf_counter()
        first_token_seconds: float | None = None
        text_parts: list[str] = []
        completion_tokens: int | None = None
        usage: dict[str, object] | None = None
        received_done = False
        finish_reason = ""
        async for line in self._stream(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=self.timeout_seconds,
        ):
            event = _parse_sse_data(line)
            if event is None:
                continue
            if event == "[DONE]":
                received_done = True
                break
            data = json_module.loads(event)
            token = _extract_delta_text(data)
            if token:
                if first_token_seconds is None:
                    first_token_seconds = time.perf_counter() - start
                text_parts.append(token)
            chunk_usage = _extract_usage(data)
            if chunk_usage is not None:
                usage = chunk_usage
                usage_tokens = _extract_completion_tokens(chunk_usage)
                if usage_tokens is not None:
                    completion_tokens = usage_tokens
            chunk_finish_reason = _extract_finish_reason(data)
            if chunk_finish_reason:
                finish_reason = chunk_finish_reason

        total_seconds = time.perf_counter() - start
        text = "".join(text_parts)
        if finish_reason == "length":
            raise IncompleteAiStreamError("incomplete_ai_stream: finish_reason=length")
        if not received_done:
            raise IncompleteAiStreamError("incomplete_ai_stream: missing_done")
        return AiCompletion(
            text=text,
            metrics=AiMetrics(
                first_token_seconds=first_token_seconds,
                total_seconds=total_seconds,
                completion_tokens=completion_tokens,
                output_chars=len(text),
                usage=usage,
            ),
        )

    def _build_chat_payload(self, request: AiRequest) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": self._select_model(request),
            "messages": self._build_messages(request),
            "max_completion_tokens": 800,
            "temperature": 1.0,
            "top_p": 0.95,
            "stream": True,
        }
        if request.tools:
            payload["tools"] = list(request.tools)
            if request.tool_choice is not None:
                payload["tool_choice"] = request.tool_choice
        return payload

    def _select_model(self, request: AiRequest) -> str:
        if request.image_urls:
            return self.vision_model
        return self.model

    def _build_messages(self, request: AiRequest) -> list[dict[str, object]]:
        system_parts = [
            "你是 QQ 群机器人的文本处理助手。",
            "只返回可以直接发送给用户的中文文本。",
            "不要编造你不能确认的事实。",
            "不要输出任何会执行群管、下载、重启或改配置的指令。",
        ]
        system_parts.extend(part for part in request.context if part.strip())
        messages: list[dict[str, object]] = [
            {"role": "system", "content": "\n".join(system_parts)},
            *[
                {"role": message.role, "content": message.content}
                for message in request.history
                if message.role in {"user", "assistant"} and message.content.strip()
            ],
        ]
        user_content: list[dict[str, object]] = [{"type": "text", "text": request.prompt}]
        if request.image_urls:
            user_content.extend(
                {"type": "image_url", "image_url": {"url": image_url}}
                for image_url in request.image_urls
            )
        messages.append({"role": "user", "content": user_content})
        return messages

    async def _stream(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> Any:
        if self.http_client is not None and hasattr(self.http_client, "stream"):
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


def _stream_json_lines(
    url: str,
    headers: dict[str, str],
    payload: dict[str, object],
    timeout: float,
):
    body = json_module.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=body, headers=headers, method="POST")
    with urlopen(request, timeout=timeout) as response:
        status = int(getattr(response, "status", 200))
        if status >= 400:
            raise RuntimeError(f"AI HTTP request failed: {status}")
        for raw_line in response:
            yield raw_line.decode("utf-8").strip()


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


def _extract_delta_text(data: dict[str, object]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    delta = first.get("delta")
    if not isinstance(delta, dict):
        return ""
    content = delta.get("content")
    return content if isinstance(content, str) else ""


def _extract_usage(data: dict[str, object]) -> dict[str, object] | None:
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None
    return usage


def _extract_finish_reason(data: dict[str, object]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    reason = first.get("finish_reason")
    return reason if isinstance(reason, str) else ""


def _extract_completion_tokens(usage: dict[str, object]) -> int | None:
    tokens = usage.get("completion_tokens")
    return int(tokens) if isinstance(tokens, int) else None
