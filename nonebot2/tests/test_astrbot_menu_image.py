from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "astrbot-local-plugins"))

from astrbot_plugin_qqbot_features.menu_image import render_feature_menu_image
from astrbot_plugin_qqbot_features.menu_image import render_overview_menu_image
from astrbot_plugin_qqbot_features.menu_catalog import MENU_SECTIONS
from astrbot_plugin_qqbot_features.menu_catalog import find_menu_section
from astrbot_plugin_qqbot_features.twin_poke import should_follow_poke_notice


@dataclass(frozen=True, slots=True)
class StubFeature:
    name: str
    aliases: tuple[str, ...] = ()
    status: str = "已移植"
    lines: tuple[str, ...] = ()


class AstrBotMenuImageTest(unittest.TestCase):
    def test_menu_catalog_groups_user_facing_sections(self) -> None:
        names = [section.name for section in MENU_SECTIONS]

        self.assertEqual(
            names,
            ["群务管理", "棉花糖互动", "养鲲", "落樱之都", "Arcaea", "Factorio", "异形工厂"],
        )
        self.assertEqual(find_menu_section("Arc").name, "Arcaea")
        self.assertEqual(find_menu_section("生图").name, "棉花糖互动")
        self.assertEqual(find_menu_section("群管").name, "群务管理")

    def test_render_overview_menu_image_creates_cached_png(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            first = render_overview_menu_image(features=MENU_SECTIONS, feature_mode="full", output_dir=output_dir)
            second = render_overview_menu_image(features=MENU_SECTIONS, feature_mode="full", output_dir=output_dir)

            self.assertEqual(first, second)
            self.assertTrue(first.is_file())
            with Image.open(first) as image:
                self.assertEqual(image.format, "PNG")
                self.assertEqual(image.width, 1120)
                self.assertGreater(image.height, 300)

    def test_render_feature_menu_image_creates_png(self) -> None:
        feature = StubFeature(
            "生图",
            ("RightCodes",),
            "已移植",
            (
                "棉花糖生图 提示词：提交 RightCodes 生图任务",
                "查看积分：查询当前 QQ 的生图积分",
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = render_feature_menu_image(feature=feature, feature_mode="full", output_dir=Path(temp_dir))

            self.assertTrue(image_path.is_file())
            with Image.open(image_path) as image:
                self.assertEqual(image.format, "PNG")
                self.assertEqual(image.width, 1120)
                self.assertGreater(image.height, 300)

    def test_poke_notice_does_not_follow_twin_bot_targets(self) -> None:
        self.assertFalse(
            should_follow_poke_notice(
                self_id="2629227874",
                user_id="3062317151",
                target_id="1443944862",
            )
        )
        self.assertFalse(
            should_follow_poke_notice(
                self_id="2629227874",
                user_id="1443944862",
                target_id="2629227874",
            )
        )
        self.assertTrue(
            should_follow_poke_notice(
                self_id="2629227874",
                user_id="3062317151",
                target_id="2629227874",
            )
        )


if __name__ == "__main__":
    unittest.main()
