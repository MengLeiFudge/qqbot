from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.group_control_service import parse_group_control_command


def test_parse_ban_seconds_command() -> None:
    command = parse_group_control_command("禁30@123", [123])

    assert command is not None
    assert command.action == "ban_member"
    assert command.target_id == 123
    assert command.duration_seconds == 30


def test_parse_ban_minutes_command() -> None:
    command = parse_group_control_command("禁言2m@123", [123])

    assert command is not None
    assert command.action == "ban_member"
    assert command.duration_seconds == 120


def test_parse_group_wide_ban_command() -> None:
    command = parse_group_control_command("群禁言", [])

    assert command is not None
    assert command.action == "ban_group"


def test_parse_unban_and_kick_commands() -> None:
    unban = parse_group_control_command("解禁@123", [123])
    kick = parse_group_control_command("踢出@123", [123])

    assert unban is not None
    assert unban.action == "unban_member"
    assert kick is not None
    assert kick.action == "kick_member"
