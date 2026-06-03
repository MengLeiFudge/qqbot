from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.social_service import (
    build_group_member_welcome_message,
    plan_poke_response,
    should_auto_approve_request,
)


def test_should_auto_approve_only_friend_and_group_invite() -> None:
    assert should_auto_approve_request("friend", None) is True
    assert should_auto_approve_request("group", "invite") is True
    assert should_auto_approve_request("group", "add") is False


def test_build_group_member_welcome_message_mentions_new_member() -> None:
    assert build_group_member_welcome_message(10001, "+=-1") == "[CQ:at,qq=10001] 欢迎大佬喵！群地位+=-1"


def test_plan_poke_response_when_someone_pokes_bot() -> None:
    plan = plan_poke_response(self_id=114514, user_id=10001, target_id=114514, roll=4)

    assert [(step.delay_ms, step.message, step.poke_target) for step in plan.steps] == [
        (0, "谁让你戳我的？我戳！", None),
        (1000, "我再戳！", 10001),
    ]


def test_plan_poke_response_when_roll_hits_third_stage() -> None:
    plan = plan_poke_response(self_id=114514, user_id=10001, target_id=114514, roll=1)

    assert [(step.delay_ms, step.message, step.poke_target) for step in plan.steps] == [
        (0, "谁让你戳我的？我戳！", None),
        (1000, "我再戳！", 10001),
        (1000, "我还戳！", 10001),
    ]


def test_plan_poke_response_when_someone_pokes_others() -> None:
    plan = plan_poke_response(self_id=114514, user_id=10001, target_id=10002, roll=20)

    assert [(step.delay_ms, step.message, step.poke_target) for step in plan.steps] == [
        (0, None, 10002),
    ]


def test_plan_poke_response_can_ignore_high_roll() -> None:
    plan = plan_poke_response(self_id=114514, user_id=10001, target_id=114514, roll=60)

    assert plan.steps == []
