from pathlib import Path
import asyncio
import base64
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.mimo_tts_client import MimoTtsClient


class FakeHttpClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        return {
            "choices": [
                {
                    "message": {
                        "audio": {
                            "data": base64.b64encode(b"wav-bytes").decode("ascii"),
                        }
                    }
                }
            ]
        }


def test_mimo_tts_client_builds_payload_and_decodes_audio() -> None:
    http_client = FakeHttpClient()
    client = MimoTtsClient(
        base_url="https://api.xiaomimimo.com/v1",
        api_key="secret-key",
        http_client=http_client,
        timeout_seconds=8.5,
    )

    audio = asyncio.run(client.synthesize("你好呀"))

    assert audio == b"wav-bytes"
    call = http_client.calls[0]
    assert call["url"] == "https://api.xiaomimimo.com/v1/chat/completions"
    assert call["headers"]["api-key"] == "secret-key"
    assert call["headers"]["Content-Type"] == "application/json"
    assert call["timeout"] == 8.5
    assert call["json"]["model"] == "mimo-v2.5-tts"
    assert call["json"]["messages"] == [
        {
            "role": "user",
            "content": "自然、清晰、适合 QQ 聊天的中文语气。",
        },
        {"role": "assistant", "content": "你好呀"},
    ]
    assert call["json"]["audio"] == {"format": "wav", "voice": "mimo_default"}


def test_mimo_tts_client_rejects_missing_audio_data() -> None:
    class MissingAudioHttpClient:
        async def post_json(self, url, *, headers, json, timeout):
            return {"choices": [{"message": {}}]}

    client = MimoTtsClient(
        base_url="https://api.xiaomimimo.com/v1",
        api_key="secret-key",
        http_client=MissingAudioHttpClient(),
    )

    try:
        asyncio.run(client.synthesize("你好呀"))
    except RuntimeError as exc:
        assert "missing audio data" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
