from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.openai_embedding_client import OpenAIEmbeddingClient


class FakeHttpClient:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def post(
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
        return self.response


def test_openai_embedding_client_posts_embeddings_payload() -> None:
    http = FakeHttpClient(
        {
            "data": [
                {"index": 0, "embedding": [0.1, 0.2]},
                {"index": 1, "embedding": [0.3, 0.4]},
            ]
        }
    )
    client = OpenAIEmbeddingClient(
        base_url="https://api.openai.com/v1/",
        api_key="secret-key",
        model="text-embedding-3-small",
        timeout_seconds=12.5,
        http_client=http,
    )

    vectors = client.embed_texts(["第一条", "第二条"])

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert http.calls == [
        {
            "url": "https://api.openai.com/v1/embeddings",
            "headers": {
                "Authorization": "Bearer secret-key",
                "Content-Type": "application/json",
            },
            "json": {
                "model": "text-embedding-3-small",
                "input": ["第一条", "第二条"],
            },
            "timeout": 12.5,
        }
    ]


def test_openai_embedding_client_restores_response_order_by_index() -> None:
    http = FakeHttpClient(
        {
            "data": [
                {"index": 1, "embedding": [0.3, 0.4]},
                {"index": 0, "embedding": [0.1, 0.2]},
            ]
        }
    )
    client = OpenAIEmbeddingClient(
        base_url="https://api.openai.com/v1",
        api_key="secret-key",
        model="text-embedding-3-small",
        http_client=http,
    )

    vectors = client.embed_texts(["第一条", "第二条"])

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
