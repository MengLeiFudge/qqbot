from __future__ import annotations

from collections import Counter

from qqbot.services.chat_memory_store import ChatMemoryStore
from qqbot.services.memory_vector_store import MemoryVectorStore


class MemoryMaintenanceService:
    def __init__(self, store: ChatMemoryStore, vector_store: MemoryVectorStore | None = None) -> None:
        self.store = store
        self.vector_store = vector_store

    def summarize_group_topics(self, group_id: int | str, *, limit: int = 100) -> dict[str, int]:
        records = self.store.load_recent_space_messages(
            space_id=f"qq:group:{group_id}",
            visibility="group_public",
            limit=limit,
        )
        topic_counter: Counter[str] = Counter()
        source_ids: list[str] = []
        for record in records:
            for topic in record.topics:
                topic_counter[topic] += 1
            if record.message_id:
                source_ids.append(record.message_id)
        inserted = 0
        for topic, _count in topic_counter.most_common(5):
            if self.store.upsert_memory_summary(
                group_id=group_id,
                topic=topic,
                summary=f"近期群聊多次讨论 {topic}，可优先检索相关历史消息。",
                source_message_ids=tuple(source_ids[:20]),
                updated_at=max((record.timestamp for record in records), default=0),
            ):
                inserted += 1
        return {
            "messages_scanned": len(records),
            "summaries_inserted": inserted,
        }

    def index_recent_messages(self, group_id: int | str, *, limit: int = 500) -> dict[str, int]:
        if self.vector_store is None:
            return {"messages_indexed": 0}
        records = self.store.load_recent_space_messages(
            space_id=f"qq:group:{group_id}",
            visibility="group_public",
            limit=limit,
        )
        for record in records:
            self.vector_store.upsert_text(f"message:{record.id}", record.text)
        return {"messages_indexed": len(records)}
