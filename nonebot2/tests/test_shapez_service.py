from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.shapez_service import (
    SHAPE_PATTERN,
    ShapeCode,
    render_shape_chart,
    render_shape_code,
    render_shape_image,
)


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


def test_shape_code_supports_legacy_extended_tokens(tmp_path: Path) -> None:
    shape, output = render_shape_code(tmp_path, "--P-cwcw:RuRucwcw:--P-cwcw:Cucrcwcw:crP-cwcw")

    assert shape.layer_count == 5
    assert output.exists()
    assert output.stat().st_size > 0


def test_shape_chart_renders_png_and_text(tmp_path: Path) -> None:
    shape, output, shape_text = render_shape_chart(tmp_path, "RuRuRuRu:crcrcrcr")

    assert shape.short_key == "RuRuRuRu:crcrcrcr"
    assert "晶晶晶晶" in shape_text
    assert output.exists()
    assert output.stat().st_size > 0


def test_shape_pattern_finds_extended_legacy_code() -> None:
    text = "帮我画 --P-cwcw:RuRucwcw:--P-cwcw:Cucrcwcw:crP-cwcw"

    match = SHAPE_PATTERN.search(text)

    assert match is not None
    assert match.group(0) == "--P-cwcw:RuRucwcw:--P-cwcw:Cucrcwcw:crP-cwcw"


def test_shape_code_supports_linked_segments(tmp_path: Path) -> None:
    shape, output = render_shape_code(tmp_path, "CbCuCbCu:Sr------:--CrS_C_:Cw______")

    assert shape.layer_count == 4
    assert output.exists()
    assert output.stat().st_size > 0
