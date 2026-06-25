from __future__ import annotations

import json
import tempfile
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "astrbot-local-plugins"))

from astrbot_plugin_qqbot_features.meme_manager import local_index


class MemeManagerLocalIndexTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.plugin_data = self.root / "plugin_data" / "meme_manager"
        self.source_pack = self.root / "data" / "memes" / "mlj_pack"
        self.source_images = self.source_pack / "images" / "happy_cheer"
        self.source_images.mkdir(parents=True)
        (self.source_images / "cheer.png").write_bytes(b"happy-cheer")
        (self.source_images / "disabled.png").write_bytes(b"disabled")

        self.old_paths = (
            local_index.MEME_INDEX_PATH,
            local_index.MEMES_DIR,
            local_index.MEMES_DATA_PATH,
        )
        local_index.MEME_INDEX_PATH = self.plugin_data / "meme_index.json"
        local_index.MEMES_DIR = self.plugin_data / "memes"
        local_index.MEMES_DATA_PATH = self.plugin_data / "memes_data.json"
        local_index._recent_selections.clear()

    def tearDown(self) -> None:
        (
            local_index.MEME_INDEX_PATH,
            local_index.MEMES_DIR,
            local_index.MEMES_DATA_PATH,
        ) = self.old_paths
        local_index._recent_selections.clear()
        self.temp_dir.cleanup()

    def test_migrate_mlj_pack_index_copies_images_and_metadata(self) -> None:
        source_index = self._write_source_index()

        result = local_index.migrate_mlj_pack_index(source_index)

        self.assertEqual(result["copied"], 2)
        self.assertEqual(result["updated"], 0)
        self.assertTrue((local_index.MEMES_DIR / "happy_cheer" / "cheer.png").is_file())
        migrated = json.loads(local_index.MEME_INDEX_PATH.read_text(encoding="utf-8"))
        self.assertEqual(migrated["source"], "meme_manager_migrated_mlj_pack")
        self.assertIn("happy_cheer", migrated["categories"])
        self.assertEqual(len(migrated["images"]), 2)
        descriptions = json.loads(local_index.MEMES_DATA_PATH.read_text(encoding="utf-8"))
        self.assertIn("happy_cheer", descriptions)

    def test_selector_uses_local_index_and_skips_disabled_images(self) -> None:
        source_index = self._write_source_index()
        local_index.migrate_mlj_pack_index(source_index)

        selected = local_index.select_meme_for_emotion(
            "happy_cheer",
            context_text="成功了 开心",
        )

        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, "cheer.png")

    def test_migrate_repairs_existing_index_entry_when_file_is_missing(self) -> None:
        source_index = self._write_source_index()
        local_index.save_meme_index(
            {
                "categories": {
                    "happy_cheer": {
                        "label": "开心加油",
                        "description": "",
                        "auto_send_enabled": True,
                    }
                },
                "images": [
                    {
                        "category": "happy_cheer",
                        "filename": "cheer.png",
                        "relative_path": "memes/happy_cheer/cheer.png",
                        "sha256": "",
                        "auto_send_enabled": True,
                    }
                ],
            }
        )

        result = local_index.migrate_mlj_pack_index(source_index)

        self.assertGreaterEqual(result["copied"], 1)
        self.assertEqual(result["skipped_missing"], 0)
        self.assertTrue((local_index.MEMES_DIR / "happy_cheer" / "cheer.png").is_file())

    def _write_source_index(self) -> Path:
        source_index = self.source_pack / "index.json"
        payload = {
            "categories": {
                "happy_cheer": {
                    "label": "开心加油",
                    "description": "开心、庆祝、加油",
                    "use_cases": ["成功确认", "轻松庆祝"],
                    "avoid_when": ["严肃报错"],
                    "auto_send_enabled": True,
                }
            },
            "images": [
                {
                    "id": "happy-cheer",
                    "category": "happy_cheer",
                    "relative_path": "images/happy_cheer/cheer.png",
                    "title": "开心加油",
                    "content_caption": "适合成功和鼓励",
                    "use_cases": ["成功确认"],
                    "emotion_tags": ["开心", "加油"],
                    "intensity": 2,
                    "avoid_when": ["报错"],
                    "auto_send_enabled": True,
                    "weight": 5,
                    "sha256": "",
                },
                {
                    "id": "happy-disabled",
                    "category": "happy_cheer",
                    "relative_path": "images/happy_cheer/disabled.png",
                    "title": "禁发表情",
                    "content_caption": "不应自动发送",
                    "use_cases": ["测试"],
                    "emotion_tags": ["开心"],
                    "intensity": 2,
                    "avoid_when": [],
                    "auto_send_enabled": False,
                    "weight": 100,
                    "sha256": "",
                },
            ],
        }
        source_index.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return source_index


if __name__ == "__main__":
    unittest.main()
