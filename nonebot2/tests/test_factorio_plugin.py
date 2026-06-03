from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.plugins.factorio import FACTORIO_DOWNLOAD_PATTERN
from qqbot.services.command_guard import is_likely_command


def test_factorio_download_pattern_matches_equivalent_requests() -> None:
    assert re.match(FACTORIO_DOWNLOAD_PATTERN, "异星下载链接")
    assert re.match(FACTORIO_DOWNLOAD_PATTERN, "factorio下载链接")
    assert re.match(FACTORIO_DOWNLOAD_PATTERN, "太空时代安装包地址")
    assert re.match(FACTORIO_DOWNLOAD_PATTERN, "Space Age win安装包链接")


def test_factorio_download_pattern_rejects_unrelated_chat() -> None:
    assert re.match(FACTORIO_DOWNLOAD_PATTERN, "异星工厂怎么玩") is None
    assert re.match(FACTORIO_DOWNLOAD_PATTERN, "下载个别的游戏") is None


def test_factorio_download_command_is_likely_command() -> None:
    assert is_likely_command("异星下载链接") is True
    assert is_likely_command("factorio下载链接") is True
