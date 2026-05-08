from __future__ import annotations

from dataclasses import dataclass
import json

from qqbot.services.chat_memory_store import (
    ChatMemoryFact,
    ChatMemoryRecord,
    ChatMemoryStore,
    parse_qq_user_actor_id,
)


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

    group_id = parse_group_id_from_space_id(plan.space_id)
    facts = store.search_facts(group_id, plan.query, limit=plan.limit)
    messages = store.search_messages(group_id, plan.query, limit=plan.limit)
    return MemoryEvidenceBundle(plan=plan, facts=facts, messages=messages, forbidden=plan.forbidden)


def parse_group_id_from_space_id(space_id: str) -> str:
    prefix = "qq:group:"
    return space_id[len(prefix) :] if space_id.startswith(prefix) else space_id


def parse_actor_user_id(actor_id: str) -> str:
    return parse_qq_user_actor_id(actor_id)

