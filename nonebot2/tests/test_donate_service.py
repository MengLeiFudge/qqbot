from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.donate_service import build_donate_caption, locate_donate_image


def test_build_donate_caption_uses_author_name() -> None:
    caption = build_donate_caption(123456, "萌泪")

    assert "您的每一份捐赠都是对萌泪最大的支持！" in caption


def test_locate_donate_image_finds_existing_file(tmp_path: Path) -> None:
    donate_file = tmp_path / "data" / "zfb.jpg"
    donate_file.parent.mkdir(parents=True, exist_ok=True)
    donate_file.write_bytes(b"fake")

    assert locate_donate_image(tmp_path) == donate_file


def test_locate_donate_image_returns_none_when_missing(tmp_path: Path) -> None:
    assert locate_donate_image(tmp_path) is None
