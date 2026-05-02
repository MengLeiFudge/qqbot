from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.command_guard import is_likely_command
from qqbot.services.command_guard import is_direct_command_event


class FakeSegment:
    def __init__(self, segment_type: str, data: dict[str, str]) -> None:
        self.type = segment_type
        self.data = data


class FakeEvent:
    def __init__(
        self,
        message_type: str,
        to_me: bool = False,
        *,
        self_id: str = "114514",
        message=None,
    ) -> None:
        self.message_type = message_type
        self.to_me = to_me
        self.self_id = self_id
        self.message = message

    def is_tome(self) -> bool:
        return self.to_me

    def get_message(self):
        return self.message or []


def test_arc_short_commands_are_guarded() -> None:
    for text in (
        "arctj10.5",
        "arctj 10.5",
        "arczm",
        "arczm5",
        "arczm 5",
        "zm",
        "zm5",
        "zm 5",
        "开 β",
        "开*",
        "10骨折光",
        "10 骨折光",
        "猜10骨折光",
        "猜 10 骨折光",
        "arcqh",
        "arcqh bt",
        "arcqh 补图",
        "arcjx",
        "jx",
        "archd",
        "arctz",
        "xz",
        "arcxz",
    ):
        assert is_likely_command(text) is True


def test_ai_model_management_commands_are_guarded() -> None:
    assert is_likely_command("AI模型") is True
    assert is_likely_command("切换AI xiaomi") is True
    assert is_likely_command("ai xiaomi 你好") is False


def test_unknown_slash_text_can_fall_through_to_ai_when_directly_addressed() -> None:
    assert is_likely_command("/chart CrRgSbWy") is False


def test_group_commands_must_be_addressed_to_bot() -> None:
    assert is_direct_command_event(FakeEvent("group", to_me=False)) is False
    assert is_direct_command_event(FakeEvent("group", to_me=True)) is True
    assert is_direct_command_event(FakeEvent("private", to_me=False)) is True


def test_group_direct_at_allows_leading_blank_text_segment() -> None:
    event = FakeEvent(
        "group",
        to_me=False,
        self_id="1443944862",
        message=[
            FakeSegment("text", {"text": " "}),
            FakeSegment("at", {"qq": "1443944862"}),
            FakeSegment("text", {"text": " 本群启用了哪些插件"}),
        ],
    )

    assert is_direct_command_event(event) is True


def test_group_direct_at_rejects_nonblank_text_before_at() -> None:
    event = FakeEvent(
        "group",
        to_me=False,
        self_id="1443944862",
        message=[
            FakeSegment("text", {"text": "普通聊天 "}),
            FakeSegment("at", {"qq": "1443944862"}),
        ],
    )

    assert is_direct_command_event(event) is False
