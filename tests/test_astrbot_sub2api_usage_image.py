from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

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
from astrbot_plugin_qqbot_features.sub2api_usage_image import (  # noqa: E402
    _USER_DAY_COL,
    _USER_NAME_MAX_WIDTH,
    _USER_NAME_X,
    _USER_THIRTY_COL,
    _USER_WEEK_COL,
    _ellipsize,
    _fit_amount_text,
    _format_amount_compact,
    _format_amount_plain,
    _format_amount_scientific,
    render_sub2api_usage_image,
    _Fonts,
    _find_font_path,
)


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
                    current_day_actual_cost=float(10 - index),
                    current_week_actual_cost=float(8 - index),
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

    def test_global_amount_columns_are_disjoint_and_fit_large_values(self) -> None:
        """Large same-row amounts stay inside fixed day/week/30d columns without overlap."""
        day_left, day_right = _USER_DAY_COL
        week_left, week_right = _USER_WEEK_COL
        thirty_left, thirty_right = _USER_THIRTY_COL

        self.assertLess(_USER_NAME_X + _USER_NAME_MAX_WIDTH, day_left)
        self.assertLess(day_right, week_left)
        self.assertLess(week_right, thirty_left)
        self.assertLessEqual(thirty_right, 1176)

        fonts = _Fonts(_find_font_path())
        probe = Image.new("RGB", (8, 8))
        draw = ImageDraw.Draw(probe)
        samples = (
            (999999.99, day_left, day_right),
            (8888888.88, week_left, week_right),
            (77777777.77, thirty_left, thirty_right),
        )
        for value, left_x, right_x in samples:
            plain = _format_amount_plain(value)
            text, font = _fit_amount_text(draw, fonts, plain, value, right_x - left_x)
            width = draw.textlength(text, font=font)
            self.assertLessEqual(width, right_x - left_x)
            self.assertTrue(text.startswith("$") or text.startswith("-$"))
            self.assertRegex(text, r"\d+(\.\d{2})?[KMB]?$")

        long_name = "#1  " + ("超长用户名用于验证省略号与金额列互不碰撞" * 4)
        ellipsized = _ellipsize(draw, fonts.body, long_name, _USER_NAME_MAX_WIDTH)
        self.assertLessEqual(draw.textlength(ellipsized, font=fonts.body), _USER_NAME_MAX_WIDTH)

        snapshot = Sub2APIUsageSnapshot(
            users=(
                Sub2APIUserUsage(
                    user_id=1,
                    username="large-amount-user-with-a-very-long-display-name",
                    email="large@example.com",
                    current_day_actual_cost=999999.99,
                    current_week_actual_cost=8888888.88,
                    thirty_day_actual_cost=77777777.77,
                ),
            ),
            users_refreshed_at=datetime(2026, 7, 13, tzinfo=timezone.utc),
        )
        with tempfile.TemporaryDirectory() as directory:
            image_path = render_sub2api_usage_image(snapshot=snapshot, output_dir=Path(directory))
            with Image.open(image_path) as image:
                self.assertEqual(image.width, 1240)
                self.assertEqual(image.format, "PNG")

        self.assertEqual(_format_amount_compact(77777777.77), "$77.78M")
        self.assertEqual(_format_amount_compact(8888888.88), "$8.89M")

    def test_extreme_amounts_fit_fixed_column_min_width(self) -> None:
        """1e100/1e308 fall back to scientific form that never exceeds the narrowest column."""
        min_col_width = min(
            _USER_DAY_COL[1] - _USER_DAY_COL[0],
            _USER_WEEK_COL[1] - _USER_WEEK_COL[0],
            _USER_THIRTY_COL[1] - _USER_THIRTY_COL[0],
        )
        fonts = _Fonts(_find_font_path())
        draw = ImageDraw.Draw(Image.new("RGB", (8, 8)))
        for value in (1e100, 1e308):
            plain = _format_amount_plain(value)
            text, font = _fit_amount_text(draw, fonts, plain, value, min_col_width)
            width = draw.textlength(text, font=font)
            self.assertLessEqual(width, min_col_width, msg=f"value={value} text={text!r} width={width}")
            self.assertTrue(text.startswith("$"))
            self.assertIn("e", text.lower())
            self.assertEqual(text, _format_amount_scientific(value))


if __name__ == "__main__":
    unittest.main()
