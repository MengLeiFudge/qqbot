from pathlib import Path
import asyncio
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import qqbot.services.onebot_message_throttle as throttle_module
from qqbot.services.chat_memory_store import ChatMemoryStore
from qqbot.services.group_message_log_store import GroupMessageLogStore
from qqbot.services.onebot_message_throttle import (
    extract_group_message_group_id,
    record_bot_group_message,
)


def test_extract_group_message_group_id_only_matches_group_messages() -> None:
    assert extract_group_message_group_id("send_group_msg", {"group_id": 10001}) == 10001
    assert (
        extract_group_message_group_id(
            "send_msg",
            {"message_type": "group", "group_id": "10002"},
        )
        == "10002"
    )
    assert extract_group_message_group_id("send_private_msg", {"user_id": 10001}) is None
    assert extract_group_message_group_id("group_poke", {"group_id": 10001}) is None


def test_record_bot_group_message_persists_successful_group_send(tmp_path: Path) -> None:
    store = GroupMessageLogStore(tmp_path / "run")
    fixed_time = 1_800_000_000.1

    record_bot_group_message(
        store=store,
        group_id=10001,
        self_id=30001,
        message="Bot 回复",
        timestamp=fixed_time,
        result={"message_id": 7788},
    )

    records = store.load_messages(10001)
    assert len(records) == 1
    assert records[0].direction == "bot"
    assert records[0].user_id == "30001"
    assert records[0].sender_name == "Bot"
    assert records[0].text == "Bot 回复"
    assert records[0].timestamp == int(fixed_time)
    assert records[0].message_id == "7788"


def test_record_bot_group_message_persists_chat_memory(tmp_path: Path) -> None:
    log_store = GroupMessageLogStore(tmp_path / "run")
    memory_store = ChatMemoryStore(tmp_path / "run")

    record_bot_group_message(
        store=log_store,
        memory_store=memory_store,
        group_id=10001,
        self_id=30001,
        message="Bot 回复 shapez 数据库",
        timestamp=1_800_000_000.1,
        result={"message_id": 7788},
    )

    records = memory_store.search_messages(10001, "shapez 数据库", limit=5)
    assert len(records) == 1
    assert records[0].direction == "bot"
    assert records[0].user_id == "30001"
    assert records[0].sender_name == "Bot"
    assert records[0].message_id == "7788"
    assert records[0].text == "Bot 回复 shapez 数据库"


def test_installed_throttle_records_bot_message_only_after_send_success(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    async def fake_call_api(self: object, api: str, **data: object) -> dict[str, object]:
        calls.append((api, data))
        return {"message_id": 8899}

    monkeypatch.setattr(throttle_module, "_INSTALLED", False)
    monkeypatch.setattr(throttle_module.OneBotV11Bot, "call_api", fake_call_api)
    monkeypatch.setattr(throttle_module, "has_waited_group_message_interval", lambda: True)
    monkeypatch.setattr(throttle_module, "get_group_message_log_store", lambda: GroupMessageLogStore(tmp_path / "run"))
    monkeypatch.setattr(time, "time", lambda: 1_800_000_001.9)

    throttle_module.install_onebot_group_message_throttle()

    class FakeBot:
        self_id = "30001"

    result = asyncio.run(
        throttle_module.OneBotV11Bot.call_api(
            FakeBot(),
            "send_group_msg",
            group_id=10001,
            message="右侧消息",
        )
    )

    assert result == {"message_id": 8899}
    assert calls == [("send_group_msg", {"group_id": 10001, "message": "右侧消息"})]
    records = GroupMessageLogStore(tmp_path / "run").load_messages(10001)
    assert len(records) == 1
    assert records[0].direction == "bot"
    assert records[0].text == "右侧消息"


def test_installed_throttle_does_not_record_failed_group_send(
    tmp_path: Path,
    monkeypatch,
) -> None:
    async def fake_call_api(self: object, api: str, **data: object) -> dict[str, object]:
        raise RuntimeError("send failed")

    monkeypatch.setattr(throttle_module, "_INSTALLED", False)
    monkeypatch.setattr(throttle_module.OneBotV11Bot, "call_api", fake_call_api)
    monkeypatch.setattr(throttle_module, "has_waited_group_message_interval", lambda: True)
    monkeypatch.setattr(throttle_module, "get_group_message_log_store", lambda: GroupMessageLogStore(tmp_path / "run"))

    throttle_module.install_onebot_group_message_throttle()

    class FakeBot:
        self_id = "30001"

    try:
        asyncio.run(
            throttle_module.OneBotV11Bot.call_api(
                FakeBot(),
                "send_group_msg",
                group_id=10001,
                message="不会记录",
            )
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("send failure should bubble up")

    assert GroupMessageLogStore(tmp_path / "run").load_messages(10001) == ()


def test_installed_throttle_keeps_send_success_when_log_store_fails(
    monkeypatch,
) -> None:
    async def fake_call_api(self: object, api: str, **data: object) -> dict[str, object]:
        return {"message_id": 8899}

    def broken_store() -> GroupMessageLogStore:
        raise RuntimeError("log store failed")

    monkeypatch.setattr(throttle_module, "_INSTALLED", False)
    monkeypatch.setattr(throttle_module.OneBotV11Bot, "call_api", fake_call_api)
    monkeypatch.setattr(throttle_module, "has_waited_group_message_interval", lambda: True)
    monkeypatch.setattr(throttle_module, "get_group_message_log_store", broken_store)

    throttle_module.install_onebot_group_message_throttle()

    class FakeBot:
        self_id = "30001"

    result = asyncio.run(
        throttle_module.OneBotV11Bot.call_api(
            FakeBot(),
            "send_group_msg",
            group_id=10001,
            message="仍然发送成功",
        )
    )

    assert result == {"message_id": 8899}
