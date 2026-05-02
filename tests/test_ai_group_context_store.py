from pathlib import Path
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
        )

    records = store.load_messages(516286670)

    assert [(record.sender_name, record.text) for record in records] == [
        ("用户2", "消息2"),
        ("用户3", "消息3"),
        ("用户4", "消息4"),
    ]


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
