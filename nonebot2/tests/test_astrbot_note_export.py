from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "astrbot-local-plugins"))

from astrbot_plugin_qqbot_features.note_export import export_group_notes_markdown
from astrbot_plugin_qqbot_features.note_export import parse_note_export_count


class AstrBotNoteExportTest(unittest.TestCase):
    def test_parse_note_export_count_uses_default_and_clamps(self) -> None:
        self.assertEqual(parse_note_export_count("记录一下这个对话的内容到当前目录下 .md格式"), 50)
        self.assertEqual(parse_note_export_count("棉花记录 20"), 20)
        self.assertEqual(parse_note_export_count("棉花导出md 999"), 200)

    def test_export_group_notes_markdown_uses_fixed_astrbot_data_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            astrbot_root = workspace / "data" / "astrbot"
            group_context_root = workspace / "data" / "nonebot2" / "run" / "ai" / "group_context"
            group_context_root.mkdir(parents=True)
            (group_context_root / "123456.json").write_text(
                json.dumps(
                    [
                        {
                            "user_id": "10001",
                            "sender_name": "甲",
                            "text": "第一条",
                            "timestamp": 0,
                            "message_id": "m1",
                        },
                        {
                            "user_id": "10002",
                            "sender_name": "乙",
                            "text": "第二条",
                            "timestamp": 0,
                            "message_id": "m2",
                        },
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            old_astrbot_root = os.environ.get("ASTRBOT_ROOT")
            os.environ["ASTRBOT_ROOT"] = str(astrbot_root)
            try:
                result = export_group_notes_markdown(
                    group_id="123456",
                    text="棉花记录 1",
                    now=datetime(2026, 6, 9, 19, 30, 0),
                )
            finally:
                if old_astrbot_root is None:
                    os.environ.pop("ASTRBOT_ROOT", None)
                else:
                    os.environ["ASTRBOT_ROOT"] = old_astrbot_root

            self.assertEqual(result.count, 1)
            self.assertEqual(
                result.path,
                astrbot_root / "data" / "exports" / "group_notes" / "group-123456-20260609-193000.md",
            )
            content = result.path.read_text(encoding="utf-8")
            self.assertIn("# 群聊记录导出 - 123456", content)
            self.assertIn("消息数量：1", content)
            self.assertNotIn("第一条", content)
            self.assertIn("第二条", content)


if __name__ == "__main__":
    unittest.main()
