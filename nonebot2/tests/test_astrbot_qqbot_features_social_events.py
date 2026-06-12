from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "astrbot-local-plugins"))

from astrbot_plugin_qqbot_features.social_events import (
    GROUP_MEMBER_WELCOME_EXPRESSIONS,
    format_group_member_welcome,
    format_self_join_private_notice,
    should_send_member_welcome,
)


class AstrBotQQBotFeaturesSocialEventsTest(unittest.TestCase):
    def test_self_join_notice_names_group_without_owner_assumption(self) -> None:
        self.assertEqual(
            format_self_join_private_notice("测试群", "1085441389"),
            "棉花糖已经加入群聊测试群（1085441389）了喵！",
        )

    def test_self_join_notice_has_fallback_group_name(self) -> None:
        self.assertEqual(
            format_self_join_private_notice("", "1085441389"),
            "棉花糖已经加入群聊未知群聊（1085441389）了喵！",
        )

    def test_member_welcome_allows_both_bots_but_never_twin_bot(self) -> None:
        self.assertTrue(
            should_send_member_welcome(
                user_id="605738729",
                self_id="2629227874",
            )
        )
        self.assertTrue(
            should_send_member_welcome(
                user_id="605738729",
                self_id="1443944862",
            )
        )
        self.assertFalse(
            should_send_member_welcome(
                user_id="1443944862",
                self_id="2629227874",
            )
        )

    def test_member_welcome_uses_expanded_suffixes_and_profile_text(self) -> None:
        self.assertEqual(
            GROUP_MEMBER_WELCOME_EXPRESSIONS,
            (
                "群地位-1",
                "群地位--",
                "群地位=群地位-1",
                "群地位+=-1",
                "群地位-=1",
                "群地位=群地位+(-1)",
                "群地位=群地位+i²",
                "群地位+=i²",
                "群地位-=-i²",
                "群地位(t+1)=群地位(t)-1",
                "群地位=群地位+e^(iπ)",
                "群地位+=e^(iπ)",
                "群地位-=(-e^(iπ))",
                "群地位=群地位+cos(π)",
                "群地位+=cos(π)",
            ),
        )
        self.assertTrue(all(" " not in expression for expression in GROUP_MEMBER_WELCOME_EXPRESSIONS))
        self.assertEqual(
            format_group_member_welcome("1443944862", "群地位-1"),
            " 欢迎大佬喵！群地位-1",
        )
        self.assertEqual(
            format_group_member_welcome("2629227874", "群地位-1"),
            " 来了个大佬，群地位-1",
        )


if __name__ == "__main__":
    unittest.main()
