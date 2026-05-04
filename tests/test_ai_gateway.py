from pathlib import Path
import asyncio
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.ai_gateway import (
    AiCompletion,
    AiGateway,
    AiMetrics,
    AiPermissionError,
    AiRequest,
)


class FakeAiClient:
    async def complete(self, request: AiRequest) -> str:
        return f"AI:{request.prompt}"

    async def stream_complete(self, request: AiRequest) -> AiCompletion:
        return AiCompletion(
            text=f"AI:{request.prompt}",
            metrics=AiMetrics(
                first_token_seconds=0.1,
                total_seconds=0.3,
                completion_tokens=3,
                output_chars=5,
            ),
        )


class SlowAiClient:
    async def complete(self, request: AiRequest) -> str:
        await asyncio.sleep(0.05)
        return "late"

    async def stream_complete(self, request: AiRequest) -> AiCompletion:
        await asyncio.sleep(0.05)
        return AiCompletion(
            text="late",
            metrics=AiMetrics(
                first_token_seconds=0.05,
                total_seconds=0.05,
                completion_tokens=1,
                output_chars=4,
            ),
        )


class FailingAiClient:
    async def stream_complete(self, request: AiRequest) -> AiCompletion:
        raise RuntimeError("boom")

    async def complete(self, request: AiRequest) -> str:
        raise RuntimeError("boom")


class EmptyAiClient:
    async def stream_complete(self, request: AiRequest) -> AiCompletion:
        return AiCompletion(
            text="   ",
            metrics=AiMetrics(
                first_token_seconds=None,
                total_seconds=0.1,
                completion_tokens=0,
                output_chars=0,
            ),
        )

    async def complete(self, request: AiRequest) -> str:
        return "   "


def test_gateway_calls_client_for_declared_capability() -> None:
    gateway = AiGateway(client=FakeAiClient())

    response = asyncio.run(
        gateway.complete(
            AiRequest(plugin_id="arc", capability="explain", prompt="你好", user_id="10001")
        )
    )

    assert response.text == "AI:你好"
    assert response.fallback is False
    assert response.metrics is not None
    assert response.metrics.completion_tokens == 3
    assert response.metrics.tokens_per_second == 10.0


def test_gateway_rejects_undeclared_capability() -> None:
    gateway = AiGateway(client=FakeAiClient())

    with pytest.raises(AiPermissionError):
        asyncio.run(
            gateway.complete(
                AiRequest(
                    plugin_id="group_assistant",
                    capability="chat",
                    prompt="禁言",
                    user_id="10001",
                )
            )
        )


def test_gateway_rejects_unknown_plugin() -> None:
    gateway = AiGateway(client=FakeAiClient())

    with pytest.raises(AiPermissionError):
        asyncio.run(
            gateway.complete(
                AiRequest(plugin_id="missing", capability="chat", prompt="你好", user_id="10001")
            )
        )


def test_gateway_returns_fallback_when_client_is_missing() -> None:
    gateway = AiGateway(client=None)

    response = asyncio.run(
        gateway.complete(
            AiRequest(plugin_id="arc", capability="explain", prompt="你好", user_id="10001")
        )
    )

    assert response.fallback is True
    assert "AI 服务尚未配置" in response.text
    assert response.metrics is None


def test_gateway_returns_fallback_on_timeout() -> None:
    gateway = AiGateway(client=SlowAiClient(), timeout_seconds=0.01)

    response = asyncio.run(
        gateway.complete(
            AiRequest(plugin_id="arc", capability="explain", prompt="你好", user_id="10001")
        )
    )

    assert response.fallback is True
    assert "AI 响应超时" in response.text
    assert response.metrics is None


def test_gateway_returns_fallback_on_client_error() -> None:
    gateway = AiGateway(client=FailingAiClient())

    response = asyncio.run(
        gateway.complete(
            AiRequest(plugin_id="arc", capability="explain", prompt="你好", user_id="10001")
        )
    )

    assert response.fallback is True
    assert "AI 请求失败：boom" in response.text
    assert response.metrics is None


def test_gateway_returns_clear_fallback_on_empty_content() -> None:
    gateway = AiGateway(client=EmptyAiClient())

    response = asyncio.run(
        gateway.complete(
            AiRequest(plugin_id="arc", capability="explain", prompt="你好", user_id="10001")
        )
    )

    assert response.fallback is True
    assert "AI 上游返回了空内容" in response.text
    assert response.metrics is None


class MarkdownAiClient:
    async def stream_complete(self, request: AiRequest) -> AiCompletion:
        return AiCompletion(
            text="# 标题\n\n- **第一段**\n\n> `第二段`",
            metrics=AiMetrics(
                first_token_seconds=0.1,
                total_seconds=0.2,
                completion_tokens=6,
                output_chars=24,
            ),
        )

    async def complete(self, request: AiRequest) -> str:
        return "# 标题\n\n- **第一段**\n\n> `第二段`"


def test_gateway_strips_markdown_and_blank_paragraphs() -> None:
    gateway = AiGateway(client=MarkdownAiClient())

    response = asyncio.run(
        gateway.complete(
            AiRequest(plugin_id="arc", capability="explain", prompt="你好", user_id="10001")
        )
    )

    assert response.fallback is False
    assert response.text == "标题\n第一段\n第二段"
