from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.chat_memory_store import ChatMemoryStore
from qqbot.services.group_nick_store import GroupNickStore
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


def test_nickname_usage_finds_identity_candidate_by_recent_sender_name(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "run"
    nick_store = GroupNickStore(run_root / "settings" / "group_nick.json")
    nick_store.record_group_sender(
        group_id=1163635014,
        qq=273548027,
        card="焰靛燦「YanDarkCollapser」",
        nickname="YanDarkCollapser",
        updated_at=1,
    )
    nick_store.record_group_sender(
        group_id=10001,
        qq=99999,
        card="YDC",
        nickname="其他群成员",
        updated_at=1,
    )
    memory_store = ChatMemoryStore(run_root)
    for index, sender_name in enumerate(["YDC", "YDC", "焰靛燦「YanDarkCollapser」"], start=1):
        memory_store.append_message(
            group_id=1163635014,
            message_id=f"ydc-{index}",
            direction="incoming",
            user_id=273548027,
            sender_name=sender_name,
            text=f"历史消息 {index}",
            timestamp=index,
        )
    memory_store.append_message(
        group_id=10001,
        message_id="other-group",
        direction="incoming",
        user_id=99999,
        sender_name="YDC",
        text="其他群消息",
        timestamp=10,
    )

    candidates = NicknameUsageService(memory_store).find_identity_candidates(
        group_id=1163635014,
        query_name="YDC",
        nick_store=nick_store,
    )

    assert len(candidates) == 1
    assert candidates[0].user_id == "273548027"
    assert candidates[0].call_name == "焰靛燦「YanDarkCollapser」"
    assert candidates[0].matched_names == ("YDC",)
    assert candidates[0].summary.sample_size == 3
