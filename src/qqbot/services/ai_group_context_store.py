from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AiGroupMessageRecord:
    user_id: str
    sender_name: str
    text: str
    timestamp: int


class AiGroupContextStore:
    def __init__(self, data_root: Path, max_messages: int = 100) -> None:
        self.root = Path(data_root) / "ai" / "group_context"
        self.max_messages = max(1, max_messages)

    def append_message(
        self,
        *,
        group_id: int | str,
        user_id: int | str,
        sender_name: str,
        text: str,
        timestamp: int,
    ) -> None:
        normalized_text = text.strip()
        if not normalized_text:
            return

        records = list(self.load_messages(group_id))
        records.append(
            AiGroupMessageRecord(
                user_id=str(user_id),
                sender_name=sender_name.strip() or str(user_id),
                text=normalized_text,
                timestamp=int(timestamp),
            )
        )
        self._write_messages(group_id, records[-self.max_messages :])

    def load_messages(
        self,
        group_id: int | str,
        *,
        limit: int | None = None,
    ) -> tuple[AiGroupMessageRecord, ...]:
        path = self._path_for_group(group_id)
        if not path.exists():
            return ()

        raw_records = json.loads(path.read_text(encoding="utf-8"))
        records: list[AiGroupMessageRecord] = []
        for raw in raw_records:
            if not isinstance(raw, dict):
                continue
            text = str(raw.get("text", "")).strip()
            if not text:
                continue
            records.append(
                AiGroupMessageRecord(
                    user_id=str(raw.get("user_id", "")),
                    sender_name=str(raw.get("sender_name", "")).strip(),
                    text=text,
                    timestamp=int(raw.get("timestamp", 0)),
                )
            )

        effective_limit = self.max_messages if limit is None else max(0, limit)
        return tuple(records[-effective_limit:])

    def _write_messages(
        self,
        group_id: int | str,
        records: list[AiGroupMessageRecord],
    ) -> None:
        path = self._path_for_group(group_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                [
                    {
                        "user_id": record.user_id,
                        "sender_name": record.sender_name,
                        "text": record.text,
                        "timestamp": record.timestamp,
                    }
                    for record in records
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _path_for_group(self, group_id: int | str) -> Path:
        return self.root / f"{group_id}.json"
