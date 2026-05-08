from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.chat_memory_store import ChatMemoryStore
from qqbot.services.memory_maintenance_service import MemoryMaintenanceService
from qqbot.services.memory_retrieval_service import (
    RetrievalPlan,
    format_evidence_bundle,
    retrieve_memory_evidence,
)
from qqbot.services.memory_vector_store import MemoryVectorStore


def test_evidence_bundle_formats_structured_prompt_block(tmp_path: Path) -> None:
    store = ChatMemoryStore(tmp_path / "run")
    store.append_message(
        group_id=10001,
        message_id=301,
        direction="incoming",
        user_id=20001,
        sender_name="可可",
        text="可可喜欢研究数据库。",
        timestamp=100,
    )

    bundle = retrieve_memory_evidence(
        store,
        RetrievalPlan(
            intent="current_group_memory_search",
            actor_id="qq:user:20001",
            space_id="qq:group:10001",
            query="可可喜欢什么",
            allowed=("current_group_memory",),
            forbidden=("private_messages",),
            limit=5,
        ),
    )

    block = format_evidence_bundle(bundle)

    assert "结构化记忆证据：" in block
    assert '"intent": "current_group_memory_search"' in block
    assert '"visibility": "group_public"' in block
    assert '"memory_type": "fact"' in block
    assert "可可喜欢研究数据库" in block


def test_behavior_instruction_policy_keeps_user_request_temporary(
    tmp_path: Path,
) -> None:
    store = ChatMemoryStore(tmp_path / "run")
    store.append_message(
        group_id=10001,
        message_id=302,
        direction="incoming",
        user_id=20001,
        sender_name="可可",
        text="你以后说话结尾带喵。",
        timestamp=100,
    )

    fact = store.search_facts(10001, "说话带喵", limit=5)[0]

    assert fact.memory_type == "behavior_instruction"
    assert "scope=group" in fact.entities
    assert "permission=user" in fact.entities
    assert "ttl=short" in fact.entities


def test_memory_maintenance_service_builds_topic_summaries(tmp_path: Path) -> None:
    store = ChatMemoryStore(tmp_path / "run")
    for index, text in enumerate(
        (
            "今天讨论 AI 长期记忆。",
            "AI 记忆需要按主题摘要。",
            "数据库可以保存聊天记录。",
        ),
        start=1,
    ):
        store.append_message(
            group_id=10001,
            message_id=400 + index,
            direction="incoming",
            user_id=20001,
            sender_name="可可",
            text=text,
            timestamp=100 + index,
        )

    result = MemoryMaintenanceService(store).summarize_group_topics(10001, limit=10)
    summaries = store.search_facts(10001, "主题摘要 AI", limit=5)

    assert result["summaries_inserted"] >= 1
    assert summaries[0].subject == "群主题摘要"
    assert summaries[0].predicate == "摘要"
    assert "AI" in summaries[0].object
    assert summaries[0].memory_type == "summary"


def test_optional_vector_store_reranks_with_embeddings(tmp_path: Path) -> None:
    vector_store = MemoryVectorStore(tmp_path / "vectors.json")
    vector_store.upsert_text("m1", "shapez 存档 数据库")
    vector_store.upsert_text("m2", "今天吃什么")

    results = vector_store.search("shapez 数据库", limit=2)

    assert [result.key for result in results] == ["m1", "m2"]
    assert results[0].score > results[1].score


def test_retrieval_service_can_rerank_messages_with_vector_store(tmp_path: Path) -> None:
    store = ChatMemoryStore(tmp_path / "run")
    store.append_message(
        group_id=10001,
        message_id=501,
        direction="incoming",
        user_id=20001,
        sender_name="可可",
        text="数据库",
        timestamp=101,
    )
    store.append_message(
        group_id=10001,
        message_id=502,
        direction="incoming",
        user_id=20001,
        sender_name="可可",
        text="shapez 存档 数据库",
        timestamp=100,
    )
    vector_store = MemoryVectorStore(tmp_path / "vectors.json")
    MemoryMaintenanceService(store, vector_store).index_recent_messages(10001, limit=10)

    bundle = retrieve_memory_evidence(
        store,
        RetrievalPlan(
            intent="current_group_memory_search",
            actor_id="qq:user:20001",
            space_id="qq:group:10001",
            query="shapez 数据库",
            allowed=("current_group_memory",),
            forbidden=("private_messages",),
            limit=5,
        ),
        vector_store=vector_store,
    )

    assert bundle.messages[0].message_id == "502"
