from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import time


@dataclass(frozen=True, slots=True)
class AiAttemptDiagnostics:
    attempt: int
    timeout_seconds: float
    result: str
    total_seconds: float
    first_token_seconds: float | None = None
    completion_tokens: int | None = None
    output_chars: int = 0
    error_type: str = ""

    @property
    def tokens_per_second(self) -> float | None:
        if self.completion_tokens is None or self.total_seconds <= 0:
            return None
        return self.completion_tokens / self.total_seconds

    def to_payload(self) -> dict[str, object]:
        return {
            "attempt": self.attempt,
            "timeout_seconds": self.timeout_seconds,
            "result": self.result,
            "total_seconds": self.total_seconds,
            "first_token_seconds": self.first_token_seconds,
            "completion_tokens": self.completion_tokens,
            "output_chars": self.output_chars,
            "tokens_per_second": self.tokens_per_second,
            "error_type": self.error_type,
        }


@dataclass(frozen=True, slots=True)
class AiDiagnosticsRecord:
    timestamp: int
    profile: str
    provider: str
    model: str
    scope: str
    group_id: str
    user_id: str
    result: str
    fallback: bool
    fallback_reason: str
    prompt_chars: int
    context_chars: int
    history_messages: int
    image_count: int
    local_prepare_seconds: float
    total_seconds: float
    attempts: tuple[AiAttemptDiagnostics, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp,
            "profile": self.profile,
            "provider": self.provider,
            "model": self.model,
            "scope": self.scope,
            "group_id": self.group_id,
            "user_id": self.user_id,
            "result": self.result,
            "fallback": self.fallback,
            "fallback_reason": self.fallback_reason,
            "prompt_chars": self.prompt_chars,
            "context_chars": self.context_chars,
            "history_messages": self.history_messages,
            "image_count": self.image_count,
            "local_prepare_seconds": self.local_prepare_seconds,
            "total_seconds": self.total_seconds,
            "attempt_count": len(self.attempts),
            "attempts": [attempt.to_payload() for attempt in self.attempts],
        }


class AiDiagnosticsStore:
    def __init__(self, data_root: Path, max_records: int = 500) -> None:
        self.path = Path(data_root) / "ai" / "diagnostics.jsonl"
        self.max_records = max(1, max_records)

    def append(self, record: AiDiagnosticsRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        records = [*self.load(limit=self.max_records - 1), record.to_payload()]
        self.path.write_text(
            "\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n",
            encoding="utf-8",
        )

    def load(self, *, limit: int = 100) -> list[dict[str, object]]:
        if limit <= 0 or not self.path.exists():
            return []
        records: list[dict[str, object]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                records.append(payload)
        return records[-limit:]

    def summary(self, *, limit: int = 100) -> dict[str, object]:
        records = self.load(limit=limit)
        attempts = [
            attempt
            for record in records
            for attempt in record.get("attempts", [])
            if isinstance(attempt, dict)
        ]
        successful_attempts = [
            attempt for attempt in attempts if str(attempt.get("result", "")) == "success"
        ]
        return {
            "count": len(records),
            "success_count": sum(1 for record in records if not bool(record.get("fallback", False))),
            "fallback_count": sum(1 for record in records if bool(record.get("fallback", False))),
            "retry_success_count": sum(
                1
                for record in records
                if not bool(record.get("fallback", False)) and int(record.get("attempt_count", 0)) > 1
            ),
            "empty_count": _count_result(attempts, "empty"),
            "timeout_count": _count_result(attempts, "timeout"),
            "client_error_count": _count_result(attempts, "client_error"),
            "avg_local_prepare_seconds": _avg(
                float(record.get("local_prepare_seconds", 0.0) or 0.0) for record in records
            ),
            "avg_total_seconds": _avg(
                float(record.get("total_seconds", 0.0) or 0.0) for record in records
            ),
            "avg_first_token_seconds": _avg(
                float(attempt.get("first_token_seconds"))
                for attempt in successful_attempts
                if attempt.get("first_token_seconds") is not None
            ),
            "p95_first_token_seconds": _percentile(
                [
                    float(attempt.get("first_token_seconds"))
                    for attempt in successful_attempts
                    if attempt.get("first_token_seconds") is not None
                ],
                0.95,
            ),
            "avg_tokens_per_second": _avg(
                float(attempt.get("tokens_per_second"))
                for attempt in successful_attempts
                if attempt.get("tokens_per_second") is not None
            ),
            "records": list(reversed(records)),
        }


def build_ai_diagnostics_record(
    *,
    profile: str,
    provider: str,
    model: str,
    scope: str,
    group_id: str,
    user_id: str,
    fallback: bool,
    fallback_reason: str,
    prompt_chars: int,
    context_chars: int,
    history_messages: int,
    image_count: int,
    local_prepare_seconds: float,
    total_seconds: float,
    attempts: tuple[AiAttemptDiagnostics, ...],
    now: int | None = None,
) -> AiDiagnosticsRecord:
    return AiDiagnosticsRecord(
        timestamp=now if now is not None else int(time.time()),
        profile=profile,
        provider=provider,
        model=model,
        scope=scope,
        group_id=group_id,
        user_id=user_id,
        result="fallback" if fallback else "success",
        fallback=fallback,
        fallback_reason=fallback_reason,
        prompt_chars=prompt_chars,
        context_chars=context_chars,
        history_messages=history_messages,
        image_count=image_count,
        local_prepare_seconds=local_prepare_seconds,
        total_seconds=total_seconds,
        attempts=attempts,
    )


def _count_result(attempts: list[dict[str, object]], result: str) -> int:
    return sum(1 for attempt in attempts if str(attempt.get("result", "")) == result)


def _avg(values) -> float | None:
    items = [float(value) for value in values]
    if not items:
        return None
    return sum(items) / len(items)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * percentile))))
    return ordered[index]
