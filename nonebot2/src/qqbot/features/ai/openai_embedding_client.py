from __future__ import annotations

import json as json_module
from typing import Any, Protocol
from urllib.request import Request, urlopen


class SyncPostClient(Protocol):
    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> Any:
        ...


class OpenAIEmbeddingClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 45.0,
        http_client: SyncPostClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.http_client = http_client

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        normalized_texts = [text.strip() for text in texts if text.strip()]
        if not normalized_texts:
            return []
        payload: dict[str, object] = {
            "model": self.model,
            "input": normalized_texts,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        response = self._post(
            f"{self.base_url}/embeddings",
            headers=headers,
            json=payload,
            timeout=self.timeout_seconds,
        )
        return _extract_embeddings(response, expected_count=len(normalized_texts))

    def _post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> Any:
        if self.http_client is not None:
            return self.http_client.post(url, headers=headers, json=json, timeout=timeout)
        return _post_json(url, headers, json, timeout)


def _extract_embeddings(response: Any, *, expected_count: int) -> list[list[float]]:
    if not isinstance(response, dict):
        raise ValueError("Embedding response must be a JSON object.")
    raw_data = response.get("data")
    if not isinstance(raw_data, list):
        raise ValueError("Embedding response missing data list.")
    ordered: dict[int, list[float]] = {}
    for fallback_index, item in enumerate(raw_data):
        if not isinstance(item, dict):
            continue
        index = int(item.get("index", fallback_index))
        embedding = item.get("embedding")
        if not isinstance(embedding, list):
            continue
        ordered[index] = [float(value) for value in embedding]
    vectors = [ordered[index] for index in range(expected_count) if index in ordered]
    if len(vectors) != expected_count:
        raise ValueError("Embedding response count does not match input count.")
    return vectors


def _post_json(
    url: str,
    headers: dict[str, str],
    payload: dict[str, object],
    timeout: float,
) -> Any:
    body = json_module.dumps(payload).encode("utf-8")
    request = Request(url, data=body, headers=headers, method="POST")
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - local config controls endpoint.
        return json_module.loads(response.read().decode("utf-8"))
