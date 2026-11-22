from __future__ import annotations

import asyncio
from collections.abc import Sequence
from urllib.parse import urlsplit

from aiohttp import ClientError, ClientSession, ClientTimeout
import numpy as np

from .storage import DIMENSION


class Providers:
    def __init__(self, embedding, rerank) -> None:
        self.embedding = embedding
        self.rerank = rerank
        for provider in (embedding, rerank):
            url = urlsplit(provider.url)
            if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
                raise ValueError("DSP 模型地址无效")
            if not provider.api_key.strip() or not provider.model.strip():
                raise ValueError("请填写 DSP 模型及其 API 密钥")
        self._session = ClientSession()

    async def close(self) -> None:
        await self._session.close()

    async def _post(self, url: str, settings, payload: dict) -> dict:
        async with self._session.post(
            url, headers={"Authorization": f"Bearer {settings.api_key}"}, json=payload,
            timeout=ClientTimeout(total=settings.timeout_seconds), allow_redirects=False,
        ) as response:
            if response.status != 200:
                raise ValueError(f"DSP 模型接口返回 HTTP {response.status}")
            result = await response.json()
            if not isinstance(result, dict):
                raise ValueError("DSP 模型接口响应不是对象")
            return result

    async def embed(self, text: Sequence[str]) -> np.ndarray:
        settings = self.embedding
        payload = {"model": settings.model, "input": text[0] if len(text) == 1 else list(text)}
        if settings.send_dimensions:
            payload["dimensions"] = DIMENSION
        result = await self._post(
            settings.url.rstrip("/") + "/embeddings", settings, payload,
        )
        rows = sorted(result["data"], key=lambda row: row["index"])
        if [row["index"] for row in rows] != list(range(len(text))):
            raise ValueError("DSP 嵌入返回的条目序号不一致")
        vectors = np.asarray([row["embedding"] for row in rows], dtype=np.float32)
        if vectors.shape != (len(text), DIMENSION) or not np.isfinite(vectors).all():
            raise ValueError("DSP 嵌入返回的维度或数值不合要求")
        return vectors

    async def embed_shard(self, chunks: tuple[str, ...]) -> np.ndarray:
        batches = [chunks[i:i + 20] for i in range(0, len(chunks), 20)]

        async def embed_batch(batch: tuple[str, ...]) -> np.ndarray:
            for attempt in range(3):
                try:
                    return await self.embed(batch)
                except (ClientError, TimeoutError, ValueError) as exc:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(2**attempt)
            raise AssertionError("Unreachable")

        pieces = []
        for i in range(0, len(batches), 2):
            async with asyncio.TaskGroup() as group:
                jobs = [group.create_task(embed_batch(batch)) for batch in batches[i:i + 2]]
            pieces.extend(job.result() for job in jobs)
        return np.concatenate(pieces)

    async def reorder(self, query: str, documents: list[str], limit: int) -> list[str]:
        settings = self.rerank
        fields = {"query": query, "documents": documents}
        options = {"top_n": limit}
        if settings.instruct:
            options["instruct"] = settings.instruct
        compatible = urlsplit(settings.url).path.rstrip("/").endswith(("/compatible-api/v1/reranks", "/compatible-mode/v1/reranks"))
        if compatible:
            payload = {"model": settings.model, **fields, **options}
        else:
            payload = {"model": settings.model, "input": fields, "parameters": options}
        result = await self._post(settings.url, settings, payload)
        rows = result["results"] if compatible else result["output"]["results"]
        ordered = [row["index"] for row in sorted(rows, key=lambda row: row["relevance_score"], reverse=True)]
        if len(set(ordered)) != len(ordered) or not ordered or any(type(i) is not int or not 0 <= i < len(documents) for i in ordered):
            raise ValueError("DSP 重排序返回的条目序号无效")
        return [documents[i] for i in ordered[:limit]]
