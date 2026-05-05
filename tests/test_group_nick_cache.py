from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.plugins.group_nick_cache import (
    record_group_message_context,
    record_group_message_log,
    record_group_nick_event,
)
from qqbot.services.ai_group_context_store import AiGroupContextStore
from qqbot.services.group_message_log_store import GroupMessageLogStore
from qqbot.services.group_nick_store import GroupNickStore


@dataclass
class FakeSender:
    card: str = ""
    nickname: str = ""


@dataclass
class FakeGroupMessageEvent:
    group_id: int
    sender: FakeSender
    time: int
    user_id: int
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


def test_record_group_nick_event_persists_sender_card_and_nickname(tmp_path: Path) -> None:
    store = GroupNickStore(tmp_path / "run" / "settings" / "group_nick.json")
    event = FakeGroupMessageEvent(
        group_id=516286670,
        sender=FakeSender(card="萌泪", nickname="MLJ"),
        time=1_800_000_000,
        user_id=605738729,
    )

    record_group_nick_event(event, store)

    payload = json.loads((tmp_path / "run" / "settings" / "group_nick.json").read_text(encoding="utf-8"))
    assert payload["516286670"]["605738729"]["card"] == "萌泪"
    assert payload["516286670"]["605738729"]["nickname"] == "MLJ"
    assert payload["516286670"]["605738729"]["updated_at"] == 1_800_000_000_000


def test_record_group_nick_event_skips_empty_card_and_nickname(tmp_path: Path) -> None:
    store = GroupNickStore(tmp_path / "run" / "settings" / "group_nick.json")
    event = FakeGroupMessageEvent(
        group_id=516286670,
        sender=FakeSender(card="", nickname=""),
        time=1_800_000_000,
        user_id=605738729,
    )

    record_group_nick_event(event, store)

    assert not (tmp_path / "run" / "settings" / "group_nick.json").exists()


def test_record_group_message_context_persists_plain_text(tmp_path: Path) -> None:
    store = AiGroupContextStore(tmp_path / "run")
    event = FakeGroupMessageEvent(
        group_id=516286670,
        sender=FakeSender(card="萌泪", nickname="MLJ"),
        time=1_800_000_000,
        user_id=605738729,
        text="今天聊了 AI 接入",
    )

    record_group_message_context(event, store)

    records = store.load_messages(516286670)
    assert len(records) == 1
    assert records[0].sender_name == "萌泪"
    assert records[0].text == "今天聊了 AI 接入"
    assert records[0].message_id == "233"


def test_record_group_message_context_persists_image_outline(tmp_path: Path) -> None:
    store = AiGroupContextStore(tmp_path / "run")
    event = FakeGroupMessageEvent(
        group_id=516286670,
        sender=FakeSender(card="萌泪", nickname="MLJ"),
        time=1_800_000_000,
        user_id=605738729,
        text="",
        segments=[FakeSegment("image", {"url": "https://example.invalid/a.png"})],
    )

    record_group_message_context(event, store)

    records = store.load_messages(516286670)
    assert len(records) == 1
    assert records[0].text == "[图片]"


def test_record_group_message_log_persists_incoming_message_for_admin_view(tmp_path: Path) -> None:
    store = GroupMessageLogStore(tmp_path / "run")
    event = FakeGroupMessageEvent(
        group_id=516286670,
        sender=FakeSender(card="", nickname="MLJ"),
        time=1_800_000_000,
        user_id=605738729,
        text="实时消息",
    )

    record_group_message_log(event, store)

    records = store.load_messages(516286670)
    assert len(records) == 1
    assert records[0].direction == "incoming"
    assert records[0].sender_name == "MLJ"
    assert records[0].text == "实时消息"
