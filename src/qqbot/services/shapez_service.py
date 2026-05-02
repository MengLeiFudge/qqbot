from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from PIL import Image, ImageDraw


SHAPE_PATTERN = re.compile(r"(?i)([CRWS][rgbypcuw]|--){4}(:([CRWS][rgbypcuw]|--){4}){0,3}")

COLOR_MAP = {
    "u": "#aaaaaa",
    "r": "#ff666a",
    "g": "#78ff66",
    "b": "#66a7ff",
    "y": "#fcf52a",
    "p": "#dd66ff",
    "c": "#87fff5",
    "w": "#ffffff",
}


@dataclass(frozen=True, slots=True)
class ShapeCode:
    short_key: str

    def __post_init__(self) -> None:
        if not SHAPE_PATTERN.fullmatch(self.short_key):
            raise ValueError(f"invalid shape code: {self.short_key}")

    @property
    def layers(self) -> list[str]:
        return self.short_key.split(":")

    @property
    def layer_count(self) -> int:
        return len(self.layers)


def render_shape_image(shape: ShapeCode, output: Path, size: int = 320) -> Path:
    image = Image.new("RGBA", (size, size), (250, 240, 230, 255))
    draw = ImageDraw.Draw(image)
    center = size / 2
    base_radius = size * 0.38

    for layer_index, layer in enumerate(shape.layers):
        scale = 1.0 - layer_index * 0.18
        layer_radius = base_radius * scale
        for quadrant in range(4):
            token = layer[quadrant * 2 : quadrant * 2 + 2]
            if token == "--":
                continue
            shape_type = token[0].upper()
            color = COLOR_MAP[token[1].lower()]
            bbox = [
                center - layer_radius,
                center - layer_radius,
                center + layer_radius,
                center + layer_radius,
            ]
            start_angles = [270, 0, 90, 180]
            start = start_angles[quadrant]
            end = start + 90
            if shape_type == "C":
                draw.pieslice(bbox, start=start, end=end, fill=color, outline="#555555", width=2)
            elif shape_type == "R":
                _draw_polygon_quadrant(draw, center, layer_radius, quadrant, color)
            elif shape_type == "S":
                _draw_star_quadrant(draw, center, layer_radius, quadrant, color)
            elif shape_type == "W":
                _draw_windmill_quadrant(draw, center, layer_radius, quadrant, color)

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG")
    return output


def render_shape_code(data_root: Path, short_code: str) -> tuple[ShapeCode, Path]:
    shape = ShapeCode(short_code.replace("：", ":").strip())
    output = Path(data_root) / "shapez" / "img" / "shape" / (
        shape.short_key.replace(":", "：") + ".png"
    )
    render_shape_image(shape, output)
    return shape, output


def _draw_polygon_quadrant(draw: ImageDraw.ImageDraw, center: float, radius: float, quadrant: int, color: str) -> None:
    points = {
        0: [(center, center), (center + radius, center), (center + radius, center - radius), (center, center - radius)],
        1: [(center, center), (center + radius, center), (center + radius, center + radius), (center, center + radius)],
        2: [(center, center), (center - radius, center), (center - radius, center + radius), (center, center + radius)],
        3: [(center, center), (center - radius, center), (center - radius, center - radius), (center, center - radius)],
    }[quadrant]
    draw.polygon(points, fill=color, outline="#555555")


def _draw_star_quadrant(draw: ImageDraw.ImageDraw, center: float, radius: float, quadrant: int, color: str) -> None:
    half = radius / 2
    points = {
        0: [(center, center), (center + radius, center - radius), (center + half, center), (center, center - half)],
        1: [(center, center), (center + radius, center + radius), (center, center + half), (center + half, center)],
        2: [(center, center), (center - radius, center + radius), (center - half, center), (center, center + half)],
        3: [(center, center), (center - radius, center - radius), (center, center - half), (center - half, center)],
    }[quadrant]
    draw.polygon(points, fill=color, outline="#555555")


def _draw_windmill_quadrant(draw: ImageDraw.ImageDraw, center: float, radius: float, quadrant: int, color: str) -> None:
    half = radius / 2
    points = {
        0: [(center, center), (center + radius, center - radius), (center + radius, center), (center + half, center)],
        1: [(center, center), (center + radius, center + radius), (center, center + radius), (center, center + half)],
        2: [(center, center), (center - radius, center + radius), (center - radius, center), (center - half, center)],
        3: [(center, center), (center - radius, center - radius), (center, center - radius), (center, center - half)],
    }[quadrant]
    draw.polygon(points, fill=color, outline="#555555")
