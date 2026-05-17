from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.bot_loop_guard import BotLoopGuard


def test_bot_loop_guard_blacklists_after_repeated_same_prompt() -> None:
    guard = BotLoopGuard(clock=lambda: 1000.0)

    assert guard.record_trigger("10001", "20001", "你好") == "allow"
    assert guard.record_trigger("10001", "20001", "你好") == "allow"
    assert guard.record_trigger("10001", "20001", "你好") == "warn"
    assert guard.record_trigger("10001", "20001", "你好") == "blocked"


def test_bot_loop_guard_blacklists_after_high_frequency() -> None:
    now = {"value": 1000.0}
    guard = BotLoopGuard(clock=lambda: now["value"])

    for index in range(4):
        assert guard.record_trigger("10001", "20001", f"第{index}条") == "allow"
        now["value"] += 1

    assert guard.record_trigger("10001", "20001", "第5条") == "warn"
    assert guard.record_trigger("10001", "20001", "第6条") == "blocked"


def test_bot_loop_guard_blacklists_after_fixed_format_replies() -> None:
    guard = BotLoopGuard(clock=lambda: 1000.0)

    assert guard.record_trigger("10001", "20001", "收到") == "allow"
    assert guard.record_trigger("10001", "20001", "好的") == "allow"
    assert guard.record_trigger("10001", "20001", "ok") == "allow"
    assert guard.record_trigger("10001", "20001", "在的") == "warn"


def test_bot_loop_guard_blacklist_expires() -> None:
    now = {"value": 1000.0}
    guard = BotLoopGuard(clock=lambda: now["value"], blacklist_seconds=10)

    guard.record_trigger("10001", "20001", "你好")
    guard.record_trigger("10001", "20001", "你好")
    assert guard.record_trigger("10001", "20001", "你好") == "warn"
    assert guard.record_trigger("10001", "20001", "你好") == "blocked"

    now["value"] = 1011.0
    assert guard.record_trigger("10001", "20001", "重新开始") == "allow"
