import asyncio
from io import BytesIO
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.request import Request

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.rightcodes_draw_client import (
    RIGHTCODES_DRAW_DEFAULT_MODEL,
    RightCodesDrawClient,
    RightCodesDrawRequest,
    format_rightcodes_draw_failure,
    format_rightcodes_draw_model_help,
    format_rightcodes_draw_success,
    looks_like_rightcodes_draw_help_command,
    looks_like_rightcodes_draw_command,
    parse_rightcodes_draw_command,
)


class FakeDrawHttpClient:
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
        yield 'data: {"choices":[{"delta":{"content":"https://example.com/a.png"}}]}'
        yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
        yield "data: [DONE]"


def test_parse_rightcodes_draw_command_uses_default_model() -> None:
    request = parse_rightcodes_draw_command("棉花生图 一只拿着糖果的猫娘")

    assert request == RightCodesDrawRequest(
        prompt="一只拿着糖果的猫娘",
        model="gpt-image-2",
    )
    assert RIGHTCODES_DRAW_DEFAULT_MODEL == "gpt-image-2"


def test_parse_rightcodes_draw_command_accepts_natural_draw_prompt() -> None:
    request = parse_rightcodes_draw_command("生成一个糖果城堡的图片")

    assert request == RightCodesDrawRequest(
        prompt="一个糖果城堡",
        model=RIGHTCODES_DRAW_DEFAULT_MODEL,
    )


def test_parse_rightcodes_draw_command_accepts_explicit_model() -> None:
    request = parse_rightcodes_draw_command("棉花糖生图 [gpt-image-2-vip] 赛博城市")

    assert request == RightCodesDrawRequest(
        prompt="赛博城市",
        model="gpt-image-2-vip",
    )


def test_parse_rightcodes_draw_command_accepts_plain_model_prefix() -> None:
    request = parse_rightcodes_draw_command("棉花糖生图 nano-banana-pro 水彩风城堡")

    assert request == RightCodesDrawRequest(
        prompt="水彩风城堡",
        model="nano-banana-pro",
    )


def test_parse_rightcodes_draw_command_ignores_general_chat() -> None:
    assert parse_rightcodes_draw_command("帮我画一下 CrRgSbWy") is None


def test_looks_like_rightcodes_draw_command_matches_draw_commands() -> None:
    assert looks_like_rightcodes_draw_command("棉花生图 一只猫")
    assert looks_like_rightcodes_draw_command("生成一只猫的图片")
    assert not looks_like_rightcodes_draw_command("普通聊天")


def test_rightcodes_draw_model_help_lists_prices() -> None:
    assert looks_like_rightcodes_draw_help_command("生图模型说明")
    assert looks_like_rightcodes_draw_help_command("棉花糖生图价格")
    assert not looks_like_rightcodes_draw_help_command("棉花糖生图 一只猫")

    help_text = format_rightcodes_draw_model_help()

    assert "gpt-image-2（默认）：0.04r/张" in help_text
    assert "gpt-image-2-vip：0.13r/张" in help_text
    assert "nano-banana：0.14r/张" in help_text
    assert "nano-banana-2：0.12r/张" in help_text
    assert "nano-banana-pro：0.18r/张" in help_text
    assert "棉花糖生图 [模型名] 提示词" in help_text


def test_rightcodes_draw_client_streams_chat_completions() -> None:
    http_client = FakeDrawHttpClient()
    client = RightCodesDrawClient(
        api_key="secret",
        timeout_seconds=99,
        http_client=http_client,
    )

    result = asyncio.run(
        client.draw(
            RightCodesDrawRequest(
                prompt="一张猫娘图片",
                model="nano-banana-2",
                image_urls=("https://example.com/ref.png",),
            )
        )
    )

    assert result.image_url == "https://example.com/a.png"
    call = http_client.calls[0]
    assert call["url"] == "https://www.right.codes/draw/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer secret"
    assert call["timeout"] == 99
    assert call["json"]["model"] == "nano-banana-2"
    assert call["json"]["stream"] is True
    message = call["json"]["messages"][0]
    assert message["role"] == "user"
    assert message["content"][0]["type"] == "text"
    assert message["content"][1] == {
        "type": "image_url",
        "image_url": {"url": "https://example.com/ref.png"},
    }


def test_format_rightcodes_draw_success() -> None:
    result = type("DrawResult", (), {"total_seconds": 53.72})()

    assert (
        format_rightcodes_draw_success(result, model="nano-banana-2")
        == "✨ 生成成功！\n📊 耗时: 53.72s\n🖼️ 数量: 1张\n🤖 模型: nano-banana-2"
    )


def test_format_rightcodes_draw_failure() -> None:
    assert format_rightcodes_draw_failure(RuntimeError("API 错误 (400)")) == "❌ 生成失败: API 错误 (400)"


def test_format_rightcodes_draw_failure_uses_upstream_http_body() -> None:
    request = Request("https://example.com")
    exc = HTTPError(
        request.full_url,
        400,
        "Bad Request",
        hdrs={},
        fp=BytesIO(b'{"error":{"message":"content policy violation"}}'),
    )

    assert format_rightcodes_draw_failure(exc) == "❌ 生成失败: content policy violation"
