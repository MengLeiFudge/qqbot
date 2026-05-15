from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.offline_message_gate import (
    clear_onebot_connect_watermark,
    is_before_onebot_connect,
    mark_onebot_connected,
)


def test_connect_watermark_detects_old_events() -> None:
    clear_onebot_connect_watermark()
    mark_onebot_connected(1_800_000_000.5)

    assert is_before_onebot_connect(1_800_000_000) is True
    assert is_before_onebot_connect(1_800_000_000.5) is False


def test_missing_event_time_is_not_treated_as_old() -> None:
    clear_onebot_connect_watermark()
    mark_onebot_connected(1_800_000_000)

    assert is_before_onebot_connect(None) is False
    assert is_before_onebot_connect("bad") is False


def test_missing_connect_watermark_does_not_block_events() -> None:
    clear_onebot_connect_watermark()

    assert is_before_onebot_connect(1) is False
