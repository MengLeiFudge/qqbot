from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.ai_group_context_store import AiGroupContextStore
from qqbot.services.chat_memory_store import ChatMemoryStore
from qqbot.services.group_cleanup_service import GroupCleanupService
from qqbot.services.group_message_log_store import GroupMessageLogStore
from qqbot.services.group_nick_store import GroupNickStore
from qqbot.services.settings_store import SettingsStore


def test_group_cleanup_service_removes_group_scoped_runtime_state(tmp_path: Path) -> None:
    data_root = tmp_path / "run"
    settings_store = SettingsStore(data_root, author_qq=605738729)
    settings_store.set_lolicon_config(10001, True, False)
    func_state = data_root / "settings" / "func_state" / "10001.json"
    func_state.parent.mkdir(parents=True)
    func_state.write_text('{"Arc": true}', encoding="utf-8")
    GroupNickStore(data_root / "settings" / "group_nick.json").record_group_sender(
        group_id=10001,
        qq=605738729,
        card="旧群名片",
        nickname="",
        updated_at=1,
    )
    AiGroupContextStore(data_root).append_message(
        group_id=10001,
        user_id=605738729,
        sender_name="萌泪",
        text="旧上下文",
        timestamp=1,
    )
    GroupMessageLogStore(data_root).append_message(
        group_id=10001,
        direction="incoming",
        user_id=605738729,
        sender_name="萌泪",
        text="旧消息",
        timestamp=1,
    )
    ChatMemoryStore(data_root).append_message(
        group_id=10001,
        message_id=3,
        direction="incoming",
        user_id=605738729,
        sender_name="萌泪",
        text="需要删除的长期记忆",
        timestamp=1,
    )

    result = GroupCleanupService(data_root, author_qq=605738729).cleanup_group(10001)

    assert result.group_id == 10001
    assert not func_state.exists()
    assert settings_store.get_lolicon_config(10001) == (False, False)
    assert GroupNickStore(data_root / "settings" / "group_nick.json").records == {}
    assert AiGroupContextStore(data_root).load_messages(10001) == ()
    assert GroupMessageLogStore(data_root).load_messages(10001) == ()
    assert ChatMemoryStore(data_root).search_messages(10001, "长期记忆") == ()
    assert "ai/chat_memory.sqlite3:10001" in result.removed_items


def test_group_cleanup_service_removes_group_nick_store_records(tmp_path: Path) -> None:
    data_root = tmp_path / "run"
    GroupNickStore(data_root / "settings" / "group_nick.json").record_group_sender(
        group_id=10001,
        qq=605738729,
        card="旧群名片",
        nickname="",
        updated_at=1,
    )

    result = GroupCleanupService(data_root, author_qq=605738729).cleanup_group(10001)

    assert "settings/group_nick.json" in result.removed_items
    assert GroupNickStore(data_root / "settings" / "group_nick.json").records == {}
