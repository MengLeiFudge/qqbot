from __future__ import annotations

from pathlib import Path

from qqbot.config import RuntimeSettings
from qqbot.plugins.ai import (
    build_ai_context,
    should_include_private_memory_context,
    should_record_private_chat_memory,
)
from qqbot.services.message_normalizer import NormalizedMessage
from qqbot.services.settings_store import SettingsStore
from qqbot.features.ai.group_context_store import AiGroupContextStore


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
