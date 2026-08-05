from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins"))

from astrbot_plugin_qqbot_features.codexradar_efficiency import (  # noqa: E402
    CodexRadarEfficiencySnapshot,
    parse_codexradar_efficiency,
    render_codexradar_efficiency_image,
)


class CodexRadarEfficiencyTest(unittest.TestCase):
    """Verify bounded parsing and fixed-width report rendering."""

    def test_parse_ignores_invalid_points_and_sorts_families(self) -> None:
        snapshot = parse_codexradar_efficiency(
            {
                "source_updated_at": "2026-08-05T08:54:14+08:00",
                "runs_24h_total": 548,
                "points": [
                    {
                        "model": "gpt-5.6-terra",
                        "effort": "high",
                        "iq": 81.7,
                        "average_price_usd": 1.1,
                        "average_minutes": 13,
                        "runs_24h": 17,
                    },
                    {"model": "gpt-5.6-sol", "effort": "ultra", "iq": 100.4},
                    {"model": "bad", "effort": "unknown", "iq": 100},
                    {"model": "bad", "effort": "low", "iq": "nan"},
                    "not-an-object",
                ],
            }
        )

        self.assertEqual(snapshot.source_updated_at, "2026-08-05T08:54:14+08:00")
        self.assertEqual(snapshot.runs_24h_total, 548)
        self.assertEqual([(point.model, point.effort) for point in snapshot.points], [
            ("gpt-5.6-sol", "ultra"),
            ("gpt-5.6-terra", "high"),
        ])

    def test_render_is_cached_fixed_width_nonblank_png(self) -> None:
        snapshot = parse_codexradar_efficiency(
            {
                "source_updated_at": "2026-08-05T08:54:14+08:00",
                "runs_24h_total": 548,
                "points": [
                    {
                        "model": family,
                        "effort": effort,
                        "iq": 80 + index,
                        "average_price_usd": 0.5 + index,
                        "average_minutes": 10 + index,
                        "runs_24h": index + 1,
                    }
                    for index, (family, effort) in enumerate(
                        (
                            ("gpt-5.6-sol", "ultra"),
                            ("gpt-5.6-sol", "max"),
                            ("gpt-5.6-terra", "xhigh"),
                            ("gpt-5.6-luna", "high"),
                            ("gpt-5.5", "medium"),
                            ("deepseek-v4", "low"),
                        )
                    )
                ],
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            first = render_codexradar_efficiency_image(snapshot=snapshot, output_dir=output_dir)
            second = render_codexradar_efficiency_image(snapshot=snapshot, output_dir=output_dir)
            self.assertEqual(first, second)
            with Image.open(first) as image:
                self.assertEqual(image.format, "PNG")
                self.assertEqual(image.width, 1240)
                self.assertGreater(image.height, 700)
                colors = image.resize((124, max(1, image.height // 10))).getcolors(maxcolors=100_000)
                self.assertIsNotNone(colors)
                self.assertGreater(len(colors or []), 10)

    def test_empty_snapshot_renders_explicit_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = render_codexradar_efficiency_image(
                snapshot=CodexRadarEfficiencySnapshot(),
                output_dir=Path(directory),
            )
            with Image.open(path) as image:
                self.assertEqual(image.width, 1240)
                self.assertGreaterEqual(image.height, 300)

    def test_parse_rejects_non_object_and_missing_points(self) -> None:
        with self.assertRaises(ValueError):
            parse_codexradar_efficiency([])
        with self.assertRaises(ValueError):
            parse_codexradar_efficiency({})


if __name__ == "__main__":
    unittest.main()
