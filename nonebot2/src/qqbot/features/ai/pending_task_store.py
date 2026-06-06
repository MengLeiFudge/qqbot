from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import time

from qqbot.features.ai.message_decision import AiMessageDecision


@dataclass(frozen=True, slots=True)
class AiPendingTaskRecord:
    task_id: str
    status: str
    group_id: str
    user_id: str
    message_id: str
    prompt: str
    decision: dict[str, object]
    created_at: int
    updated_at: int
    ack_sent: bool = False
    result_message_id: str = ""
    error: str = ""


class AiPendingTaskStore:
    def __init__(self, data_root: Path) -> None:
        self.path = Path(data_root) / "ai" / "pending_tasks.json"

    def create_ack_task(
        self,
        *,
        group_id: int | str | None,
        user_id: int | str,
        message_id: int | str | None,
        prompt: str,
        decision: AiMessageDecision,
        now: int | None = None,
    ) -> AiPendingTaskRecord:
        now = now if now is not None else int(time.time())
        task_id = self._build_task_id(group_id, user_id, message_id, now)
        record = AiPendingTaskRecord(
            task_id=task_id,
            status="ack_sent",
            group_id=str(group_id or ""),
            user_id=str(user_id),
            message_id=str(message_id or ""),
            prompt=prompt,
            decision=self._decision_payload(decision),
            created_at=now,
            updated_at=now,
            ack_sent=True,
        )
        records = [item for item in self.list_records() if item.task_id != task_id]
        records.append(record)
        self._write_records(records[-200:])
        return record

    def complete_task(
        self,
        task_id: str,
        *,
        result_message_id: int | str | None = None,
        error: str = "",
        now: int | None = None,
    ) -> bool:
        records = list(self.list_records())
        updated = False
        now = now if now is not None else int(time.time())
        next_records: list[AiPendingTaskRecord] = []
        for record in records:
            if record.task_id != task_id:
                next_records.append(record)
                continue
            next_records.append(
                AiPendingTaskRecord(
                    task_id=record.task_id,
                    status="failed" if error else "completed",
                    group_id=record.group_id,
                    user_id=record.user_id,
                    message_id=record.message_id,
                    prompt=record.prompt,
                    decision=record.decision,
                    created_at=record.created_at,
                    updated_at=now,
                    ack_sent=record.ack_sent,
                    result_message_id=str(result_message_id or ""),
                    error=error,
                )
            )
            updated = True
        if updated:
            self._write_records(next_records[-200:])
        return updated

    def list_records(self, *, status: str = "", limit: int = 100) -> tuple[AiPendingTaskRecord, ...]:
        if not self.path.exists():
            return ()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ()
        records = []
        for item in raw if isinstance(raw, list) else []:
            if not isinstance(item, dict):
                continue
            record = AiPendingTaskRecord(
                task_id=str(item.get("task_id", "")),
                status=str(item.get("status", "")),
                group_id=str(item.get("group_id", "")),
                user_id=str(item.get("user_id", "")),
                message_id=str(item.get("message_id", "")),
                prompt=str(item.get("prompt", "")),
                decision=item.get("decision", {}) if isinstance(item.get("decision", {}), dict) else {},
                created_at=int(item.get("created_at", 0) or 0),
                updated_at=int(item.get("updated_at", 0) or 0),
                ack_sent=bool(item.get("ack_sent", False)),
                result_message_id=str(item.get("result_message_id", "")),
                error=str(item.get("error", "")),
            )
            if status and record.status != status:
                continue
            records.append(record)
        records.sort(key=lambda item: (-item.updated_at, item.task_id))
        return tuple(records[: max(1, limit)])

    def _write_records(self, records: list[AiPendingTaskRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(record) for record in records]
        tmp_path = self.path.with_name(f"{self.path.name}.{time.time_ns()}.tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self.path)

    @staticmethod
    def _build_task_id(
        group_id: int | str | None,
        user_id: int | str,
        message_id: int | str | None,
        now: int,
    ) -> str:
        scope = f"g{group_id}" if group_id is not None else "private"
        anchor = str(message_id or now)
        return f"{scope}:u{user_id}:m{anchor}"

    @staticmethod
    def _decision_payload(decision: AiMessageDecision) -> dict[str, object]:
        return {
            "trigger_kind": decision.trigger_kind.value,
            "intent": decision.intent.value,
            "difficulty": decision.difficulty.value,
            "latency_policy": decision.latency_policy.value,
            "format_policy": decision.format_policy.value,
            "domain": decision.domain.value,
            "confidence": decision.confidence,
            "reason": decision.reason,
            "fe_feedback_kind": decision.fe_feedback_kind.value,
        }
