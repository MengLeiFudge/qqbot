from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins"))

from astrbot_plugin_qqbot_features.sub2api_usage import (  # noqa: E402
    Sub2APIAccountUsage,
    Sub2APIUsageSnapshot,
    Sub2APIUsageWindow,
    Sub2APIUserUsage,
)
from astrbot_plugin_qqbot_features.sub2api_usage_image import render_sub2api_usage_image  # noqa: E402


class AstrBotSub2APIUsageImageTest(unittest.TestCase):
    def test_render_creates_dynamic_cached_report_image(self) -> None:
        snapshot = Sub2APIUsageSnapshot(
            accounts=(
                Sub2APIAccountUsage(
                    account_id=1,
                    name="Christeena",
                    platform="openai",
                    account_type="oauth",
                    status="active",
                    current_concurrency=0,
                    five_hour=Sub2APIUsageWindow(utilization=0.0, remaining_seconds=0),
                    seven_day=Sub2APIUsageWindow(utilization=5.0, remaining_seconds=3600),
                    last_used_at="2026-07-15T02:34:16.710391+08:00",
                    updated_at="2026-07-15T02:35:00.831240125+08:00",
                ),
            ),
            users=tuple(
                Sub2APIUserUsage(
                    user_id=index,
                    username="" if index % 2 else f"user-{index}",
                    email=f"user-{index}@example.com",
                    account_seven_day_actual_cost=float(index) / 3,
                    last_24_hours_actual_cost=float(10 - index),
                    seven_day_actual_cost=float(8 - index),
                    fourteen_day_actual_cost=float(12 - index),
                    thirty_day_actual_cost=float(index),
                )
                for index in range(1, 9)
            ),
            accounts_refreshed_at=datetime(2026, 7, 13, tzinfo=timezone.utc),
            users_refreshed_at=datetime(2026, 7, 13, tzinfo=timezone.utc),
            account_seven_day_refreshed_at=datetime(2026, 7, 13, tzinfo=timezone.utc),
            users_error="上游暂时超时，保留上次成功用户榜。",
        )
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            first_path = render_sub2api_usage_image(snapshot=snapshot, output_dir=output_dir)
            second_path = render_sub2api_usage_image(snapshot=snapshot, output_dir=output_dir)

            self.assertEqual(first_path, second_path)
            self.assertTrue(first_path.is_file())
            with Image.open(first_path) as image:
                self.assertEqual(image.width, 1240)
                self.assertGreater(image.height, 700)
                self.assertEqual(image.format, "PNG")


if __name__ == "__main__":
    unittest.main()
