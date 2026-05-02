from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.shapez_service import ShapeCode, render_shape_image


def test_shape_code_parses_layers() -> None:
    shape = ShapeCode("CrRgSbWy")

    assert shape.layer_count == 1
    assert shape.short_key == "CrRgSbWy"


def test_shape_image_renders_png(tmp_path: Path) -> None:
    shape = ShapeCode("CrRgSbWy")
    output = tmp_path / "shape.png"

    render_shape_image(shape, output)

    assert output.exists()
    assert output.stat().st_size > 0
