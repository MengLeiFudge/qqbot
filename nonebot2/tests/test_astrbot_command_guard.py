from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "astrbot-local-plugins"))

from astrbot_plugin_qqbot_features.command_guard import clear_command_claims
from astrbot_plugin_qqbot_features.command_guard import decide_migrated_command_route
from astrbot_plugin_qqbot_features.command_guard import targeted_twin_bot_ids
from astrbot_plugin_qqbot_features.command_guard import try_claim_command


class AstrBotCommandGuardTest(unittest.TestCase):
    def tearDown(self) -> None:
        clear_command_claims()

    def test_single_at_targets_only_that_bot_for_fixed_commands(self) -> None:
        angel = decide_migrated_command_route(
            sender_id="3062317151",
            self_id="1443944862",
            at_ids=("1443944862",),
            is_private=False,
            is_direct_or_private=True,
            feature_mode="full",
            full_mode="full",
            command_owner_qq="2629227874",
        )
        demon = decide_migrated_command_route(
            sender_id="3062317151",
            self_id="2629227874",
            at_ids=("1443944862",),
            is_private=False,
            is_direct_or_private=True,
            feature_mode="full",
            full_mode="full",
            command_owner_qq="2629227874",
        )

        self.assertTrue(angel.should_handle)
        self.assertEqual(angel.reason, "explicit_target")
        self.assertFalse(demon.should_handle)
        self.assertEqual(demon.reason, "other_twin_targeted")

    def test_dual_at_allows_current_target_then_claim_deduplicates_message(self) -> None:
        self.assertEqual(targeted_twin_bot_ids(["1443944862", "2629227874", "123"]), {"1443944862", "2629227874"})
        self.assertTrue(try_claim_command("message:m1:rightcodes_draw", now=10.0))
        self.assertFalse(try_claim_command("message:m1:rightcodes_draw", now=11.0))
        self.assertTrue(try_claim_command("message:m1:menu", now=11.0))

    def test_direct_without_explicit_target_uses_command_owner(self) -> None:
        owner = decide_migrated_command_route(
            sender_id="3062317151",
            self_id="2629227874",
            at_ids=(),
            is_private=False,
            is_direct_or_private=True,
            feature_mode="full",
            full_mode="full",
            command_owner_qq="2629227874",
        )
        non_owner = decide_migrated_command_route(
            sender_id="3062317151",
            self_id="1443944862",
            at_ids=(),
            is_private=False,
            is_direct_or_private=True,
            feature_mode="full",
            full_mode="full",
            command_owner_qq="2629227874",
        )

        self.assertTrue(owner.should_handle)
        self.assertEqual(owner.reason, "direct_owner")
        self.assertFalse(non_owner.should_handle)
        self.assertEqual(non_owner.reason, "direct_non_owner_without_explicit_target")


if __name__ == "__main__":
    unittest.main()
