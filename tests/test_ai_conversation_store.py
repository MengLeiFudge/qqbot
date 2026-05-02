from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.ai_conversation_store import AiConversationStore


def test_ai_conversation_store_keeps_bounded_private_history(tmp_path: Path) -> None:
    store = AiConversationStore(tmp_path, max_messages=4)
    key = store.private_key("605738729", "xiaomi")

    store.append_turn(key, "一", "1")
    store.append_turn(key, "二", "2")
    store.append_turn(key, "三", "3")

    reloaded = AiConversationStore(tmp_path, max_messages=4)
    messages = reloaded.load_messages(key)

    assert [(message.role, message.content) for message in messages] == [
        ("user", "二"),
        ("assistant", "2"),
        ("user", "三"),
        ("assistant", "3"),
    ]


def test_ai_conversation_store_builds_group_user_key(tmp_path: Path) -> None:
    store = AiConversationStore(tmp_path, max_messages=4)

    assert (
        store.group_user_key("10000", "605738729", "xiaomi")
        == "group_user:10000:605738729:xiaomi"
    )
