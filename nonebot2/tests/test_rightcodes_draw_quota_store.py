from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from qqbot.features.ai.rightcodes_draw_quota_store import (
    RightCodesDrawQuotaStore,
    format_rightcodes_draw_points_status,
)


class RightCodesDrawQuotaStoreTest(unittest.TestCase):
    def test_gpt_image_2_first_draw_is_free_once_per_day(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RightCodesDrawQuotaStore(Path(temp_dir))
            first = store.reserve("10001", model="gpt-image-2", date_key="2026-06-08")
            second = store.reserve("10001", model="gpt-image-2", date_key="2026-06-08")

            self.assertTrue(first.allowed)
            self.assertTrue(first.used_free)
            self.assertEqual(first.cost_points, 0)
            self.assertFalse(second.allowed)
            self.assertEqual(second.cost_points, 20)
            self.assertEqual(second.balance_before, 0)

    def test_paid_draw_uses_message_points_by_model_price(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RightCodesDrawQuotaStore(Path(temp_dir))
            store.record_group_message("10001", amount=80)

            vip = store.reserve("10001", model="gpt-image-2-vip", date_key="2026-06-08")

            self.assertTrue(vip.allowed)
            self.assertFalse(vip.used_free)
            self.assertEqual(vip.cost_points, 65)
            self.assertEqual(vip.balance_before, 80)
            self.assertEqual(vip.balance_after, 15)

    def test_second_gpt_image_2_draw_costs_twenty_points(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RightCodesDrawQuotaStore(Path(temp_dir))
            store.record_group_message("10001", amount=25)
            first = store.reserve("10001", model="gpt-image-2", date_key="2026-06-08")
            second = store.reserve("10001", model="gpt-image-2", date_key="2026-06-08")

            self.assertTrue(first.used_free)
            self.assertTrue(second.allowed)
            self.assertEqual(second.cost_points, 20)
            self.assertEqual(second.balance_after, 5)

    def test_refund_restores_paid_points_and_free_use(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RightCodesDrawQuotaStore(Path(temp_dir))
            free = store.reserve("10001", model="gpt-image-2", date_key="2026-06-08")
            store.refund(free)
            free_again = store.reserve("10001", model="gpt-image-2", date_key="2026-06-08")

            self.assertTrue(free_again.used_free)

            store.record_group_message("10001", amount=20)
            paid = store.reserve("10001", model="gpt-image-2", date_key="2026-06-08")
            store.refund(paid)
            paid_again = store.reserve("10001", model="gpt-image-2", date_key="2026-06-08")

            self.assertTrue(paid_again.allowed)
            self.assertEqual(paid_again.balance_before, 20)

    def test_get_balance_defaults_for_new_user(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RightCodesDrawQuotaStore(Path(temp_dir))
            balance = store.get_balance("10001", date_key="2026-06-08")

            self.assertEqual(balance.points, 0)
            self.assertEqual(balance.message_count, 0)
            self.assertTrue(balance.free_available)

            text = format_rightcodes_draw_points_status(balance)
            self.assertIn("当前生图积分：0", text)
            self.assertIn("全群累计消息数：0", text)
            self.assertIn("gpt-image-2 今日免费次数：可用", text)
            self.assertIn("gpt-image-2-vip: 65 积分", text)

    def test_get_balance_reports_used_free_and_points(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RightCodesDrawQuotaStore(Path(temp_dir))
            store.record_group_message("10001", amount=25)
            store.reserve("10001", model="gpt-image-2", date_key="2026-06-08")

            balance = store.get_balance("10001", date_key="2026-06-08")

            self.assertEqual(balance.points, 25)
            self.assertEqual(balance.message_count, 25)
            self.assertFalse(balance.free_available)

            text = format_rightcodes_draw_points_status(balance)
            self.assertIn("当前生图积分：25", text)
            self.assertIn("gpt-image-2 今日免费次数：已使用", text)
            self.assertIn("gpt-image-2: 20 积分", text)


if __name__ == "__main__":
    unittest.main()
