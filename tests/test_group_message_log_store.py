from pathlib import Path

from qqbot.services.group_message_log_store import GroupMessageLogStore


def test_group_message_log_store_keeps_recent_messages_by_group(tmp_path: Path) -> None:
    store = GroupMessageLogStore(tmp_path / "run", max_messages=2)

    store.append_message(
        group_id=10001,
        direction="incoming",
        user_id=20001,
        sender_name="甲",
        text="第一条",
        timestamp=1,
        message_id=11,
    )
    store.append_message(
        group_id=10001,
        direction="bot",
        user_id=30001,
        sender_name="Bot",
        text="第二条",
        timestamp=2,
        message_id=12,
    )
    store.append_message(
        group_id=10001,
        direction="incoming",
        user_id=20002,
        sender_name="乙",
        text="第三条",
        timestamp=3,
    )

    records = store.load_messages(10001)

    assert [record.text for record in records] == ["第二条", "第三条"]
    assert records[0].direction == "bot"
    assert records[1].direction == "incoming"
    assert records[0].message_id == "12"


def test_group_message_log_store_lists_groups_with_display_names(tmp_path: Path) -> None:
    store = GroupMessageLogStore(tmp_path / "run")
    store.append_message(
        group_id=10001,
        direction="incoming",
        user_id=20001,
        sender_name="甲",
        text="你好",
        timestamp=1,
    )
    store.append_message(
        group_id=10002,
        direction="bot",
        user_id=30001,
        sender_name="Bot",
        text="收到",
        timestamp=2,
    )

    payload = store.list_group_messages({10001: "测试群"})

    assert payload == {
        "groups": [
            {
                "group_id": 10001,
                "group_name": "测试群",
                "display_name": "测试群（10001）",
                "messages": [
                    {
                        "direction": "incoming",
                        "user_id": "20001",
                        "sender_name": "甲",
                        "text": "你好",
                        "timestamp": 1,
                        "message_id": "",
                    }
                ],
            },
            {
                "group_id": 10002,
                "group_name": "",
                "display_name": "10002",
                "messages": [
                    {
                        "direction": "bot",
                        "user_id": "30001",
                        "sender_name": "Bot",
                        "text": "收到",
                        "timestamp": 2,
                        "message_id": "",
                    }
                ],
            },
        ],
    }


def test_group_message_log_store_skips_blank_text_and_bad_direction(tmp_path: Path) -> None:
    store = GroupMessageLogStore(tmp_path / "run")

    store.append_message(
        group_id=10001,
        direction="incoming",
        user_id=20001,
        sender_name="甲",
        text="   ",
        timestamp=1,
    )

    assert store.load_messages(10001) == ()


def test_group_message_log_store_removes_group_file(tmp_path: Path) -> None:
    store = GroupMessageLogStore(tmp_path / "run")
    store.append_message(
        group_id=10001,
        direction="incoming",
        user_id=20001,
        sender_name="甲",
        text="你好",
        timestamp=1,
    )

    assert store.remove_group(10001) is True
    assert store.load_messages(10001) == ()
    assert store.remove_group(10001) is False
