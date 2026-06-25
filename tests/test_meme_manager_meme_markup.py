from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "astrbot-local-plugins"))

from astrbot_plugin_qqbot_features.meme_manager.meme_markup import clean_meme_markup_text
from astrbot_plugin_qqbot_features.meme_manager.meme_markup import extract_wrapped_meme_markups


class MemeManagerMarkupTest(unittest.TestCase):
    def test_extracts_standard_wrapped_label(self) -> None:
        cleaned, emotions = extract_wrapped_meme_markups(
            "&&affection_kiss&&服了你了",
            {"affection_kiss"},
        )

        self.assertEqual(cleaned, "服了你了")
        self.assertEqual(emotions, ["affection_kiss"])

    def test_extracts_missing_ampersand_and_extra_a_prefix_label(self) -> None:
        cleaned, emotions = extract_wrapped_meme_markups(
            "&Aaffection_kiss 服了你了，你赢了行吧，摸完快滚。",
            {"affection_kiss"},
        )

        self.assertEqual(cleaned, "服了你了，你赢了行吧，摸完快滚。")
        self.assertEqual(emotions, ["affection_kiss"])

    def test_cleaner_removes_malformed_known_label_without_image_send(self) -> None:
        self.assertEqual(
            clean_meme_markup_text(
                "先别发图 &Aaffection_kiss 只留文字",
                {"affection_kiss"},
            ),
            "先别发图 只留文字",
        )


if __name__ == "__main__":
    unittest.main()
