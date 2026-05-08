from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.plugins.private_memory_cache import record_private_chat_memory
from qqbot.services.chat_memory_store import ChatMemoryStore


@dataclass
class FakePrivateMessageEvent:
    user_id: int
    time: int
    message_id: int = 233
    text: str = "你好"
    segments: list[object] | None = None

    def get_user_id(self) -> str:
        return str(self.user_id)

    def get_plaintext(self) -> str:
        return self.text

    @property
    def original_message(self):
        return FakeMessage(self.text, self.segments)

    @property
    def message(self):
        return self.original_message


class FakeSegment:
    def __init__(self, segment_type: str, data: dict[str, str] | None = None) -> None:
        self.type = segment_type
        self.data = data or {}


class FakeMessage:
    def __init__(self, text: str, segments: list[object] | None = None) -> None:
        self.text = text
        self.segments = segments

    def extract_plain_text(self) -> str:
        return self.text

    def __iter__(self):
        if self.segments is not None:
            return iter(self.segments)
        return iter([FakeSegment("text", {"text": self.text})])


def test_record_private_chat_memory_persists_private_space_message(tmp_path: Path) -> None:
    store = ChatMemoryStore(tmp_path / "run")
    event = FakePrivateMessageEvent(
        user_id=605738729,
        time=1_800_000_000,
        text="私聊里讨论 OpenAI embedding",
    )

    record_private_chat_memory(event, store)

    records = store.search_space_messages(
        space_id="qq:private:605738729",
        visibility="private",
        query="OpenAI embedding",
        limit=5,
    )
    assert len(records) == 1
    assert records[0].group_id == "private:605738729"
    assert records[0].actor_id == "qq:user:605738729"
    assert records[0].visibility == "private"
    assert records[0].memory_type == "raw_message"


def test_record_private_chat_memory_uses_unique_message_guard(tmp_path: Path) -> None:
    store = ChatMemoryStore(tmp_path / "run")
    event = FakePrivateMessageEvent(
        user_id=605738729,
        time=1_800_000_000,
        message_id=996,
        text="同一条私聊只记一次",
    )

    record_private_chat_memory(event, store)
    record_private_chat_memory(event, store)

    records = store.search_space_messages(
        space_id="qq:private:605738729",
        visibility="private",
        query="只记一次",
        limit=5,
    )
    assert len(records) == 1
