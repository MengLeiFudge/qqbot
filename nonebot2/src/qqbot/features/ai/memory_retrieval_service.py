from __future__ import annotations

from dataclasses import dataclass
import json

from qqbot.features.ai.chat_memory_store import (
    ChatMemoryFact,
    ChatMemoryRecord,
    ChatMemoryStore,
    parse_qq_user_actor_id,
)
from qqbot.features.ai.embedding_vector_store import EmbeddingVectorStore
from qqbot.features.ai.memory_vector_store import MemoryVectorStore
from qqbot.features.ai.memory_maintenance_service import EmbeddingClient


@dataclass(frozen=True, slots=True)
class RetrievalPlan:
    intent: str
    actor_id: str
    space_id: str
    query: str
    allowed: tuple[str, ...]
    forbidden: tuple[str, ...]
    exclude_space_id: str = ""
    visibility: str = "group_public"
    limit: int = 6

    def to_prompt_json(self) -> str:
        payload = {
            "intent": self.intent,
            "actor_id": self.actor_id,
            "space_id": self.space_id,
            "allowed": list(self.allowed),
            "forbidden": list(self.forbidden),
        }
        if self.exclude_space_id:
            payload["exclude_space_id"] = self.exclude_space_id
        if self.visibility:
            payload["visibility"] = self.visibility
        return json.dumps(payload, ensure_ascii=False, separators=(", ", ": "))


@dataclass(frozen=True, slots=True)
class MemoryEvidenceBundle:
    plan: RetrievalPlan
    facts: tuple[ChatMemoryFact, ...]
    messages: tuple[ChatMemoryRecord, ...]
    forbidden: tuple[str, ...]


def retrieve_memory_evidence(
    store: ChatMemoryStore,
    plan: RetrievalPlan,
    *,
    vector_store: MemoryVectorStore | EmbeddingVectorStore | None = None,
    embedding_client: EmbeddingClient | None = None,
) -> MemoryEvidenceBundle:
    if plan.limit <= 0:
        return MemoryEvidenceBundle(plan=plan, facts=(), messages=(), forbidden=plan.forbidden)

    if plan.intent == "forbidden_private_disclosure_in_group":
        return MemoryEvidenceBundle(plan=plan, facts=(), messages=(), forbidden=plan.forbidden)

    if plan.intent == "cross_group_recent_self_messages":
        return MemoryEvidenceBundle(
            plan=plan,
            facts=(),
            messages=store.load_recent_actor_messages_across_spaces(
                actor_id=plan.actor_id,
                exclude_space_id=plan.exclude_space_id or plan.space_id,
                visibility=plan.visibility,
                limit=plan.limit,
            ),
            forbidden=plan.forbidden,
        )

    if plan.intent == "private_conversation":
        private_messages = _rerank_messages_with_vectors(
            store.search_space_messages(
                space_id=plan.space_id,
                query=plan.query,
                visibility=plan.visibility,
                limit=plan.limit,
            ),
            plan.query,
            vector_store,
            embedding_client,
        )
        public_actor_messages = store.load_recent_actor_messages_across_spaces(
            actor_id=plan.actor_id,
            exclude_space_id=plan.space_id,
            visibility="group_public",
            limit=plan.limit,
        )
        return MemoryEvidenceBundle(
            plan=plan,
            facts=(),
            messages=(*private_messages, *public_actor_messages)[: plan.limit],
            forbidden=plan.forbidden,
        )

    group_id = parse_group_id_from_space_id(plan.space_id)
    facts = store.search_facts(group_id, plan.query, limit=plan.limit)
    messages = _rerank_messages_with_vectors(
        store.search_messages(group_id, plan.query, limit=plan.limit),
        plan.query,
        vector_store,
        embedding_client,
    )
    return MemoryEvidenceBundle(plan=plan, facts=facts, messages=messages, forbidden=plan.forbidden)


def format_evidence_bundle(bundle: MemoryEvidenceBundle) -> str:
    payload = {
        "plan": json.loads(bundle.plan.to_prompt_json()),
        "facts": [
            {
                "space_id": fact.space_id,
                "visibility": fact.visibility,
                "memory_type": fact.memory_type,
                "subject": fact.subject,
                "predicate": fact.predicate,
                "object": fact.object,
                "confidence": fact.confidence,
                "source_message_ids": list(fact.source_message_ids),
            }
            for fact in bundle.facts
        ],
        "messages": [
            {
                "space_id": record.space_id,
                "actor_id": record.actor_id,
                "visibility": record.visibility,
                "memory_type": record.memory_type,
                "sender_name": record.sender_name,
                "user_id": record.user_id,
                "text": record.text,
                "timestamp": record.timestamp,
            }
            for record in bundle.messages
        ],
        "forbidden": list(bundle.forbidden),
    }
    return "结构化记忆证据：" + json.dumps(payload, ensure_ascii=False, separators=(", ", ": "))


def parse_group_id_from_space_id(space_id: str) -> str:
    prefix = "qq:group:"
    return space_id[len(prefix) :] if space_id.startswith(prefix) else space_id


def parse_actor_user_id(actor_id: str) -> str:
    return parse_qq_user_actor_id(actor_id)


def _rerank_messages_with_vectors(
    messages: tuple[ChatMemoryRecord, ...],
    query: str,
    vector_store: MemoryVectorStore | EmbeddingVectorStore | None,
    embedding_client: EmbeddingClient | None = None,
) -> tuple[ChatMemoryRecord, ...]:
    if vector_store is None or not messages:
        return messages
    if isinstance(vector_store, EmbeddingVectorStore) and embedding_client is not None:
        try:
            vectors = embedding_client.embed_texts([query])
            results = vector_store.search_vector(vectors[0], limit=max(len(messages) * 2, len(messages)))
        except Exception:
            return messages
    else:
        results = vector_store.search(query, limit=max(len(messages) * 2, len(messages)))
    scores = {result.key: result.score for result in results}
    return tuple(
        sorted(
            messages,
            key=lambda record: (
                -scores.get(f"message:{record.id}", -1.0),
                -record.timestamp,
                -record.id,
            ),
        )
    )
