from __future__ import annotations

from dataclasses import dataclass
import json
from math import sqrt
from pathlib import Path


@dataclass(frozen=True, slots=True)
class VectorSearchResult:
    key: str
    score: float


class MemoryVectorStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def upsert_text(self, key: str, text: str) -> None:
        data = self._load()
        data[key] = _embed(text)
        self._save(data)

    def search(self, query: str, *, limit: int = 5) -> tuple[VectorSearchResult, ...]:
        if limit <= 0:
            return ()
        target = _embed(query)
        rows = [
            VectorSearchResult(key=key, score=_cosine(target, vector))
            for key, vector in self._load().items()
        ]
        rows.sort(key=lambda row: row.score, reverse=True)
        return tuple(rows[:limit])

    def _load(self) -> dict[str, dict[str, float]]:
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        payload: dict[str, dict[str, float]] = {}
        for key, value in raw.items():
            if isinstance(key, str) and isinstance(value, dict):
                payload[key] = {str(term): float(score) for term, score in value.items()}
        return payload

    def _save(self, payload: dict[str, dict[str, float]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _embed(text: str) -> dict[str, float]:
    # 轻量可选向量：字符 3-gram 词袋，避免引入外部依赖。
    normalized = text.strip().lower()
    grams: dict[str, float] = {}
    for token in normalized.replace("，", " ").replace(",", " ").split():
        grams[token] = grams.get(token, 0.0) + 2.0
    for index in range(max(len(normalized) - 2, 1)):
        gram = normalized[index : index + 3] if len(normalized) >= 3 else normalized
        if not gram:
            continue
        grams[gram] = grams.get(gram, 0.0) + 1.0
    return grams


def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
    terms = set(left) | set(right)
    dot = sum(left.get(term, 0.0) * right.get(term, 0.0) for term in terms)
    norm_a = sqrt(sum(value * value for value in left.values()))
    norm_b = sqrt(sum(value * value for value in right.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
