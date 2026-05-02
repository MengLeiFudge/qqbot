from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.config import RuntimeSettings
from qqbot.services.status import build_status_lines


def test_build_status_lines_contains_runtime_summary() -> None:
    settings = RuntimeSettings.from_mapping(
        {
            "QQBOT_PORT": "18080",
            "QQBOT_ONEBOT_ACCESS_TOKEN": "token-value",
        }
    )

    lines = build_status_lines(settings)

    assert "QQBot Python skeleton is running." in lines
    assert "OneBot V11 Reverse WS: ws://127.0.0.1:18080/onebot/v11/ws" in lines
    assert "Access Token: configured" in lines


def test_build_status_lines_marks_migration_phase() -> None:
    settings = RuntimeSettings.from_mapping({})

    lines = build_status_lines(settings, phase="mirai migration pending")

    assert "Migration Phase: mirai migration pending" in lines
    assert "NapCat is expected to connect as the QQ gateway." in lines
