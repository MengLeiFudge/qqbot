from __future__ import annotations

import sys
from pathlib import Path
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1] / "astrbot-local-plugins"
sys.path.insert(0, str(PLUGIN_ROOT))

from astrbot_plugin_qqbot_features.meme_manager.commands import (  # noqa: E402
    looks_like_meme_manager_command,
)
from astrbot_plugin_qqbot_features.meme_manager.commands import (  # noqa: E402
    parse_meme_manager_command,
)


class MemeManagerCommandTests(unittest.TestCase):
    def test_default_command_uses_primary_gallery_action(self) -> None:
        command = parse_meme_manager_command("表情管理")

        self.assertIsNotNone(command)
        self.assertEqual(command.action, "list_emotions")
        self.assertEqual(command.primary_text, "查看图库")
        self.assertFalse(command.admin_only)

    def test_alias_maps_to_primary_action(self) -> None:
        command = parse_meme_manager_command("表情管理 打开管理后台")

        self.assertIsNotNone(command)
        self.assertEqual(command.action, "start_webui")
        self.assertEqual(command.primary_text, "开启管理后台")
        self.assertTrue(command.admin_only)

    def test_compact_command_keeps_argument(self) -> None:
        command = parse_meme_manager_command("表情管理添加表情 开心")

        self.assertIsNotNone(command)
        self.assertEqual(command.action, "upload_meme")
        self.assertEqual(command.argument, "开心")
        self.assertEqual(command.primary_text, "添加表情")

    def test_non_command_text_is_ignored(self) -> None:
        self.assertFalse(looks_like_meme_manager_command("今天表情管理挺好用"))


if __name__ == "__main__":
    unittest.main()
