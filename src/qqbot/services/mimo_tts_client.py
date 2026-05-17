from __future__ import annotations

import asyncio
import base64
import json as json_module
from typing import Any, Protocol
from urllib.request import Request, urlopen


DEFAULT_TTS_MODEL = "mimo-v2.5-tts"
DEFAULT_TTS_VOICE = "mimo_default"
DEFAULT_TTS_STYLE = "自然、清晰、适合 QQ 聊天的中文语气。"


class AsyncJsonPostClient(Protocol):
    async def post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> dict[str, object]:
        ...


class MimoTtsClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str = DEFAULT_TTS_MODEL,
        voice: str = DEFAULT_TTS_VOICE,
        style_prompt: str = DEFAULT_TTS_STYLE,
        timeout_seconds: float = 45.0,
        http_client: AsyncJsonPostClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model.strip() or DEFAULT_TTS_MODEL
        self.voice = voice.strip() or DEFAULT_TTS_VOICE
        self.style_prompt = style_prompt.strip() or DEFAULT_TTS_STYLE
        self.timeout_seconds = timeout_seconds
        self.http_client = http_client

    async def synthesize(self, text: str) -> bytes:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": self.style_prompt},
                {"role": "assistant", "content": text},
            ],
            "audio": {
                "format": "wav",
                "voice": self.voice,
            },
        }
        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }
        response = await self._post_json(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=self.timeout_seconds,
        )
        audio_data = _extract_audio_data(response)
        if not audio_data:
            raise RuntimeError("mimo_tts missing audio data")
        return base64.b64decode(audio_data)

    async def _post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> dict[str, object]:
        if self.http_client is not None:
            return await self.http_client.post_json(
                url,
                headers=headers,
                json=json,
                timeout=timeout,
            )
        return await asyncio.to_thread(_post_json, url, headers, json, timeout)


def _post_json(
    url: str,
    headers: dict[str, str],
    payload: dict[str, object],
    timeout: float,
) -> dict[str, object]:
    body = json_module.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=body, headers=headers, method="POST")
    with urlopen(request, timeout=timeout) as response:
        status = int(getattr(response, "status", 200))
        if status >= 400:
            raise RuntimeError(f"MiMo TTS HTTP request failed: {status}")
        raw = response.read().decode("utf-8")
    data = json_module.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError("mimo_tts invalid json response")
    return data


def _extract_audio_data(response: dict[str, object]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    audio = message.get("audio")
    if not isinstance(audio, dict):
        return ""
    data: Any = audio.get("data")
    return data if isinstance(data, str) else ""
