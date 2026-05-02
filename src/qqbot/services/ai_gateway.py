from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from qqbot.services.ai_output_style import sanitize_ai_output_text
from qqbot.services.plugin_registry import get_plugin_spec_by_id


class AiPermissionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AiRequest:
    plugin_id: str
    capability: str
    prompt: str
    user_id: str
    group_id: str | None = None
    image_urls: tuple[str, ...] = ()
    context: tuple[str, ...] = ()
    history: tuple["AiMessage", ...] = ()
    tools: tuple[dict[str, object], ...] = ()
    tool_choice: str | None = None


@dataclass(frozen=True, slots=True)
class AiMessage:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class AiMetrics:
    first_token_seconds: float | None
    total_seconds: float
    completion_tokens: int | None
    output_chars: int
    usage: dict[str, object] | None = None

    @property
    def tokens_per_second(self) -> float | None:
        if self.completion_tokens is None or self.total_seconds <= 0:
            return None
        return self.completion_tokens / self.total_seconds

    @property
    def chars_per_second(self) -> float:
        if self.total_seconds <= 0:
            return 0.0
        return self.output_chars / self.total_seconds


@dataclass(frozen=True, slots=True)
class AiCompletion:
    text: str
    metrics: AiMetrics


@dataclass(frozen=True, slots=True)
class AiResponse:
    text: str
    fallback: bool = False
    metrics: AiMetrics | None = None


class AiClient(Protocol):
    async def stream_complete(self, request: AiRequest) -> AiCompletion:
        ...

    async def complete(self, request: AiRequest) -> str:
        ...


class AiGateway:
    def __init__(self, client: AiClient | None = None, timeout_seconds: float = 45.0) -> None:
        self.client = client
        self.timeout_seconds = timeout_seconds

    async def complete(self, request: AiRequest) -> AiResponse:
        spec = get_plugin_spec_by_id(request.plugin_id)
        if spec is None:
            raise AiPermissionError(f"未知插件：{request.plugin_id}")
        if request.capability not in spec.ai_capabilities:
            raise AiPermissionError(f"插件 {request.plugin_id} 未声明 AI 能力：{request.capability}")
        if self.client is None:
            return AiResponse("AI 服务尚未配置，请稍后再试。", fallback=True)

        try:
            completion = await asyncio.wait_for(
                self._complete(request),
                timeout=self.timeout_seconds,
            )
        except TimeoutError:
            return AiResponse("AI 响应超时，请稍后再试。", fallback=True)
        except Exception as exc:
            return AiResponse(f"AI 请求失败：{exc}", fallback=True)

        cleaned = sanitize_ai_output_text(completion.text)
        if not cleaned:
            return AiResponse(
                "AI 上游返回了空内容，可能是生成被中断或内容被上游过滤。请稍后重试。",
                fallback=True,
            )
        return AiResponse(cleaned, metrics=completion.metrics)

    async def _complete(self, request: AiRequest) -> AiCompletion:
        stream_complete = getattr(self.client, "stream_complete", None)
        if callable(stream_complete):
            return await stream_complete(request)

        text = await self.client.complete(request)
        return AiCompletion(
            text=text,
            metrics=AiMetrics(
                first_token_seconds=None,
                total_seconds=0.0,
                completion_tokens=None,
                output_chars=len(text),
            ),
        )
