from __future__ import annotations

import asyncio
from pathlib import Path

from qqbot.config import RuntimeSettings
from qqbot.features.ai.gateway import AiMessage, AiRequest
from qqbot.features.ai.gemini_generate_content_client import GeminiGenerateContentClient
from qqbot.features.ai.runtime import build_ai_gateway


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self.payload


class FakeHttpClient:
    def __init__(self) -> None:
        self.url = ""
        self.headers: dict[str, str] = {}
        self.payload: dict[str, object] = {}

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> FakeResponse:
        self.url = url
        self.headers = headers
        self.payload = json
        return FakeResponse(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "你好"},
                                {"text": "，已切到 Gemini。"},
                            ]
                        }
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 10,
                    "candidatesTokenCount": 4,
                    "totalTokenCount": 14,
                },
            }
        )


def test_gemini_client_calls_generate_content_endpoint() -> None:
    http_client = FakeHttpClient()
    client = GeminiGenerateContentClient(
        base_url="https://www.packyapi.com/",
        api_key="secret",
        model="gemini-3-flash-preview",
        max_output_tokens=1234,
        http_client=http_client,
    )

    completion = asyncio.run(
        client.stream_complete(
            AiRequest(
                plugin_id="ai",
                capability="chat",
                prompt="切过去了吗",
                user_id="10001",
                context=("当前群聊上下文",),
                history=(AiMessage(role="assistant", content="上一轮回复"),),
            )
        )
    )

    assert http_client.url == (
        "https://www.packyapi.com/v1beta/models/"
        "gemini-3-flash-preview:generateContent"
    )
    assert http_client.headers["x-goog-api-key"] == "secret"
    assert http_client.headers["User-Agent"] == "qqbot-nonebot2"
    assert http_client.payload["generationConfig"] == {"maxOutputTokens": 1234}
    assert http_client.payload["contents"] == [
        {"role": "model", "parts": [{"text": "上一轮回复"}]},
        {"role": "user", "parts": [{"text": "切过去了吗"}]},
    ]
    assert "当前群聊上下文" in str(http_client.payload["systemInstruction"])
    assert completion.text == "你好，已切到 Gemini。"
    assert completion.metrics.completion_tokens == 4


def test_runtime_builds_gemini_gateway(tmp_path: Path, monkeypatch) -> None:
    profile_file = tmp_path / "qqbot.toml"
    profile_file.write_text(
        """
[ai]
default_profile = "packyapi-gemini"

[ai.providers.packyapi-gemini]
provider = "gemini"
base_url = "https://www.packyapi.com"
model = "gemini-3-flash-preview"
api_key_env = "QQBOT_AI_KEY_PACKYAPI"
timeout_seconds = 45
max_output_tokens = 4096
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("QQBOT_AI_KEY_PACKYAPI", "secret")

    gateway = build_ai_gateway(
        RuntimeSettings(ai_profile_file=profile_file),
        "packyapi-gemini",
    )

    assert isinstance(gateway.client, GeminiGenerateContentClient)
