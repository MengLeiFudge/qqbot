from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.plugins.private_memory_cache import handle_private_memory_cache_event, record_private_chat_memory
from qqbot.plugins import private_memory_cache
from qqbot.config import RuntimeSettings
from qqbot.services.ai_gateway import AiMetrics, AiResponse
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


def test_handle_private_memory_cache_event_runs_blocking_write_in_thread(monkeypatch) -> None:
    event = FakePrivateMessageEvent(
        user_id=605738729,
        time=1_800_000_000,
        text="私聊记录",
    )
    calls: list[object] = []

    async def fake_to_thread(func, *args, **kwargs):
        calls.append((func, args, kwargs))
        return "ok"

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

    asyncio.run(handle_private_memory_cache_event(event))

    assert len(calls) == 1


def test_old_private_messages_schedule_one_ai_replay_per_user(monkeypatch) -> None:
    private_memory_cache.reset_offline_private_ai_replay_state()
    events = [
        FakePrivateMessageEvent(user_id=605738729, time=10, message_id=1, text="第一条旧私聊"),
        FakePrivateMessageEvent(user_id=605738729, time=11, message_id=2, text="第二条旧私聊"),
    ]
    scheduled: list[tuple[object, float]] = []

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    def fake_is_before_onebot_connect(event_time):
        return event_time < 100

    def fake_schedule(bot, user_id, delay_seconds=None):
        scheduled.append((user_id, delay_seconds))

    monkeypatch.setattr(private_memory_cache.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(private_memory_cache, "is_before_onebot_connect", fake_is_before_onebot_connect)
    monkeypatch.setattr(private_memory_cache, "schedule_offline_private_ai_replay", fake_schedule)

    asyncio.run(handle_private_memory_cache_event(events[0], bot=object()))
    asyncio.run(handle_private_memory_cache_event(events[1], bot=object()))

    assert scheduled == [("605738729", None), ("605738729", None)]
    assert private_memory_cache.OFFLINE_PRIVATE_PENDING_USERS == {"605738729"}


def test_online_private_messages_do_not_schedule_offline_replay(monkeypatch) -> None:
    private_memory_cache.reset_offline_private_ai_replay_state()
    event = FakePrivateMessageEvent(user_id=605738729, time=101, text="在线私聊")
    scheduled: list[object] = []

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(private_memory_cache.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(private_memory_cache, "is_before_onebot_connect", lambda event_time: False)
    monkeypatch.setattr(
        private_memory_cache,
        "schedule_offline_private_ai_replay",
        lambda *args, **kwargs: scheduled.append((args, kwargs)),
    )

    asyncio.run(handle_private_memory_cache_event(event, bot=object()))

    assert scheduled == []


def test_old_private_messages_skip_replay_after_user_was_replayed(monkeypatch) -> None:
    private_memory_cache.reset_offline_private_ai_replay_state()
    event = FakePrivateMessageEvent(user_id=605738729, time=10, message_id=1, text="后到的旧私聊")
    scheduled: list[object] = []

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    private_memory_cache._OFFLINE_PRIVATE_REPLAYED_USERS.add("605738729")
    monkeypatch.setattr(private_memory_cache.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(private_memory_cache, "is_before_onebot_connect", lambda event_time: True)
    monkeypatch.setattr(
        private_memory_cache,
        "schedule_offline_private_ai_replay",
        lambda *args, **kwargs: scheduled.append((args, kwargs)),
    )

    asyncio.run(handle_private_memory_cache_event(event, bot=object()))

    assert scheduled == []
    assert private_memory_cache.OFFLINE_PRIVATE_PENDING_USERS == set()
    assert private_memory_cache._OFFLINE_PRIVATE_PENDING_MESSAGE_IDS == {}


def test_reset_offline_private_ai_replay_state_clears_connection_state() -> None:
    private_memory_cache.reset_offline_private_ai_replay_state()
    private_memory_cache.OFFLINE_PRIVATE_PENDING_USERS.add("605738729")
    private_memory_cache._OFFLINE_PRIVATE_REPLAYED_USERS.add("605738729")
    private_memory_cache._OFFLINE_PRIVATE_PENDING_MESSAGE_IDS["605738729"] = ["1"]

    private_memory_cache.reset_offline_private_ai_replay_state()

    assert private_memory_cache.OFFLINE_PRIVATE_PENDING_USERS == set()
    assert private_memory_cache._OFFLINE_PRIVATE_REPLAYED_USERS == set()
    assert private_memory_cache._OFFLINE_PRIVATE_PENDING_MESSAGE_IDS == {}


def test_offline_private_replay_uses_only_pending_message_ids(tmp_path: Path, monkeypatch) -> None:
    private_memory_cache.reset_offline_private_ai_replay_state()
    store = ChatMemoryStore(tmp_path)
    store.append_message(
        group_id="private:605738729",
        space_id="qq:private:605738729",
        message_id=1,
        direction="incoming",
        user_id=605738729,
        actor_id="qq:user:605738729",
        sender_name="605738729",
        text="更早的历史",
        timestamp=1,
        visibility="private",
    )
    store.append_message(
        group_id="private:605738729",
        space_id="qq:private:605738729",
        message_id=2,
        direction="incoming",
        user_id=605738729,
        actor_id="qq:user:605738729",
        sender_name="605738729",
        text="本批第一条",
        timestamp=2,
        visibility="private",
    )
    store.append_message(
        group_id="private:605738729",
        space_id="qq:private:605738729",
        message_id=3,
        direction="incoming",
        user_id=605738729,
        actor_id="qq:user:605738729",
        sender_name="605738729",
        text="本批第二条",
        timestamp=3,
        visibility="private",
    )
    store.append_message(
        group_id="private:605738729",
        space_id="qq:private:605738729",
        message_id=4,
        direction="incoming",
        user_id=605738729,
        actor_id="qq:user:605738729",
        sender_name="605738729",
        text="上线后的新消息",
        timestamp=4,
        visibility="private",
    )
    prompts: list[str] = []

    class FakeGateway:
        async def complete(self, request):
            prompts.append(request.prompt)
            return AiResponse(
                "合并回复",
                metrics=AiMetrics(
                    first_token_seconds=None,
                    total_seconds=0.1,
                    completion_tokens=1,
                    output_chars=4,
                ),
            )

    class FakeBot:
        self_id = "1443944862"

        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        async def call_api(self, api: str, **data):
            self.calls.append((api, data))

    private_memory_cache._OFFLINE_PRIVATE_PENDING_MESSAGE_IDS["605738729"] = ["2", "3"]
    monkeypatch.setattr(
        private_memory_cache,
        "load_settings",
        lambda: RuntimeSettings(data_root=tmp_path, ai_enabled=True, ai_default_profile="default"),
    )
    monkeypatch.setattr(private_memory_cache, "load_ai_profiles", lambda path: {})
    monkeypatch.setattr(private_memory_cache, "get_current_ai_profile_name", lambda settings, store, profiles: "default")
    monkeypatch.setattr(private_memory_cache, "build_ai_gateway", lambda settings, profile: FakeGateway())

    bot = FakeBot()
    asyncio.run(private_memory_cache.replay_offline_private_ai_once(bot, "605738729"))

    assert len(prompts) == 1
    assert "本批第一条" in prompts[0]
    assert "本批第二条" in prompts[0]
    assert "更早的历史" not in prompts[0]
    assert "上线后的新消息" not in prompts[0]
    assert bot.calls == [("send_private_msg", {"user_id": 605738729, "message": "合并回复"})]
