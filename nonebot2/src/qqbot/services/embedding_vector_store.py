from __future__ import annotations

from dataclasses import dataclass
import json
from math import sqrt
from pathlib import Path


@dataclass(frozen=True, slots=True)
class EmbeddingSearchResult:
    key: str
    score: float


class EmbeddingVectorStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def upsert_vector(self, key: str, vector: list[float] | tuple[float, ...]) -> None:
        normalized = [float(value) for value in vector]
        if not key.strip() or not normalized:
            return
        data = self._load()
        data[key] = normalized
        self._save(data)

    def search_vector(
        self,
        vector: list[float] | tuple[float, ...],
        *,
        limit: int = 5,
    ) -> tuple[EmbeddingSearchResult, ...]:
        if limit <= 0:
            return ()
        target = [float(value) for value in vector]
        rows = [
            EmbeddingSearchResult(key=key, score=_cosine(target, stored_vector))
            for key, stored_vector in self._load().items()
        ]
        rows.sort(key=lambda row: row.score, reverse=True)
        return tuple(rows[:limit])

    def _load(self) -> dict[str, list[float]]:
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        payload: dict[str, list[float]] = {}
        for key, value in raw.items():
            if isinstance(key, str) and isinstance(value, list):
                payload[key] = [float(item) for item in value]
        return payload

    def _save(self, payload: dict[str, list[float]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _cosine(left: list[float], right: list[float]) -> float:
    length = min(len(left), len(right))
    if length <= 0:
        return 0.0
    dot = sum(left[index] * right[index] for index in range(length))
    norm_a = sqrt(sum(value * value for value in left[:length]))
    norm_b = sqrt(sum(value * value for value in right[:length]))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
