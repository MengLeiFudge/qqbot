from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.settings_store import SettingsStore
from qqbot.services.thunder_service import (
    clamp_thunder_percent,
    normalize_thunder_range,
    parse_thunder_command,
)


def test_thunder_defaults_match_old_project(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path, author_qq=605738729)

    assert store.get_thunder_config(516286670) == (0.05, 5, 20)


def test_parse_thunder_probability_command() -> None:
    command = parse_thunder_command("设置禁言概率2.5")

    assert command is not None
    assert command.action == "set_probability"
    assert command.probability == 0.025


def test_parse_thunder_time_command() -> None:
    command = parse_thunder_command("设置随机禁言时间20 5")

    assert command is not None
    assert command.action == "set_range"
    assert (command.min_seconds, command.max_seconds) == (5, 20)


def test_normalize_thunder_range_and_probability_are_clamped() -> None:
    assert clamp_thunder_percent(0) == 0.0001
    assert clamp_thunder_percent(80) == 0.5
    assert normalize_thunder_range(100, 0) == (1, 30)
