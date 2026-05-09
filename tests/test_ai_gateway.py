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


class HighRiskRejectedAiClient:
    async def stream_complete(self, request: AiRequest) -> AiCompletion:
        raise RuntimeError("The request was rejected because it was considered high risk")

    async def complete(self, request: AiRequest) -> str:
        raise RuntimeError("The request was rejected because it was considered high risk")


class HighRiskTextAiClient:
    async def stream_complete(self, request: AiRequest) -> AiCompletion:
        return AiCompletion(
            text="The request was rejected because it was considered high risk",
            metrics=AiMetrics(
                first_token_seconds=0.1,
                total_seconds=0.2,
                completion_tokens=9,
                output_chars=60,
            ),
        )

    async def complete(self, request: AiRequest) -> str:
        return "The request was rejected because it was considered high risk"


class RiskExplanationAiClient:
    async def stream_complete(self, request: AiRequest) -> AiCompletion:
        text = "这个设定有风险，但可以通过限制权限来降低风险。"
        return AiCompletion(
            text=text,
            metrics=AiMetrics(
                first_token_seconds=0.1,
                total_seconds=0.2,
                completion_tokens=12,
                output_chars=len(text),
            ),
        )


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


class EmptyThenSuccessAiClient:
    def __init__(self) -> None:
        self.calls = 0

    async def stream_complete(self, request: AiRequest) -> AiCompletion:
        self.calls += 1
        if self.calls == 1:
            return AiCompletion(
                text="   ",
                metrics=AiMetrics(
                    first_token_seconds=None,
                    total_seconds=0.1,
                    completion_tokens=0,
                    output_chars=0,
                ),
            )
        return AiCompletion(
            text="第二次成功",
            metrics=AiMetrics(
                first_token_seconds=0.1,
                total_seconds=0.2,
                completion_tokens=4,
                output_chars=5,
            ),
        )


class TimeoutThenSuccessAiClient:
    def __init__(self) -> None:
        self.calls = 0

    async def stream_complete(self, request: AiRequest) -> AiCompletion:
        self.calls += 1
        if self.calls == 1:
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
        return AiCompletion(
            text="重试成功",
            metrics=AiMetrics(
                first_token_seconds=0.001,
                total_seconds=0.001,
                completion_tokens=4,
                output_chars=4,
            ),
        )


class IncompleteThenSuccessAiClient:
    def __init__(self) -> None:
        self.calls = 0

    async def stream_complete(self, request: AiRequest) -> AiCompletion:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("incomplete_ai_stream: missing_done")
        return AiCompletion(
            text="重试后的完整回复",
            metrics=AiMetrics(
                first_token_seconds=0.1,
                total_seconds=0.2,
                completion_tokens=8,
                output_chars=8,
            ),
        )


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
    assert [attempt.result for attempt in response.attempts] == ["success"]


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
    assert response.text == "棉花糖还没接上线，暂时没法回应喵。"
    assert response.metrics is None


def test_gateway_returns_fallback_on_timeout() -> None:
    gateway = AiGateway(client=SlowAiClient(), timeout_seconds=0.01, max_attempts=1)

    response = asyncio.run(
        gateway.complete(
            AiRequest(plugin_id="arc", capability="explain", prompt="你好", user_id="10001")
        )
    )

    assert response.fallback is True
    assert response.text == "棉花糖等回复等到快化掉啦，稍后再试试喵。"
    assert response.metrics is None
    assert response.fallback_reason == "timeout"
    assert [attempt.result for attempt in response.attempts] == ["timeout"]


def test_gateway_returns_fallback_on_client_error() -> None:
    gateway = AiGateway(client=FailingAiClient(), max_attempts=1)

    response = asyncio.run(
        gateway.complete(
            AiRequest(plugin_id="arc", capability="explain", prompt="你好", user_id="10001")
        )
    )

    assert response.fallback is True
    assert response.text == "棉花糖刚刚摔了一跤，换个问法再试试喵。"
    assert "boom" not in response.text
    assert "上游" not in response.text
    assert response.metrics is None


def test_gateway_returns_cute_fallback_on_high_risk_rejection() -> None:
    gateway = AiGateway(client=HighRiskRejectedAiClient())

    response = asyncio.run(
        gateway.complete(
            AiRequest(plugin_id="arc", capability="explain", prompt="你好", user_id="10001")
        )
    )

    assert response.fallback is True
    assert response.text == "棉花糖被安全结界拦住啦，这个话题现在不能继续说喵。换个问法吧。"
    assert "high risk" not in response.text
    assert "rejected" not in response.text
    assert response.metrics is None


def test_gateway_returns_cute_fallback_when_high_risk_rejection_is_text() -> None:
    gateway = AiGateway(client=HighRiskTextAiClient())

    response = asyncio.run(
        gateway.complete(
            AiRequest(plugin_id="arc", capability="explain", prompt="你好", user_id="10001")
        )
    )

    assert response.fallback is True
    assert response.text == "棉花糖被安全结界拦住啦，这个话题现在不能继续说喵。换个问法吧。"
    assert "high risk" not in response.text
    assert "rejected" not in response.text
    assert response.metrics is None


def test_gateway_keeps_normal_risk_explanations() -> None:
    gateway = AiGateway(client=RiskExplanationAiClient())

    response = asyncio.run(
        gateway.complete(
            AiRequest(plugin_id="arc", capability="explain", prompt="有什么风险", user_id="10001")
        )
    )

    assert response.fallback is False
    assert response.text == "这个设定有风险，但可以通过限制权限来降低风险。"
    assert response.metrics is not None


def test_gateway_returns_clear_fallback_on_empty_content() -> None:
    gateway = AiGateway(client=EmptyAiClient(), max_attempts=1)

    response = asyncio.run(
        gateway.complete(
            AiRequest(plugin_id="arc", capability="explain", prompt="你好", user_id="10001")
        )
    )

    assert response.fallback is True
    assert response.text == "棉花糖抓到了一团空空的棉花，没有生成出回复喵。再问一次吧。"
    assert response.metrics is None
    assert response.fallback_reason == "empty"
    assert [attempt.result for attempt in response.attempts] == ["empty"]


def test_gateway_retries_empty_content_before_fallback() -> None:
    client = EmptyThenSuccessAiClient()
    gateway = AiGateway(client=client)

    response = asyncio.run(
        gateway.complete(
            AiRequest(plugin_id="arc", capability="explain", prompt="你好", user_id="10001")
        )
    )

    assert response.fallback is False
    assert response.text == "第二次成功"
    assert client.calls == 2
    assert [attempt.result for attempt in response.attempts] == ["empty", "success"]


def test_gateway_retries_timeout_with_short_first_attempt() -> None:
    client = TimeoutThenSuccessAiClient()
    gateway = AiGateway(client=client, timeout_seconds=1.0, first_attempt_timeout_seconds=0.01)

    response = asyncio.run(
        gateway.complete(
            AiRequest(plugin_id="arc", capability="explain", prompt="你好", user_id="10001")
        )
    )

    assert response.fallback is False
    assert response.text == "重试成功"
    assert client.calls == 2
    assert [attempt.result for attempt in response.attempts] == ["timeout", "success"]


def test_gateway_retries_incomplete_stream_before_success() -> None:
    client = IncompleteThenSuccessAiClient()
    gateway = AiGateway(client=client)

    response = asyncio.run(
        gateway.complete(
            AiRequest(plugin_id="arc", capability="explain", prompt="你好", user_id="10001")
        )
    )

    assert response.fallback is False
    assert response.text == "重试后的完整回复"
    assert client.calls == 2
    assert [attempt.result for attempt in response.attempts] == ["incomplete", "success"]


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
