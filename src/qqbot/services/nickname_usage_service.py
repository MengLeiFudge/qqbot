from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from qqbot.services.chat_memory_store import ChatMemoryStore
from qqbot.services.group_nick_store import GroupNickStore, normalize_call_name


@dataclass(frozen=True, slots=True)
class NicknameUsageEntry:
    name: str
    count: int
    ratio: float


@dataclass(frozen=True, slots=True)
class NicknameUsageSummary:
    sample_size: int
    entries: tuple[NicknameUsageEntry, ...]


@dataclass(frozen=True, slots=True)
class NicknameIdentityCandidate:
    user_id: str
    call_name: str
    matched_names: tuple[str, ...]
    summary: NicknameUsageSummary


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

    def find_identity_candidates(
        self,
        *,
        group_id: int | str,
        query_name: str,
        nick_store: GroupNickStore,
        limit: int = 100,
        max_candidates: int = 3,
    ) -> tuple[NicknameIdentityCandidate, ...]:
        normalized_query = normalize_call_name(query_name)
        if not normalized_query:
            return ()

        group_records = nick_store.records.get(str(group_id), {})
        candidates: list[NicknameIdentityCandidate] = []
        for user_id, record in group_records.items():
            if not user_id.isdigit():
                continue
            summary = self.summarize(group_id=group_id, user_id=user_id, limit=limit)
            call_name = nick_store.resolve_call_name(int(group_id), int(user_id))
            names = [
                call_name,
                record.card,
                record.nickname,
                *[entry.name for entry in summary.entries],
            ]
            matched_names = tuple(
                dict.fromkeys(
                    name
                    for name in (normalize_call_name(item) for item in names)
                    if name and name == normalized_query
                )
            )
            if not matched_names:
                continue
            candidates.append(
                NicknameIdentityCandidate(
                    user_id=user_id,
                    call_name=call_name,
                    matched_names=matched_names,
                    summary=summary,
                )
            )

        def sort_key(candidate: NicknameIdentityCandidate) -> tuple[int, int, int]:
            matched_count = next(
                (
                    entry.count
                    for entry in candidate.summary.entries
                    if entry.name in candidate.matched_names
                ),
                0,
            )
            return (-matched_count, -candidate.summary.sample_size, int(candidate.user_id))

        return tuple(sorted(candidates, key=sort_key)[:max_candidates])
