from pathlib import Path
import asyncio
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.ai_gateway import AiMessage, AiRequest
from qqbot.services.openai_compatible_client import OpenAICompatibleClient


class FakeHttpClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> object:
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        return FakeResponse({"output_text": "你好，我是 AI"})

    async def stream(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ):
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        yield 'data: {"type":"response.output_text.delta","delta":"你"}'
        yield 'data: {"type":"response.output_text.delta","delta":"好"}'
        yield 'data: {"type":"response.completed","response":{"usage":{"output_tokens":2}}}'
        yield "data: [DONE]"


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self.payload


def test_openai_compatible_client_complete_uses_streaming_responses_request() -> None:
    http_client = FakeHttpClient()
    client = OpenAICompatibleClient(
        base_url="https://token-plan-cn.xiaomimimo.com/v1",
        api_key="secret-key",
        model="mimo-v2.5-pro",
        timeout_seconds=8.5,
        max_output_tokens=2048,
        http_client=http_client,
    )

    text = asyncio.run(
        client.complete(
            AiRequest(
                plugin_id="arc",
                capability="explain",
                prompt="你好",
                user_id="10001",
                context=("只用中文回答。",),
            )
        )
    )

    assert text == "你好"
    call = http_client.calls[0]
    assert call["url"] == "https://token-plan-cn.xiaomimimo.com/v1/responses"
    assert call["headers"]["Authorization"] == "Bearer secret-key"
    assert call["headers"]["User-Agent"] == "codex-cli"
    assert call["json"]["model"] == "mimo-v2.5-pro"
    assert call["json"]["max_output_tokens"] == 2048
    assert "只用中文回答。" in call["json"]["instructions"]
    assert call["json"]["stream"] is True
    assert call["json"]["store"] is False
    assert call["json"]["input"][0]["role"] == "user"
    assert call["json"]["input"][0]["content"] == "你好"
    assert call["timeout"] == 8.5


def test_openai_compatible_client_accepts_base_url_with_trailing_slash() -> None:
    http_client = FakeHttpClient()
    client = OpenAICompatibleClient(
        base_url="https://token-plan-cn.xiaomimimo.com/v1/",
        api_key="secret-key",
        model="mimo-v2.5-pro",
        http_client=http_client,
    )

    asyncio.run(
        client.complete(
            AiRequest(plugin_id="arc", capability="explain", prompt="你好", user_id="10001")
        )
    )

    assert http_client.calls[0]["url"] == "https://token-plan-cn.xiaomimimo.com/v1/responses"


def test_openai_compatible_client_streams_responses_with_metrics() -> None:
    http_client = FakeHttpClient()
    client = OpenAICompatibleClient(
        base_url="https://token-plan-cn.xiaomimimo.com/v1",
        api_key="secret-key",
        model="mimo-v2.5-pro",
        timeout_seconds=8.5,
        http_client=http_client,
    )

    completion = asyncio.run(
        client.stream_complete(
            AiRequest(
                plugin_id="arc",
                capability="explain",
                prompt="你好",
                user_id="10001",
                context=("只用中文回答。",),
                history=(AiMessage(role="assistant", content="历史回答"),),
            )
        )
    )

    assert completion.text == "你好"
    assert completion.metrics.completion_tokens == 2
    assert completion.metrics.output_chars == 2
    assert completion.metrics.first_token_seconds is not None
    assert completion.metrics.first_token_seconds >= 0
    assert completion.metrics.total_seconds >= 0
    assert completion.metrics.tokens_per_second is not None
    assert completion.metrics.tokens_per_second >= 0
    call = http_client.calls[0]
    assert call["url"] == "https://token-plan-cn.xiaomimimo.com/v1/responses"
    assert call["json"]["stream"] is True
    assert "stream_options" not in call["json"]
    assert call["json"]["input"][0] == {"role": "assistant", "content": "历史回答"}
    assert call["json"]["input"][1] == {"role": "user", "content": "你好"}


def test_openai_compatible_client_includes_images_when_request_has_images() -> None:
    http_client = FakeHttpClient()
    client = OpenAICompatibleClient(
        base_url="https://example.invalid/v1",
        api_key="secret-key",
        model="vision-model",
        http_client=http_client,
    )

    asyncio.run(
        client.stream_complete(
            AiRequest(
                plugin_id="ai",
                capability="chat",
                prompt="看看这个是什么",
                user_id="10001",
                image_urls=("https://example.invalid/a.png",),
            )
        )
    )

    user_input = http_client.calls[0]["json"]["input"][0]
    assert user_input["role"] == "user"
    assert user_input["content"] == [
        {"type": "input_text", "text": "看看这个是什么"},
        {"type": "input_image", "image_url": "https://example.invalid/a.png"},
    ]
