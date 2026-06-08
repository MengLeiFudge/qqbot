from __future__ import annotations

from pathlib import Path

from qqbot.config import RuntimeSettings
from qqbot.features.ai.private_memory_policy import (
    should_include_private_memory_context,
    should_record_private_chat_memory,
)
from qqbot.plugins.ai import build_ai_context
from qqbot.plugins.ai.private_memory_cache import record_private_chat_memory
from qqbot.services.message_normalizer import NormalizedMessage
from qqbot.services.settings_store import SettingsStore
from qqbot.features.ai.group_context_store import AiGroupContextStore
from qqbot.features.ai.chat_memory_store import ChatMemoryStore


class FakePrivateEvent:
    message_type = "private"
    time = 2_000_000_000
    message_id = 12345
    self_id = "1443944862"

    def __init__(self, user_id: str = "605738729") -> None:
        self.user_id = user_id

    def get_user_id(self) -> str:
        return self.user_id


def make_settings(tmp_path: Path) -> RuntimeSettings:
    return RuntimeSettings(
        data_root=tmp_path,
        author_qq=605738729,
        ai_memory_enabled=True,
    )


def test_private_short_chat_skips_memory_record_and_retrieval(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    event = FakePrivateEvent()
    normalized = NormalizedMessage(text="在吗在吗", outline="在吗在吗")

    assert not should_record_private_chat_memory(normalized)
    assert not should_include_private_memory_context(normalized)

    context = build_ai_context(
        settings,
        event,
        AiGroupContextStore(settings.data_root),
        normalized,
        settings_store=SettingsStore(settings.data_root, settings.author_qq),
    )

    joined = "\n".join(context)
    assert "本轮记忆检索计划" not in joined
    assert "本轮检索到的记忆证据" not in joined
    assert "当前发言者相关长期记忆" not in joined


def test_private_memory_question_keeps_memory_context_enabled() -> None:
    normalized = NormalizedMessage(text="你还记得我之前说过什么吗", outline="你还记得我之前说过什么吗")

    assert should_record_private_chat_memory(normalized)
    assert should_include_private_memory_context(normalized)


def test_private_memory_cache_skips_short_chat(tmp_path: Path, monkeypatch) -> None:
    event = FakePrivateEvent()
    monkeypatch.setattr(
        "qqbot.plugins.ai.private_memory_cache.normalize_onebot_event",
        lambda _event: NormalizedMessage(text="在吗在吗", outline="在吗在吗"),
    )

    record_private_chat_memory(event, ChatMemoryStore(tmp_path))

    assert ChatMemoryStore(tmp_path).search_messages(f"private:{event.user_id}", "在吗", limit=3) == ()


def test_private_raw_messages_do_not_extract_rule_facts(tmp_path: Path) -> None:
    store = ChatMemoryStore(tmp_path)

    assert store.append_message(
        group_id="private:605738729",
        message_id="998620322",
        direction="incoming",
        user_id="605738729",
        sender_name="605738729",
        text="但是你回复我太慢了。你再说句话看看呢",
        timestamp=2_000_000_000,
        space_id="qq:private:605738729",
        actor_id="qq:user:605738729",
        visibility="private",
        memory_type="raw_message",
    )
    assert store.search_facts("private:605738729", "太慢", limit=3) == ()
