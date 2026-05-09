from __future__ import annotations

import asyncio
import json as json_module
import time
from typing import Any, Protocol
from urllib.request import Request, urlopen

from qqbot.services.ai_gateway import AiClient, AiCompletion, AiMetrics, AiRequest


class AsyncPostClient(Protocol):
    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> Any:
        ...

    async def stream(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> Any:
        ...


class OpenAICompatibleClient(AiClient):
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 45.0,
        max_output_tokens: int = 4096,
        supports_vision: bool = False,
        http_client: AsyncPostClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max(1, int(max_output_tokens))
        self.supports_vision = supports_vision
        self.http_client = http_client

    async def complete(self, request: AiRequest) -> str:
        completion = await self.stream_complete(request)
        return completion.text

    async def stream_complete(self, request: AiRequest) -> AiCompletion:
        payload = self._build_responses_payload(request, stream=True)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "codex-cli",
        }

        start = time.perf_counter()
        first_token_seconds: float | None = None
        text_parts: list[str] = []
        completion_tokens: int | None = None
        async for line in self._stream(
            f"{self.base_url}/responses",
            headers=headers,
            json=payload,
            timeout=self.timeout_seconds,
        ):
            event = _parse_sse_data(line)
            if event is None:
                continue
            if event == "[DONE]":
                break
            data = json_module.loads(event)
            token = self._extract_response_delta_text(data)
            if token:
                if first_token_seconds is None:
                    first_token_seconds = time.perf_counter() - start
                text_parts.append(token)
            usage_tokens = self._extract_response_output_tokens(data)
            if usage_tokens is not None:
                completion_tokens = usage_tokens
            completed_text = self._extract_response_text_from_event(data)
            if completed_text and not text_parts:
                if first_token_seconds is None:
                    first_token_seconds = time.perf_counter() - start
                text_parts.append(completed_text)

        total_seconds = time.perf_counter() - start
        text = "".join(text_parts)
        return AiCompletion(
            text=text,
            metrics=AiMetrics(
                first_token_seconds=first_token_seconds,
                total_seconds=total_seconds,
                completion_tokens=completion_tokens,
                output_chars=len(text),
            ),
        )

    async def _post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> Any:
        if self.http_client is not None:
            return await self.http_client.post(url, headers=headers, json=json, timeout=timeout)

        return await asyncio.to_thread(
            _post_json,
            url,
            headers,
            json,
            timeout,
        )

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

    def _build_responses_payload(self, request: AiRequest, *, stream: bool) -> dict[str, object]:
        return {
            "model": self.model,
            "instructions": self._build_instructions(request),
            "input": self._build_input(request),
            "max_output_tokens": self.max_output_tokens,
            "stream": stream,
            "store": False,
        }

    @staticmethod
    def _build_instructions(request: AiRequest) -> str:
        system_parts = [
            "你是 QQ 群机器人的文本处理助手。",
            "只返回可以直接发送给用户的中文文本。",
            "不要编造你不能确认的事实。",
            "不要输出任何会执行群管、下载、重启或改配置的指令。",
        ]
        system_parts.extend(part for part in request.context if part.strip())
        return "\n".join(system_parts)

    def _build_input(self, request: AiRequest) -> list[dict[str, object]]:
        messages: list[dict[str, object]] = [
            *[
                {"role": message.role, "content": message.content}
                for message in request.history
                if message.role in {"user", "assistant"} and message.content.strip()
            ],
        ]
        if not request.image_urls:
            messages.append({"role": "user", "content": request.prompt})
            return messages

        content: list[dict[str, object]] = [
            {"type": "input_text", "text": request.prompt},
            *[
                {"type": "input_image", "image_url": image_url}
                for image_url in request.image_urls
            ],
        ]
        messages.append({"role": "user", "content": content})
        return messages

    @staticmethod
    def _extract_text(data: dict[str, object]) -> str:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        first = choices[0]
        if not isinstance(first, dict):
            return ""
        message = first.get("message")
        if not isinstance(message, dict):
            return ""
        content = message.get("content")
        return content if isinstance(content, str) else ""

    @staticmethod
    def _extract_response_text(data: dict[str, object]) -> str:
        output_text = data.get("output_text")
        if isinstance(output_text, str):
            return output_text

        output = data.get("output")
        if not isinstance(output, list):
            return ""

        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)

    @staticmethod
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

    @staticmethod
    def _extract_response_delta_text(data: dict[str, object]) -> str:
        event_type = data.get("type")
        if event_type in {"response.output_text.delta", "response.text.delta"}:
            delta = data.get("delta")
            return delta if isinstance(delta, str) else ""
        return ""

    @staticmethod
    def _extract_completion_tokens(data: dict[str, object]) -> int | None:
        usage = data.get("usage")
        if not isinstance(usage, dict):
            return None
        tokens = usage.get("completion_tokens")
        return int(tokens) if isinstance(tokens, int) else None

    @staticmethod
    def _extract_response_output_tokens(data: dict[str, object]) -> int | None:
        usage = data.get("usage")
        if isinstance(usage, dict):
            output_tokens = usage.get("output_tokens")
            if isinstance(output_tokens, int):
                return output_tokens

        response = data.get("response")
        if not isinstance(response, dict):
            return None
        response_usage = response.get("usage")
        if not isinstance(response_usage, dict):
            return None
        output_tokens = response_usage.get("output_tokens")
        return int(output_tokens) if isinstance(output_tokens, int) else None

    @staticmethod
    def _extract_response_text_from_event(data: dict[str, object]) -> str:
        response = data.get("response")
        if not isinstance(response, dict):
            return ""
        return OpenAICompatibleClient._extract_response_text(response)


class UrlLibResponse:
    def __init__(self, status: int, payload: dict[str, object]) -> None:
        self.status = status
        self.payload = payload

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise RuntimeError(f"AI HTTP request failed: {self.status}")

    def json(self) -> dict[str, object]:
        return self.payload


def _post_json(
    url: str,
    headers: dict[str, str],
    payload: dict[str, object],
    timeout: float,
) -> UrlLibResponse:
    body = json_module.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=body, headers=headers, method="POST")
    with urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
        data = json_module.loads(raw) if raw else {}
        status = int(getattr(response, "status", 200))
        return UrlLibResponse(status, data)


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
