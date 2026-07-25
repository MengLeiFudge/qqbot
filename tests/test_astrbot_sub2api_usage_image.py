from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins"))

from astrbot_plugin_qqbot_features.sub2api_usage import (  # noqa: E402
    Sub2APIAccountSevenDayRanking,
    Sub2APIAccountUsage,
    Sub2APIAccountUserUsage,
    Sub2APIUsageSnapshot,
    Sub2APIUsageWindow,
    Sub2APIUserUsage,
)
from astrbot_plugin_qqbot_features.sub2api_usage_image import render_sub2api_usage_image  # noqa: E402


class AstrBotSub2APIUsageImageTest(unittest.TestCase):
    """Verify cached report geometry for per-account and global rankings."""

    def test_render_stacks_per_account_rankings_before_global_table(self) -> None:
        """Populated account rows increase height without changing the fixed width."""
        accounts = (
            Sub2APIAccountUsage(
                account_id=1,
                name="Christeena primary account with a deliberately long display name",
                platform="openai",
                account_type="oauth",
                status="active",
                current_concurrency=0,
                five_hour=Sub2APIUsageWindow(utilization=0.0, remaining_seconds=0),
                seven_day=Sub2APIUsageWindow(utilization=5.0, remaining_seconds=3600),
                last_used_at="2026-07-15T02:34:16.710391+08:00",
                updated_at="2026-07-15T02:35:00.831240125+08:00",
            ),
            Sub2APIAccountUsage(
                account_id=2,
                name="Backup",
                platform="claude",
                account_type="session",
                status="active",
                five_hour=Sub2APIUsageWindow(utilization=10.0, remaining_seconds=7200),
                seven_day=Sub2APIUsageWindow(utilization=20.0, remaining_seconds=86400),
            ),
        )
        refreshed_at = datetime(2026, 7, 13, tzinfo=timezone.utc)
        snapshot = Sub2APIUsageSnapshot(
            accounts=accounts,
            account_seven_day_rankings=(
                Sub2APIAccountSevenDayRanking(
                    account_id=1,
                    users=tuple(
                        Sub2APIAccountUserUsage(
                            user_id=index,
                            username=f"account-one-user-{index}-with-a-long-name",
                            actual_cost=54321.98 / index,
                        )
                        for index in range(1, 9)
                    ),
                    refreshed_at=refreshed_at,
                ),
                Sub2APIAccountSevenDayRanking(
                    account_id=2,
                    users=(
                        Sub2APIAccountUserUsage(user_id=2, username="backup-two", actual_cost=7654.32),
                        Sub2APIAccountUserUsage(user_id=1, username="backup-one", actual_cost=12.34),
                    ),
                    refreshed_at=refreshed_at,
                    error="upstream timeout; showing the last complete account ranking",
                ),
            ),
            users=tuple(
                Sub2APIUserUsage(
                    user_id=index,
                    username="" if index % 2 else f"global-user-{index}",
                    email=f"user-{index}@example.com",
                    last_24_hours_actual_cost=float(10 - index),
                    seven_day_actual_cost=float(8 - index),
                    fourteen_day_actual_cost=float(12 - index),
                    thirty_day_actual_cost=float(index),
                )
                for index in range(1, 9)
            ),
            accounts_refreshed_at=refreshed_at,
            users_refreshed_at=refreshed_at,
            users_error="global ranking is stale but still visible",
        )
        empty_account_rankings = replace(
            snapshot,
            account_seven_day_rankings=tuple(
                Sub2APIAccountSevenDayRanking(
                    account_id=account.account_id,
                    refreshed_at=refreshed_at,
                )
                for account in accounts
            ),
        )

        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            populated_path = render_sub2api_usage_image(snapshot=snapshot, output_dir=output_dir)
            cached_path = render_sub2api_usage_image(snapshot=snapshot, output_dir=output_dir)
            empty_path = render_sub2api_usage_image(snapshot=empty_account_rankings, output_dir=output_dir)

            self.assertEqual(populated_path, cached_path)
            self.assertNotEqual(populated_path, empty_path)
            with Image.open(populated_path) as populated_image, Image.open(empty_path) as empty_image:
                self.assertEqual(populated_image.width, 1240)
                self.assertEqual(empty_image.width, 1240)
                self.assertGreater(populated_image.height, empty_image.height)
                self.assertGreater(populated_image.height, 1500)
                self.assertEqual(populated_image.format, "PNG")

    def test_render_handles_empty_accounts_and_global_users(self) -> None:
        """The no-data error state still produces a valid fixed-width report."""
        snapshot = Sub2APIUsageSnapshot(
            accounts_error="account list timeout",
            users_error="global ranking timeout",
        )

        with tempfile.TemporaryDirectory() as directory:
            image_path = render_sub2api_usage_image(
                snapshot=snapshot,
                output_dir=Path(directory),
            )

            with Image.open(image_path) as image:
                self.assertEqual(image.width, 1240)
                self.assertGreater(image.height, 500)
                self.assertEqual(image.format, "PNG")


if __name__ == "__main__":
    unittest.main()
