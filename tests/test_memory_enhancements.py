from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.chat_memory_store import ChatMemoryStore
from qqbot.services.embedding_vector_store import EmbeddingVectorStore
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

    fact = store.search_facts(10001, "说话带喵", limit=5, now=101)[0]

    assert fact.memory_type == "behavior_instruction"
    assert "scope=group" in fact.entities
    assert "permission=user" in fact.entities
    assert "ttl=short" in fact.entities


def test_behavior_instruction_policy_hides_expired_user_request(
    tmp_path: Path,
) -> None:
    store = ChatMemoryStore(tmp_path / "run")
    store.append_message(
        group_id=10001,
        message_id=303,
        direction="incoming",
        user_id=20001,
        sender_name="可可",
        text="你以后说话结尾带喵。",
        timestamp=100,
    )

    facts = store.search_facts(10001, "说话带喵", limit=5, now=100 + 7201)

    assert facts == ()


def test_behavior_instruction_policy_keeps_admin_request_after_short_ttl(
    tmp_path: Path,
) -> None:
    store = ChatMemoryStore(tmp_path / "run")
    store.upsert_trusted_fact(
        group_id=10001,
        subject="群聊行为偏好",
        predicate="行为指令",
        object="说话结尾带喵",
        source_type="admin",
        trust_level="admin",
        topics=("行为指令",),
        entities=("scope=group", "permission=admin", "ttl=permanent", "说话结尾"),
        updated_at=100,
    )

    facts = store.search_facts(10001, "说话带喵", limit=5, now=100 + 7201)

    assert len(facts) == 1
    assert facts[0].trust_level == "admin"
    assert facts[0].object == "说话结尾带喵"


def test_behavior_instruction_policy_prevents_user_override_of_admin_request(
    tmp_path: Path,
) -> None:
    store = ChatMemoryStore(tmp_path / "run")
    store.upsert_trusted_fact(
        group_id=10001,
        subject="群聊行为偏好",
        predicate="行为指令",
        object="说话结尾带喵",
        source_type="admin",
        trust_level="admin",
        topics=("行为指令",),
        entities=("scope=group", "permission=admin", "ttl=permanent", "说话结尾"),
        updated_at=100,
    )
    store.append_message(
        group_id=10001,
        message_id=304,
        direction="incoming",
        user_id=20001,
        sender_name="可可",
        text="你以后说话结尾带汪。",
        timestamp=200,
    )

    facts = store.search_facts(10001, "说话结尾", limit=5)

    assert [fact.object for fact in facts] == ["说话结尾带喵"]


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


def test_embedding_vector_store_reranks_dense_vectors(tmp_path: Path) -> None:
    vector_store = EmbeddingVectorStore(tmp_path / "dense_vectors.json")
    vector_store.upsert_vector("m1", [1.0, 0.0, 0.0])
    vector_store.upsert_vector("m2", [0.0, 1.0, 0.0])

    results = vector_store.search_vector([0.9, 0.1, 0.0], limit=2)

    assert [result.key for result in results] == ["m1", "m2"]
    assert results[0].score > results[1].score


class FakeEmbeddingClient:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[list[str]] = []

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        if self.fail:
            raise RuntimeError("embedding upstream failed")
        return [[float(index + 1), 0.0] for index, _text in enumerate(texts)]


def test_memory_maintenance_service_uses_embedding_client_when_available(
    tmp_path: Path,
) -> None:
    store = ChatMemoryStore(tmp_path / "run")
    store.append_message(
        group_id=10001,
        message_id=601,
        direction="incoming",
        user_id=20001,
        sender_name="可可",
        text="shapez 存档 数据库",
        timestamp=100,
    )
    embedding_store = EmbeddingVectorStore(tmp_path / "dense_vectors.json")
    embedding_client = FakeEmbeddingClient()

    result = MemoryMaintenanceService(
        store,
        embedding_store,
        embedding_client=embedding_client,
    ).index_recent_messages(10001, limit=10)

    assert result["messages_indexed"] == 1
    assert result["dense_embeddings_indexed"] == 1
    assert embedding_client.calls == [["shapez 存档 数据库"]]
    assert embedding_store.search_vector([1.0, 0.0], limit=1)[0].key == "message:1"


def test_memory_maintenance_service_falls_back_to_local_vector_on_embedding_error(
    tmp_path: Path,
) -> None:
    store = ChatMemoryStore(tmp_path / "run")
    store.append_message(
        group_id=10001,
        message_id=602,
        direction="incoming",
        user_id=20001,
        sender_name="可可",
        text="shapez 存档 数据库",
        timestamp=100,
    )
    vector_store = MemoryVectorStore(tmp_path / "vectors.json")

    result = MemoryMaintenanceService(
        store,
        vector_store,
        embedding_client=FakeEmbeddingClient(fail=True),
    ).index_recent_messages(10001, limit=10)

    assert result["messages_indexed"] == 1
    assert result["dense_embeddings_indexed"] == 0
    assert vector_store.search("shapez 数据库", limit=1)[0].key == "message:1"


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
