from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.ai_conversation_store import AiConversationStore


def test_ai_conversation_store_keeps_bounded_private_history(tmp_path: Path) -> None:
    store = AiConversationStore(tmp_path, max_messages=4)
    key = store.private_key("605738729", "xiaomi", "2026-05-17T04:00")

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


def test_ai_conversation_store_builds_group_key(tmp_path: Path) -> None:
    store = AiConversationStore(tmp_path, max_messages=4)

    assert (
        store.group_key("10000", "xiaomi", "2026-05-17T04:00")
        == "group:10000:xiaomi:2026-05-17T04:00"
    )
    assert (
        store.private_key("605738729", "xiaomi", "2026-05-17T04:00")
        == "private:605738729:xiaomi:2026-05-17T04:00"
    )


def test_ai_conversation_store_filters_high_risk_rejection_text(tmp_path: Path) -> None:
    store = AiConversationStore(tmp_path, max_messages=4)
    key = store.group_key("10000", "xiaomi", "2026-05-17T04:00")
    store.append_turn(
        key,
        "风险测试",
        "The request was rejected because it was considered high risk",
    )

    assert store.load_messages(key) == ()


def test_ai_conversation_store_sanitizes_action_descriptions(tmp_path: Path) -> None:
    store = AiConversationStore(tmp_path, max_messages=4)
    key = store.group_key("10000", "xiaomi", "2026-05-17T04:00")

    store.append_turn(
        key,
        "你怎么也是绿绿的",
        "喵呜~被你发现了！(尾巴心虚地甩了甩) 🐱",
    )

    messages = store.load_messages(key)

    assert messages[-1].content == "喵呜~被你发现了！🐱"
