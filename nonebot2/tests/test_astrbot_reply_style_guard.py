from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "astrbot-local-plugins"))

from astrbot_plugin_reply_style_guard.logic import sanitize_reply_plain_text
from astrbot_plugin_reply_style_guard.logic import should_disable_segmented_reply_for_text
from astrbot_plugin_reply_style_guard.logic import strip_followup_tail
from astrbot_plugin_reply_style_guard.logic import strip_markdown_syntax


class AstrBotReplyStyleGuardTest(unittest.TestCase):
    def test_stripping_only_followup_question_returns_empty_text(self) -> None:
        self.assertEqual(strip_followup_tail("你把具体名字发我。"), "")
        self.assertEqual(strip_followup_tail("是不是更安全？"), "")

    def test_stripping_followup_tail_keeps_real_answer(self) -> None:
        self.assertEqual(
            strip_followup_tail("这个网站不正规，别登录喵。你把具体名字发我。"),
            "这个网站不正规，别登录喵。",
        )

    def test_strip_markdown_syntax_keeps_plain_text(self) -> None:
        self.assertEqual(
            strip_markdown_syntax(
                "目前能确定的规则是：\n"
                "- **并联 Mek 粉碎机**：最稳。\n"
                "- `gpt-image-2`：每天首张免费。\n"
                "1. [文档](https://example.invalid)"
            ),
            "目前能确定的规则是：\n"
            "· 并联 Mek 粉碎机：最稳。\n"
            "· gpt-image-2：每天首张免费。\n"
            "1、文档 https://example.invalid",
        )

    def test_sanitize_reply_plain_text_strips_markdown_and_tail(self) -> None:
        self.assertEqual(
            sanitize_reply_plain_text("**结论**：别登录。\n- 原因：不正规。\n你把具体名字发我。"),
            "结论：别登录。\n· 原因：不正规。",
        )

    def test_strip_markdown_syntax_preserves_json_indentation(self) -> None:
        self.assertEqual(
            strip_markdown_syntax(
                "```json\n"
                "{\n"
                '  "model": "gpt-image-2",\n'
                '  "size": "1024x1024"\n'
                "}\n"
                "```"
            ),
            "{\n"
            '  "model": "gpt-image-2",\n'
            '  "size": "1024x1024"\n'
            "}",
        )

    def test_segmented_reply_is_disabled_when_it_would_split_more_than_three_parts(self) -> None:
        self.assertTrue(
            should_disable_segmented_reply_for_text(
                "比如：\n"
                "工资太高税扣好多。\n"
                "车太大停车麻烦。\n"
                "随便考又第一。\n"
                "这就是凡尔赛。"
            )
        )
        self.assertFalse(should_disable_segmented_reply_for_text("懂了吧，低调版炫耀。"))


if __name__ == "__main__":
    unittest.main()
