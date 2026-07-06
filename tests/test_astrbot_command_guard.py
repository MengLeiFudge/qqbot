from __future__ import annotations

from pathlib import Path
import random
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins"))

from astrbot_plugin_qqbot_features.command_guard import clear_command_claims
from astrbot_plugin_qqbot_features.command_guard import decide_migrated_command_route
from astrbot_plugin_topic_concentration.twin_scheduler import clear_scheduler_state
from astrbot_plugin_topic_concentration.twin_scheduler import set_group_balance
from astrbot_plugin_qqbot_features.command_guard import targeted_twin_bot_ids
from astrbot_plugin_qqbot_features.command_guard import try_claim_command


class AstrBotCommandGuardTest(unittest.TestCase):
    def tearDown(self) -> None:
        clear_command_claims()
        clear_scheduler_state()

    def test_single_at_targets_only_that_bot_for_fixed_commands(self) -> None:
        angel = decide_migrated_command_route(
            sender_id="3062317151",
            self_id="1443944862",
            at_ids=("1443944862",),
            group_id="10001",
            message_key="command:single-at",
            text="用量",
            is_private=False,
            is_direct_or_private=True,
            feature_mode="full",
            full_mode="full",
            command_owner_qq="2629227874",
            rng=random.Random(1),
        )
        demon = decide_migrated_command_route(
            sender_id="3062317151",
            self_id="2629227874",
            at_ids=("1443944862",),
            group_id="10001",
            message_key="command:single-at",
            text="用量",
            is_private=False,
            is_direct_or_private=True,
            feature_mode="full",
            full_mode="full",
            command_owner_qq="2629227874",
            rng=random.Random(1),
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

    def test_dual_at_fixed_command_uses_one_weighted_worker(self) -> None:
        set_group_balance("10001", -8.0)
        angel = decide_migrated_command_route(
            sender_id="3062317151",
            self_id="1443944862",
            at_ids=("1443944862", "2629227874"),
            group_id="10001",
            message_key="command:dual-at-weighted",
            text="用量",
            is_private=False,
            is_direct_or_private=True,
            feature_mode="full",
            full_mode="full",
            command_owner_qq="2629227874",
            rng=random.Random(0),
        )
        demon = decide_migrated_command_route(
            sender_id="3062317151",
            self_id="2629227874",
            at_ids=("1443944862", "2629227874"),
            group_id="10001",
            message_key="command:dual-at-weighted",
            text="用量",
            is_private=False,
            is_direct_or_private=True,
            feature_mode="full",
            full_mode="full",
            command_owner_qq="2629227874",
            rng=random.Random(0),
        )

        self.assertFalse(angel.should_handle)
        self.assertEqual(angel.reason, "multi_target_other_selected")
        self.assertTrue(demon.should_handle)
        self.assertEqual(demon.reason, "multi_target_selected")
        self.assertEqual(demon.selected_worker, "2629227874")

    def test_direct_without_explicit_target_uses_group_weighted_worker(self) -> None:
        set_group_balance("10001", 8.0)
        angel = decide_migrated_command_route(
            sender_id="3062317151",
            self_id="1443944862",
            at_ids=(),
            group_id="10001",
            message_key="command:weighted",
            text="用量",
            is_private=False,
            is_direct_or_private=True,
            feature_mode="full",
            full_mode="full",
            command_owner_qq="2629227874",
            rng=random.Random(1),
        )
        demon = decide_migrated_command_route(
            sender_id="3062317151",
            self_id="2629227874",
            at_ids=(),
            group_id="10001",
            message_key="command:weighted",
            text="用量",
            is_private=False,
            is_direct_or_private=True,
            feature_mode="full",
            full_mode="full",
            command_owner_qq="2629227874",
            rng=random.Random(1),
        )

        self.assertTrue(angel.should_handle)
        self.assertEqual(angel.reason, "direct_weighted_selected")
        self.assertEqual(angel.selected_worker, "1443944862")
        self.assertFalse(demon.should_handle)
        self.assertEqual(demon.reason, "direct_weighted_other_selected")


if __name__ == "__main__":
    unittest.main()
