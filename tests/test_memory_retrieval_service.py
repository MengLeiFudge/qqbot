from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.chat_memory_store import ChatMemoryStore
from qqbot.services.memory_retrieval_service import (
    RetrievalPlan,
    retrieve_memory_evidence,
)


def test_retrieval_service_returns_structured_cross_group_evidence(
    tmp_path: Path,
) -> None:
    store = ChatMemoryStore(tmp_path / "run")
    store.append_message(
        group_id=10001,
        message_id=101,
        direction="incoming",
        user_id=20001,
        sender_name="可可",
        text="喵喵喵",
        timestamp=100,
    )
    store.append_message(
        group_id=10002,
        message_id=102,
        direction="incoming",
        user_id=20001,
        sender_name="可可",
        text="我刚刚在另一个群说了什么？",
        timestamp=101,
    )

    bundle = retrieve_memory_evidence(
        store,
        RetrievalPlan(
            intent="cross_group_recent_self_messages",
            actor_id="qq:user:20001",
            space_id="qq:group:10002",
            query="我刚刚在另一个群说了什么？",
            allowed=("current_actor_cross_group_public_messages",),
            forbidden=("private_messages", "other_users_cross_group_messages"),
            exclude_space_id="qq:group:10002",
            visibility="group_public",
            limit=5,
        ),
    )

    assert bundle.plan.intent == "cross_group_recent_self_messages"
    assert bundle.messages[0].text == "喵喵喵"
    assert bundle.messages[0].space_id == "qq:group:10001"
    assert bundle.messages[0].actor_id == "qq:user:20001"
    assert bundle.messages[0].visibility == "group_public"
    assert bundle.facts == ()
    assert bundle.forbidden == ("private_messages", "other_users_cross_group_messages")


def test_retrieval_service_supports_private_conversation_memory(
    tmp_path: Path,
) -> None:
    store = ChatMemoryStore(tmp_path / "run")
    store.append_message(
        group_id="private:20001",
        space_id="qq:private:20001",
        message_id=201,
        direction="incoming",
        user_id=20001,
        actor_id="qq:user:20001",
        sender_name="可可",
        text="我喜欢写小说。",
        timestamp=100,
        visibility="private",
        memory_type="raw_message",
    )

    bundle = retrieve_memory_evidence(
        store,
        RetrievalPlan(
            intent="private_conversation",
            actor_id="qq:user:20001",
            space_id="qq:private:20001",
            query="你还记得我喜欢什么吗",
            allowed=("private_messages", "user_profile"),
            forbidden=("group_private_disclosure",),
            visibility="private",
            limit=5,
        ),
    )

    assert bundle.messages[0].space_id == "qq:private:20001"
    assert bundle.messages[0].visibility == "private"
    assert bundle.messages[0].text == "我喜欢写小说。"
    assert bundle.forbidden == ("group_private_disclosure",)
