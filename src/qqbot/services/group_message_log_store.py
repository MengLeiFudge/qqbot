from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading

from qqbot.services.ai_output_style import sanitize_ai_output_text
from qqbot.services.json_file_store import atomic_write_json, load_json_array


VALID_DIRECTIONS = {"incoming", "bot"}


@dataclass(frozen=True, slots=True)
class GroupMessageLogRecord:
    direction: str
    user_id: str
    sender_name: str
    text: str
    timestamp: int
    message_id: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "direction": self.direction,
            "user_id": self.user_id,
            "sender_name": self.sender_name,
            "text": self.text,
            "timestamp": self.timestamp,
            "message_id": self.message_id,
        }


class GroupMessageLogStore:
    _lock = threading.Lock()

    def __init__(self, data_root: Path, max_messages: int = 200) -> None:
        self.root = Path(data_root) / "admin" / "group_messages"
        self.max_messages = max(1, max_messages)

    def append_message(
        self,
        *,
        group_id: int | str,
        direction: str,
        user_id: int | str,
        sender_name: str,
        text: str,
        timestamp: int | float,
        message_id: int | str | None = None,
    ) -> None:
        normalized_text = sanitize_ai_output_text(text) if direction == "bot" else text.strip()
        if not normalized_text:
            return
        if direction not in VALID_DIRECTIONS:
            raise ValueError(f"Unsupported group message direction: {direction}")

        with self._lock:
            records = list(self.load_messages(group_id))
            records.append(
                GroupMessageLogRecord(
                    direction=direction,
                    user_id=str(user_id),
                    sender_name=sender_name.strip() or str(user_id),
                    text=normalized_text,
                    timestamp=int(timestamp),
                    message_id=str(message_id or ""),
                )
            )
            self._write_messages(group_id, records[-self.max_messages :])

    def load_messages(
        self,
        group_id: int | str,
        *,
        limit: int | None = None,
    ) -> tuple[GroupMessageLogRecord, ...]:
        path = self._path_for_group(group_id)
        if not path.exists():
            return ()

        raw_records = load_json_array(path)
        records: list[GroupMessageLogRecord] = []
        for raw in raw_records:
            if not isinstance(raw, dict):
                continue
            direction = str(raw.get("direction", "")).strip()
            text = str(raw.get("text", "")).strip()
            if direction == "bot":
                text = sanitize_ai_output_text(text)
            if direction not in VALID_DIRECTIONS or not text:
                continue
            records.append(
                GroupMessageLogRecord(
                    direction=direction,
                    user_id=str(raw.get("user_id", "")),
                    sender_name=str(raw.get("sender_name", "")).strip(),
                    text=text,
                    timestamp=int(raw.get("timestamp", 0)),
                    message_id=str(raw.get("message_id", "") or ""),
                )
            )

        effective_limit = self.max_messages if limit is None else max(0, limit)
        return tuple(records[-effective_limit:])

    def list_group_messages(
        self,
        group_names: dict[int, str] | None = None,
        *,
        limit_per_group: int | None = None,
    ) -> dict[str, object]:
        group_names = group_names or {}
        group_ids = sorted(set(self.list_group_ids()) | set(group_names))
        return {
            "groups": [
                {
                    "group_id": group_id,
                    "group_name": group_names.get(group_id, ""),
                    "display_name": self._format_group_display_name(
                        group_id,
                        group_names.get(group_id, ""),
                    ),
                    "messages": [
                        record.to_dict()
                        for record in self.load_messages(group_id, limit=limit_per_group)
                    ],
                }
                for group_id in group_ids
            ],
        }

    def list_group_ids(self) -> list[int]:
        if not self.root.exists():
            return []

        group_ids: list[int] = []
        for path in self.root.glob("*.json"):
            if path.stem.isdigit():
                group_ids.append(int(path.stem))
        return sorted(group_ids)

    def remove_group(self, group_id: int | str) -> bool:
        path = self._path_for_group(group_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def _write_messages(
        self,
        group_id: int | str,
        records: list[GroupMessageLogRecord],
    ) -> None:
        path = self._path_for_group(group_id)
        atomic_write_json(path, [record.to_dict() for record in records])

    def _path_for_group(self, group_id: int | str) -> Path:
        return self.root / f"{group_id}.json"

    @staticmethod
    def _format_group_display_name(group_id: int, group_name: str) -> str:
        return f"{group_name}（{group_id}）" if group_name else str(group_id)
