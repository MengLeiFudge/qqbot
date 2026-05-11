from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.chat_memory_store import ChatMemoryStore
from qqbot.services.nickname_usage_service import NicknameUsageService


def test_nickname_usage_summary_counts_recent_sender_names(tmp_path: Path) -> None:
    memory_store = ChatMemoryStore(tmp_path)
    for index, sender_name in enumerate(
        [
            "୧⍤⃝୨鱼子勺：[聊天记录]",
            "୧⍤⃝୨鱼子勺：[聊天记录]",
            "୧⍤⃝୨勺子鱼",
            "其他人",
        ],
        start=1,
    ):
        memory_store.append_message(
            group_id=1163635014,
            message_id=f"m{index}",
            direction="incoming",
            user_id=1728704949 if sender_name != "其他人" else 3120618805,
            sender_name=sender_name,
            text=f"消息 {index}",
            timestamp=index,
        )

    summary = NicknameUsageService(memory_store).summarize(
        group_id=1163635014,
        user_id=1728704949,
        limit=100,
    )

    assert summary.sample_size == 3
    assert [(entry.name, entry.count, entry.ratio) for entry in summary.entries] == [
        ("鱼子勺", 2, 2 / 3),
        ("勺子鱼", 1, 1 / 3),
    ]


def test_nickname_usage_summary_respects_recent_limit(tmp_path: Path) -> None:
    memory_store = ChatMemoryStore(tmp_path)
    memory_store.append_message(
        group_id=1163635014,
        message_id="old",
        direction="incoming",
        user_id=1728704949,
        sender_name="旧称呼",
        text="旧消息",
        timestamp=1,
    )
    memory_store.append_message(
        group_id=1163635014,
        message_id="new",
        direction="incoming",
        user_id=1728704949,
        sender_name="新称呼",
        text="新消息",
        timestamp=2,
    )

    summary = NicknameUsageService(memory_store).summarize(
        group_id=1163635014,
        user_id=1728704949,
        limit=1,
    )

    assert summary.sample_size == 1
    assert [(entry.name, entry.count) for entry in summary.entries] == [("新称呼", 1)]
