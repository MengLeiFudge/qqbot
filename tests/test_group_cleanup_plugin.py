from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nonebot.adapters.onebot.v11 import GroupDecreaseNoticeEvent

from qqbot.plugins.group_cleanup import should_cleanup_group_decrease


def test_group_cleanup_only_handles_bot_leaving_group() -> None:
    bot_left = GroupDecreaseNoticeEvent(
        time=1,
        self_id=10001,
        post_type="notice",
        notice_type="group_decrease",
        sub_type="kick_me",
        user_id=10001,
        group_id=20001,
        operator_id=30001,
    )
    other_member_left = GroupDecreaseNoticeEvent(
        time=1,
        self_id=10001,
        post_type="notice",
        notice_type="group_decrease",
        sub_type="leave",
        user_id=40001,
        group_id=20001,
        operator_id=40001,
    )

    assert should_cleanup_group_decrease(bot_left) is True
    assert should_cleanup_group_decrease(other_member_left) is False
