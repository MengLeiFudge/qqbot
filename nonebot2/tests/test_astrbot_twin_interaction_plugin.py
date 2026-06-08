from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "astrbot-local-plugins"))

from astrbot_plugin_twin_interaction.logic import (
    TwinInteractionConfig,
    build_direct_twin_prompt,
    build_twin_injection,
    is_bot_sender_id,
    is_twin_related_text,
    load_recent_other_bot_records,
    read_profile,
    read_profile_for_self_id,
    should_handle_direct_twin_request,
)


class AstrBotTwinInteractionPluginTest(unittest.TestCase):
    def test_detects_twin_related_text_without_generic_noise(self) -> None:
        profile = read_profile("angel")

        self.assertTrue(is_twin_related_text("天使棉花糖你怎么看恶魔刚才那句", profile))
        self.assertTrue(is_twin_related_text("你们双子今天谁值班", profile))
        self.assertFalse(is_twin_related_text("普通 Factorio 下载链接", profile))

    def test_direct_request_requires_private_wake_or_current_bot_mention(self) -> None:
        profile = read_profile("angel")

        self.assertTrue(
            should_handle_direct_twin_request(
                "天使棉花糖你点评一下恶魔刚才那句",
                profile,
                is_private=False,
                is_at_or_wake_command=False,
            )
        )
        self.assertTrue(
            should_handle_direct_twin_request(
                "恶魔刚才那句怎么理解",
                profile,
                is_private=False,
                is_at_or_wake_command=True,
            )
        )
        self.assertFalse(
            should_handle_direct_twin_request(
                "恶魔刚才那句怎么理解",
                profile,
                is_private=False,
                is_at_or_wake_command=False,
            )
        )

    def test_bot_sender_ids_are_never_eligible_for_direct_handling(self) -> None:
        profile = read_profile("angel")

        self.assertTrue(is_bot_sender_id(profile.bot_id, "999", profile))
        self.assertTrue(is_bot_sender_id(profile.other_bot_id, "999", profile))
        self.assertTrue(is_bot_sender_id("333", "333", profile))
        self.assertFalse(is_bot_sender_id("333", "999", profile))

    def test_profile_can_be_inferred_from_event_self_id(self) -> None:
        self.assertEqual(read_profile_for_self_id("1443944862").profile, "angel")
        self.assertEqual(read_profile_for_self_id("2629227874").profile, "demon")
        self.assertEqual(read_profile_for_self_id("missing", "angel").profile, "angel")

    def test_load_recent_other_bot_records_only_uses_other_bot_public_context(self) -> None:
        profile = read_profile("angel")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "123.json").write_text(
                json.dumps(
                    [
                        {"user_id": "111", "text": "human"},
                        {"user_id": profile.other_bot_id, "text": "恶魔第一句", "message_id": "a"},
                        {"user_id": profile.bot_id, "text": "天使自己的话"},
                        {"user_id": profile.other_bot_id, "text": "恶魔第二句", "message_id": "b"},
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            records = load_recent_other_bot_records(root, "123", profile, limit=1)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["text"], "恶魔第二句")

    def test_injection_and_direct_prompt_keep_identity_boundary(self) -> None:
        profile = read_profile("angel")
        config = TwinInteractionConfig(
            enabled_groups=set(),
            direct_handler_enabled=True,
            max_context_messages=2,
            max_context_chars=2000,
            context_root=Path("/tmp/missing"),
        )

        injection = build_twin_injection(
            text="天使棉花糖让你妹妹说句话",
            group_id="123",
            profile=profile,
            config=config,
        )
        prompt = build_direct_twin_prompt(
            text="天使棉花糖让你妹妹说句话",
            group_id="123",
            profile=profile,
            config=config,
        )

        self.assertIn("当前 bot：😇棉花糖😇", injection)
        self.assertIn("另一个 bot：👿棉花糖👿", injection)
        self.assertIn("禁止：冒充另一个 bot 输出", injection)
        self.assertIn("不要替另一个 bot 发言", prompt)
        self.assertIn("用户原话：天使棉花糖让你妹妹说句话", prompt)


if __name__ == "__main__":
    unittest.main()
