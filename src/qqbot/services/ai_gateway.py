from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from qqbot.services.ai_output_style import sanitize_ai_output_text
from qqbot.services.plugin_registry import get_plugin_spec_by_id


AI_FALLBACK_NOT_CONFIGURED = "棉花糖还没接上线，暂时没法回应喵。"
AI_FALLBACK_TIMEOUT = "棉花糖等回复等到快化掉啦，稍后再试试喵。"
AI_FALLBACK_CLIENT_ERROR = "棉花糖刚刚摔了一跤，换个问法再试试喵。"
AI_FALLBACK_SAFETY_REJECTED = "棉花糖被安全结界拦住啦，这个话题现在不能继续说喵。换个问法吧。"
AI_FALLBACK_EMPTY = "棉花糖抓到了一团空空的棉花，没有生成出回复喵。再问一次吧。"


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
    def __init__(
        self,
        client: AiClient | None = None,
        timeout_seconds: float = 45.0,
        *,
        max_attempts: int = 2,
        first_attempt_timeout_seconds: float | None = None,
    ) -> None:
        self.client = client
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max(1, int(max_attempts))
        self.first_attempt_timeout_seconds = first_attempt_timeout_seconds

    async def complete(self, request: AiRequest) -> AiResponse:
        spec = get_plugin_spec_by_id(request.plugin_id)
        if spec is None:
            raise AiPermissionError(f"未知插件：{request.plugin_id}")
        if request.capability not in spec.ai_capabilities:
            raise AiPermissionError(f"插件 {request.plugin_id} 未声明 AI 能力：{request.capability}")
        if self.client is None:
            return AiResponse(AI_FALLBACK_NOT_CONFIGURED, fallback=True)

        last_fallback = AI_FALLBACK_CLIENT_ERROR
        try:
            for attempt in range(self.max_attempts):
                timeout = self._timeout_for_attempt(attempt)
                try:
                    completion = await asyncio.wait_for(
                        self._complete(request),
                        timeout=timeout,
                    )
                except TimeoutError:
                    last_fallback = AI_FALLBACK_TIMEOUT
                    continue
                except Exception as exc:
                    last_fallback = format_ai_exception_fallback(exc)
                    if last_fallback == AI_FALLBACK_SAFETY_REJECTED:
                        return AiResponse(last_fallback, fallback=True)
                    continue

                cleaned = sanitize_ai_output_text(completion.text)
                if not cleaned:
                    last_fallback = AI_FALLBACK_EMPTY
                    continue
                if is_safety_rejection_text(cleaned):
                    return AiResponse(AI_FALLBACK_SAFETY_REJECTED, fallback=True)
                return AiResponse(cleaned, metrics=completion.metrics)
        except Exception as exc:
            return AiResponse(format_ai_exception_fallback(exc), fallback=True)
        return AiResponse(last_fallback, fallback=True)

    def _timeout_for_attempt(self, attempt: int) -> float:
        if attempt == 0 and self.first_attempt_timeout_seconds is not None:
            return max(0.001, min(float(self.first_attempt_timeout_seconds), self.timeout_seconds))
        return self.timeout_seconds

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


def format_ai_exception_fallback(exc: Exception) -> str:
    if is_safety_rejection_text(str(exc)):
        return AI_FALLBACK_SAFETY_REJECTED
    return AI_FALLBACK_CLIENT_ERROR


def is_safety_rejection_text(text: str) -> bool:
    detail = text.lower()
    rejection_markers = (
        "the request was rejected",
        "considered high risk",
        "content policy",
        "safety policy",
        "unsafe content",
        "请求被拒绝",
        "内容被拒绝",
        "安全策略",
        "安全结界",
        "不能继续说",
    )
    if any(marker in detail for marker in rejection_markers):
        return True

    paired_risk_markers = (
        "high risk",
        "rejected",
        "拒绝",
    )
    return sum(1 for marker in paired_risk_markers if marker in detail) >= 2
