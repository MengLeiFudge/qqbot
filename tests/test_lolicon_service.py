from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.lolicon_service import (
    LoliconMode,
    parse_lolicon_command,
    parse_lolicon_response,
)
from qqbot.services.settings_store import SettingsStore


def test_lolicon_settings_default_to_closed(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path, author_qq=605738729)

    assert store.get_lolicon_config(516286670) == (False, False)


def test_parse_simple_lolicon_command() -> None:
    command = parse_lolicon_command("来点色图")

    assert command is not None
    assert command.mode == LoliconMode.R18
    assert command.num == 1
    assert command.tags == []


def test_parse_tagged_lolicon_command_with_count() -> None:
    command = parse_lolicon_command("美图 凯露 可可萝 10")

    assert command is not None
    assert command.mode == LoliconMode.NON_R18
    assert command.num == 10
    assert command.tags == ["凯露", "可可萝"]


def test_parse_lolicon_response_extracts_images() -> None:
    payload = {
        "error": "",
        "data": [
            {
                "title": "test-title",
                "pid": 123,
                "author": "author",
                "uid": 456,
                "r18": False,
                "urls": {"original": "https://example.com/a.jpg"},
            }
        ],
    }

    items = parse_lolicon_response(payload)

    assert len(items) == 1
    assert items[0].url == "https://example.com/a.jpg"
    assert items[0].title == "test-title"
