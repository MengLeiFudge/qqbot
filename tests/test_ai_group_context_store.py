from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.ai_group_context_store import AiGroupContextStore


def test_ai_group_context_store_keeps_recent_group_messages(tmp_path: Path) -> None:
    store = AiGroupContextStore(tmp_path, max_messages=3)

    for index in range(5):
        store.append_message(
            group_id=516286670,
            user_id=10000 + index,
            sender_name=f"用户{index}",
            text=f"消息{index}",
            timestamp=index,
            message_id=100 + index,
        )

    records = store.load_messages(516286670)

    assert [(record.sender_name, record.text) for record in records] == [
        ("用户2", "消息2"),
        ("用户3", "消息3"),
        ("用户4", "消息4"),
    ]
    assert [record.message_id for record in records] == ["102", "103", "104"]


def test_ai_group_context_store_skips_empty_text(tmp_path: Path) -> None:
    store = AiGroupContextStore(tmp_path)

    store.append_message(
        group_id=516286670,
        user_id=10001,
        sender_name="萌泪",
        text="   ",
        timestamp=1,
    )

    assert store.load_messages(516286670) == ()


def test_ai_group_context_store_filters_high_risk_rejection_text(tmp_path: Path) -> None:
    store = AiGroupContextStore(tmp_path)

    store.append_message(
        group_id=516286670,
        user_id=10001,
        sender_name="Bot",
        text="The request was rejected because it was considered high risk",
        timestamp=1,
    )

    assert store.load_messages(516286670) == ()


def test_ai_group_context_store_loads_legacy_records_without_message_id(tmp_path: Path) -> None:
    path = tmp_path / "ai" / "group_context" / "516286670.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            [
                {
                    "user_id": "10001",
                    "sender_name": "萌泪",
                    "text": "旧消息",
                    "timestamp": 1,
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    records = AiGroupContextStore(tmp_path).load_messages(516286670)

    assert len(records) == 1
    assert records[0].message_id == ""


def test_ai_group_context_store_removes_group_file(tmp_path: Path) -> None:
    store = AiGroupContextStore(tmp_path)
    store.append_message(
        group_id=516286670,
        user_id=10001,
        sender_name="萌泪",
        text="旧消息",
        timestamp=1,
    )

    assert store.remove_group(516286670) is True
    assert store.load_messages(516286670) == ()
    assert store.remove_group(516286670) is False
