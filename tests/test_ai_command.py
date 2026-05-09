from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.ai_command import (
    build_ai_conversation_key,
    parse_ai_model_command,
    should_handle_ai_chat,
)
from qqbot.services.ai_conversation_store import AiConversationStore


class FakeEvent:
    def __init__(
        self,
        message_type: str,
        user_id: str,
        *,
        group_id: str | None = None,
        to_me: bool = False,
    ) -> None:
        self.message_type = message_type
        self.user_id = user_id
        if group_id is not None:
            self.group_id = group_id
        self._to_me = to_me

    def get_user_id(self) -> str:
        return self.user_id

    def is_tome(self) -> bool:
        return self._to_me


def test_private_plain_message_enters_ai_chat() -> None:
    assert should_handle_ai_chat(FakeEvent("private", "10001"), "你好") is True
    assert should_handle_ai_chat(FakeEvent("private", "10001"), "/status") is False
    assert should_handle_ai_chat(FakeEvent("private", "10001"), "菜单") is False
    assert should_handle_ai_chat(FakeEvent("private", "10001"), "") is False


def test_group_message_requires_direct_at_for_ai_chat() -> None:
    assert (
        should_handle_ai_chat(
            FakeEvent("group", "10001", group_id="20001", to_me=True),
            "你好",
        )
        is True
    )
    assert (
        should_handle_ai_chat(
            FakeEvent("group", "10001", group_id="20001", to_me=False),
            "你好",
        )
        is False
    )
    assert (
        should_handle_ai_chat(
            FakeEvent("group", "10001", group_id="20001", to_me=True),
            "菜单",
        )
        is False
    )


def test_group_draw_command_enters_ai_chat_without_direct_at() -> None:
    assert (
        should_handle_ai_chat(
            FakeEvent("group", "10001", group_id="20001", to_me=False),
            "棉花糖生图 卡拉比丘联动原神的宣传图",
        )
        is True
    )
    assert (
        should_handle_ai_chat(
            FakeEvent("group", "10001", group_id="20001", to_me=False),
            "生成卡拉比丘联动原神的宣传图",
        )
        is True
    )


def test_parse_ai_model_command_lists_or_switches_profile() -> None:
    status_command = parse_ai_model_command("AI模型")
    switch_command = parse_ai_model_command("切换AI xiaomi")

    assert status_command is not None
    assert status_command.action == "status"
    assert status_command.profile is None
    assert switch_command is not None
    assert switch_command.action == "switch"
    assert switch_command.profile == "xiaomi"
    assert parse_ai_model_command("ai xiaomi 你好") is None


def test_build_ai_conversation_key_uses_private_or_group_user_scope(tmp_path: Path) -> None:
    store = AiConversationStore(tmp_path)

    assert build_ai_conversation_key(store, FakeEvent("private", "605738729"), "xiaomi") == (
        "private:605738729:xiaomi"
    )
    assert build_ai_conversation_key(
        store,
        FakeEvent("group", "605738729", group_id="516286670", to_me=True),
        "xiaomi",
    ) == "group_user:516286670:605738729:xiaomi"
