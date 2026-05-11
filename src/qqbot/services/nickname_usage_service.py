from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from qqbot.services.chat_memory_store import ChatMemoryStore
from qqbot.services.group_nick_store import normalize_call_name


@dataclass(frozen=True, slots=True)
class NicknameUsageEntry:
    name: str
    count: int
    ratio: float


@dataclass(frozen=True, slots=True)
class NicknameUsageSummary:
    sample_size: int
    entries: tuple[NicknameUsageEntry, ...]


class NicknameUsageService:
    def __init__(self, memory_store: ChatMemoryStore) -> None:
        self.memory_store = memory_store

    def summarize(
        self,
        *,
        group_id: int | str,
        user_id: int | str,
        limit: int = 100,
    ) -> NicknameUsageSummary:
        records = self.memory_store.load_recent_group_user_messages(
            group_id=group_id,
            user_id=user_id,
            limit=limit,
        )
        counter: Counter[str] = Counter()
        for record in records:
            name = normalize_call_name(record.sender_name)
            if name:
                counter[name] += 1

        sample_size = sum(counter.values())
        if sample_size <= 0:
            return NicknameUsageSummary(sample_size=0, entries=())

        entries = tuple(
            NicknameUsageEntry(
                name=name,
                count=count,
                ratio=count / sample_size,
            )
            for name, count in sorted(
                counter.items(),
                key=lambda item: (-item[1], item[0]),
            )
        )
        return NicknameUsageSummary(sample_size=sample_size, entries=entries)
