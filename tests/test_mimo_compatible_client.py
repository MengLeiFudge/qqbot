from pathlib import Path
import asyncio
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.ai_gateway import AiMessage, AiRequest
from qqbot.services.mimo_compatible_client import IncompleteAiStreamError, MimoCompatibleClient


class FakeHttpClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

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
        yield 'data: {"choices":[{"delta":{"content":"收"}}]}'
        yield 'data: {"choices":[{"delta":{"content":"到"}}]}'
        yield (
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}],'
            '"usage":{"completion_tokens":2,'
            '"prompt_tokens_details":{"image_tokens":17},'
            '"web_search_usage":{"tool_usage":3}}}'
        )
        yield "data: [DONE]"


def test_mimo_client_streams_chat_completions_with_api_key_header() -> None:
    http_client = FakeHttpClient()
    client = MimoCompatibleClient(
        base_url="https://api.xiaomimimo.com/v1",
        api_key="secret-key",
        model="mimo-v2.5-pro",
        timeout_seconds=8.5,
        http_client=http_client,
    )

    completion = asyncio.run(
        client.stream_complete(
            AiRequest(
                plugin_id="ai",
                capability="chat",
                prompt="你好",
                user_id="605738729",
                context=("只用中文回答。",),
                history=(AiMessage(role="assistant", content="历史回答"),),
            )
        )
    )

    assert completion.text == "收到"
    assert completion.metrics.completion_tokens == 2
    assert completion.metrics.usage == {
        "completion_tokens": 2,
        "prompt_tokens_details": {"image_tokens": 17},
        "web_search_usage": {"tool_usage": 3},
    }
    call = http_client.calls[0]
    assert call["url"] == "https://api.xiaomimimo.com/v1/chat/completions"
    assert call["headers"]["api-key"] == "secret-key"
    assert "Authorization" not in call["headers"]
    assert call["json"]["model"] == "mimo-v2.5-pro"
    assert call["json"]["stream"] is True
    assert call["json"]["max_completion_tokens"] == 800
    assert call["json"]["messages"][0]["role"] == "system"
    assert call["json"]["messages"][1] == {"role": "assistant", "content": "历史回答"}
    assert call["json"]["messages"][2]["role"] == "user"
    assert call["json"]["messages"][2]["content"] == [{"type": "text", "text": "你好"}]


def test_mimo_client_includes_images_when_request_has_images() -> None:
    http_client = FakeHttpClient()
    client = MimoCompatibleClient(
        base_url="https://api.xiaomimimo.com/v1",
        api_key="secret-key",
        model="text-model",
        vision_model="vision-model",
        http_client=http_client,
    )

    asyncio.run(
        client.stream_complete(
            AiRequest(
                plugin_id="ai",
                capability="chat",
                prompt="看看这个是什么",
                user_id="605738729",
                image_urls=("https://example.invalid/a.png",),
            )
        )
    )

    user_message = http_client.calls[0]["json"]["messages"][1]
    assert http_client.calls[0]["json"]["model"] == "vision-model"
    assert user_message["role"] == "user"
    assert user_message["content"] == [
        {"type": "text", "text": "看看这个是什么"},
        {"type": "image_url", "image_url": {"url": "https://example.invalid/a.png"}},
    ]


def test_mimo_client_keeps_text_model_without_images() -> None:
    http_client = FakeHttpClient()
    client = MimoCompatibleClient(
        base_url="https://api.xiaomimimo.com/v1",
        api_key="secret-key",
        model="text-model",
        vision_model="vision-model",
        http_client=http_client,
    )

    asyncio.run(
        client.stream_complete(
            AiRequest(plugin_id="ai", capability="chat", prompt="你好", user_id="605738729")
        )
    )

    assert http_client.calls[0]["json"]["model"] == "text-model"


def test_mimo_client_includes_function_tools_when_requested() -> None:
    http_client = FakeHttpClient()
    client = MimoCompatibleClient(
        base_url="https://api.xiaomimimo.com/v1",
        api_key="secret-key",
        model="mimo-v2.5-pro",
        http_client=http_client,
    )

    asyncio.run(
        client.stream_complete(
            AiRequest(
                plugin_id="ai",
                capability="chat",
                prompt="画一下 Cu------",
                user_id="605738729",
                tools=(
                    {
                        "type": "function",
                        "function": {
                            "name": "shapez_render_code",
                            "description": "渲染 shapez 短代码",
                            "parameters": {
                                "type": "object",
                                "properties": {"code": {"type": "string"}},
                                "required": ["code"],
                            },
                        },
                    },
                ),
                tool_choice="auto",
            )
        )
    )

    payload = http_client.calls[0]["json"]
    assert payload["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "shapez_render_code",
                "description": "渲染 shapez 短代码",
                "parameters": {
                    "type": "object",
                    "properties": {"code": {"type": "string"}},
                    "required": ["code"],
                },
            },
        }
    ]
    assert payload["tool_choice"] == "auto"


class MissingDoneHttpClient:
    async def stream(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ):
        yield 'data: {"choices":[{"delta":{"content":"半截回复"}}]}'


class LengthFinishHttpClient:
    async def stream(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ):
        yield 'data: {"choices":[{"delta":{"content":"半截回复"}}]}'
        yield 'data: {"choices":[{"delta":{},"finish_reason":"length"}]}'
        yield "data: [DONE]"


def test_mimo_client_rejects_stream_without_done_marker() -> None:
    client = MimoCompatibleClient(
        base_url="https://api.xiaomimimo.com/v1",
        api_key="secret-key",
        model="mimo-v2.5-pro",
        http_client=MissingDoneHttpClient(),
    )

    try:
        asyncio.run(
            client.stream_complete(
                AiRequest(plugin_id="ai", capability="chat", prompt="你好", user_id="605738729")
            )
        )
    except IncompleteAiStreamError as exc:
        assert "missing_done" in str(exc)
    else:
        raise AssertionError("missing [DONE] should be treated as incomplete")


def test_mimo_client_rejects_length_truncated_stream() -> None:
    client = MimoCompatibleClient(
        base_url="https://api.xiaomimimo.com/v1",
        api_key="secret-key",
        model="mimo-v2.5-pro",
        http_client=LengthFinishHttpClient(),
    )

    try:
        asyncio.run(
            client.stream_complete(
                AiRequest(plugin_id="ai", capability="chat", prompt="你好", user_id="605738729")
            )
        )
    except IncompleteAiStreamError as exc:
        assert "finish_reason=length" in str(exc)
    else:
        raise AssertionError("finish_reason=length should be treated as incomplete")
