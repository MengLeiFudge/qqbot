from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "astrbot-local-plugins"))

from astrbot_plugin_reply_style_guard.logic import strip_followup_tail


class AstrBotReplyStyleGuardTest(unittest.TestCase):
    def test_stripping_only_followup_question_returns_empty_text(self) -> None:
        self.assertEqual(strip_followup_tail("你把具体名字发我。"), "")
        self.assertEqual(strip_followup_tail("是不是更安全？"), "")

    def test_stripping_followup_tail_keeps_real_answer(self) -> None:
        self.assertEqual(
            strip_followup_tail("这个网站不正规，别登录喵。你把具体名字发我。"),
            "这个网站不正规，别登录喵。",
        )


if __name__ == "__main__":
    unittest.main()
