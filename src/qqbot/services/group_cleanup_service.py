from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from qqbot.services.ai_group_context_store import AiGroupContextStore
from qqbot.services.chat_memory_store import ChatMemoryStore
from qqbot.services.group_message_log_store import GroupMessageLogStore
from qqbot.services.group_nick_store import GroupNickStore
from qqbot.services.settings_store import SettingsStore


@dataclass(frozen=True, slots=True)
class GroupCleanupResult:
    group_id: int
    removed_items: tuple[str, ...]


class GroupCleanupService:
    def __init__(self, data_root: Path, author_qq: int) -> None:
        self.data_root = Path(data_root)
        self.store = SettingsStore(self.data_root, author_qq)

    def cleanup_group(self, group_id: int | str) -> GroupCleanupResult:
        normalized_group_id = int(str(group_id).strip())
        removed: list[str] = []

        removed.extend(self.store.remove_group_scoped_settings(normalized_group_id))

        nick_store = GroupNickStore(self.data_root / "settings" / "group_nick.json")
        if nick_store.remove_group(normalized_group_id):
            removed.append("settings/group_nick.json")

        if AiGroupContextStore(self.data_root).remove_group(normalized_group_id):
            removed.append(f"ai/group_context/{normalized_group_id}.json")

        if GroupMessageLogStore(self.data_root).remove_group(normalized_group_id):
            removed.append(f"admin/group_messages/{normalized_group_id}.json")

        if ChatMemoryStore(self.data_root).remove_group(normalized_group_id):
            removed.append(f"ai/chat_memory.sqlite3:{normalized_group_id}")

        return GroupCleanupResult(
            group_id=normalized_group_id,
            removed_items=tuple(removed),
        )
