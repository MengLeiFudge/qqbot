from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nonebot.adapters.onebot.v11 import Message, MessageSegment

from qqbot.services.reread_service import (
    RereadRepeatState,
    clamp_reread_percent,
    format_reread_chance,
    normalize_reread_key,
    render_reread_message,
    should_skip_reread_message,
)
from qqbot.services.settings_store import SettingsStore


def test_reread_chance_defaults_to_five_percent(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path, author_qq=605738729)

    assert store.get_reread_chance(516286670) == 0.05


def test_set_reread_percent_is_global_and_clamped(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path, author_qq=605738729)

    store.set_reread_chance(516286670, clamp_reread_percent(0))
    assert store.get_reread_chance(516286670) == 0.0001
    assert store.get_reread_chance(319567534) == 0.0001

    store.set_reread_chance(516286670, clamp_reread_percent(80))
    assert store.get_reread_chance(516286670) == 0.5
    assert store.get_reread_chance(319567534) == 0.5


def test_reread_repeat_state_repeats_second_duplicate_once() -> None:
    state = RereadRepeatState()

    assert state.should_repeat(10001, "你好") is False
    assert state.should_repeat(10001, "你好") is True
    assert state.should_repeat(10001, "你好") is False

    assert state.should_repeat(10001, "换一句") is False
    assert state.should_repeat(10001, "换一句") is True


def test_reread_repeat_state_is_group_scoped_and_normalizes_spaces() -> None:
    state = RereadRepeatState()

    assert state.should_repeat(10001, "你好   世界") is False
    assert state.should_repeat(10002, "你好 世界") is False
    assert state.should_repeat(10001, "你好 世界") is True
    assert state.should_repeat(10002, "你好 世界") is True
    assert normalize_reread_key("  你好\n世界  ") == "你好 世界"


def test_render_reread_message_keeps_plain_text() -> None:
    message = Message("你好世界")

    rendered = render_reread_message(message)

    assert str(rendered) == "你好世界"


def test_skip_reread_message_when_image_or_at_is_present() -> None:
    assert should_skip_reread_message(Message([MessageSegment.image("file:///tmp/a.png")])) is True
    assert should_skip_reread_message(Message([MessageSegment.at(10001), MessageSegment.text("你好")])) is True
    assert should_skip_reread_message(Message([MessageSegment.text("你好")])) is False


def test_render_reread_message_keeps_mixed_message() -> None:
    message = Message([
        MessageSegment.text("你好"),
        MessageSegment.face(123),
    ])

    rendered = render_reread_message(message)

    assert rendered == message


def test_format_reread_chance_matches_old_style() -> None:
    assert format_reread_chance(0.025) == "2.500%"
