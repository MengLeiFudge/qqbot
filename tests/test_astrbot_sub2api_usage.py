from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins"))

from astrbot_plugin_qqbot_features.sub2api_usage import (  # noqa: E402
    Sub2APIAccountUsage,
    Sub2APIClient,
    Sub2APIUsageCache,
    Sub2APIUsageSnapshot,
    Sub2APIUsageWindow,
    build_user_usage_ranking,
    format_sub2api_http_error,
    format_sub2api_user_name,
    format_sub2api_usage_alert_message,
    format_sub2api_usage_response,
    format_time_text,
    load_sub2api_config,
    mask_sub2api_email,
    parse_sub2api_group_ids,
    parse_sub2api_usage_command,
    sub2api_calendar_range,
    sub2api_last_24_hours_range,
    update_sub2api_usage_alert_state,
)


class StubSub2APIHttpClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def get_json(self, url: str, *, headers: dict[str, str], timeout: float):
        self.calls.append({"url": url, "headers": headers, "timeout": timeout})
        if "/api/v1/admin/accounts?" in url:
            return {
                "code": 0,
                "data": {
                    "items": [
                        {
                            "id": 88,
                            "name": "Christeena",
                            "platform": "openai",
                            "type": "oauth",
                            "status": "active",
                            "current_concurrency": 2,
                        },
                        {
                            "id": 89,
                            "name": "Backup",
                            "platform": "claude",
                            "type": "session",
                            "status": "active",
                            "current_concurrency": 1,
                        },
                    ],
                    "total": 2,
                },
            }
        if "/api/v1/admin/users?" in url:
            return {
                "code": 0,
                "data": {
                    "items": [
                        {"id": 1, "username": "alice", "email": "alice@example.com"},
                        {"id": 2, "username": "", "email": "bob@example.com"},
                        {"id": 3, "username": "", "email": "zero@example.com"},
                    ],
                    "total": 3,
                },
            }
        if "/api/v1/admin/dashboard/user-breakdown?" in url:
            if "start_date=" not in url or "end_date=" not in url or "timezone=Asia%2FShanghai" not in url:
                raise AssertionError(f"missing date range or timezone: {url}")
            return {
                "code": 0,
                "data": {
                    "users": [
                        {"user_id": 1, "actual_cost": 12.5},
                        {"user_id": 2, "actual_cost": 3.25},
                    ]
                },
            }
        if "/api/v1/admin/accounts/" in url and "/usage?" in url:
            return {
                "code": 0,
                "data": {
                    "source": "active",
                    "updated_at": "2026-07-13T04:00:00Z",
                    "five_hour": {"utilization": 15.4, "remaining_seconds": 7260},
                    "seven_day": {"utilization": 34.8, "remaining_seconds": 604800},
                },
            }
        raise AssertionError(f"unexpected url: {url}")


class PartiallyFailingAccountUsageStub(StubSub2APIHttpClient):
    async def get_json(self, url: str, *, headers: dict[str, str], timeout: float):
        if "/api/v1/admin/accounts/89/usage?" in url:
            self.calls.append({"url": url, "headers": headers, "timeout": timeout})
            raise TimeoutError("backup account usage timed out")
        return await super().get_json(url, headers=headers, timeout=timeout)


class EmptyAccountsStub:
    async def get_json(self, url: str, *, headers: dict[str, str], timeout: float):
        del headers, timeout
        if "/api/v1/admin/accounts?" not in url:
            raise AssertionError(f"unexpected url: {url}")
        return {"code": 0, "data": {"items": [], "total": 0}}


class ServerCappedPageStub:
    async def get_json(self, url: str, *, headers: dict[str, str], timeout: float):
        del headers, timeout
        if "/api/v1/admin/accounts?" not in url:
            raise AssertionError(f"unexpected url: {url}")
        if "page=1" in url:
            start, count = 1, 50
        elif "page=2" in url:
            start, count = 51, 50
        elif "page=3" in url:
            start, count = 101, 1
        else:
            raise AssertionError(f"unexpected page: {url}")
        return {
            "code": 0,
            "data": {
                "items": [{"id": index, "name": f"account-{index}"} for index in range(start, start + count)],
                "total": 101,
            },
        }


class TooManyUsersStub:
    async def get_json(self, url: str, *, headers: dict[str, str], timeout: float):
        del headers, timeout
        if "/api/v1/admin/users?" not in url:
            raise AssertionError(f"unexpected url: {url}")
        return {
            "code": 0,
            "data": {
                "items": [{"id": index, "email": f"user-{index}@example.com"} for index in range(1, 202)],
                "total": 201,
            },
        }


class AstrBotSub2APIUsageTest(unittest.TestCase):
    def test_config_defaults_and_secret_fields(self) -> None:
        config = load_sub2api_config(
            {
                "sub2api_base_url": "https://ai.example.com/",
                "sub2api_admin_api_key": "test-admin-key",
                "sub2api_alert_group_ids": "123, 456，bad,123",
            }
        )

        self.assertEqual(config.base_url, "https://ai.example.com")
        self.assertEqual(config.admin_api_key, "test-admin-key")
        self.assertEqual(config.timeout_seconds, 90.0)
        self.assertEqual(config.refresh_interval_seconds, 300.0)
        self.assertEqual(config.alert_group_ids, ("123", "456"))
        self.assertNotIn("default_account_name", config.__dataclass_fields__)

    def test_parse_only_usage_command(self) -> None:
        self.assertIsNotNone(parse_sub2api_usage_command("用量"))
        self.assertIsNone(parse_sub2api_usage_command("查询"))
        self.assertIsNone(parse_sub2api_usage_command("用量 Pro2"))

    def test_parse_sub2api_alert_group_ids(self) -> None:
        self.assertEqual(parse_sub2api_group_ids("123, 456，789,abc,123"), ("123", "456", "789"))

    def test_calendar_ranges_match_sub2api_webui(self) -> None:
        today = date(2026, 7, 13)
        self.assertEqual(sub2api_last_24_hours_range(today=today), (date(2026, 7, 12), today))
        self.assertEqual(sub2api_calendar_range(days=7, today=today), (date(2026, 7, 7), today))
        self.assertEqual(sub2api_calendar_range(days=14, today=today), (date(2026, 6, 30), today))
        self.assertEqual(sub2api_calendar_range(days=30, today=today), (date(2026, 6, 14), today))

    def test_client_lists_all_accounts_and_forces_each_usage_refresh(self) -> None:
        stub = StubSub2APIHttpClient()
        client = Sub2APIClient(
            base_url="https://ai.example.com",
            admin_api_key="test-admin-key",
            timeout_seconds=9.0,
            http_client=stub,
        )

        usages = asyncio.run(client.get_account_usage(force_refresh=True))

        self.assertEqual([usage.account_id for usage in usages], [88, 89])
        self.assertEqual([usage.name for usage in usages], ["Christeena", "Backup"])
        self.assertEqual(len(stub.calls), 3)
        headers = stub.calls[0]["headers"]
        self.assertIsInstance(headers, dict)
        assert isinstance(headers, dict)
        self.assertEqual(headers["x-api-key"], "test-admin-key")
        self.assertIn("page_size=100", str(stub.calls[0]["url"]))
        self.assertIn("source=active", str(stub.calls[1]["url"]))
        self.assertIn("force=true", str(stub.calls[1]["url"]))
        self.assertIn("source=active", str(stub.calls[2]["url"]))

    def test_client_merges_four_usage_ranges_and_hides_zero_spend_users(self) -> None:
        stub = StubSub2APIHttpClient()
        client = Sub2APIClient(
            base_url="https://ai.example.com",
            admin_api_key="test-admin-key",
            http_client=stub,
        )

        ranking = asyncio.run(client.get_user_usage_ranking())

        self.assertEqual([usage.user_id for usage in ranking], [1, 2])
        self.assertEqual(ranking[0].last_24_hours_actual_cost, 12.5)
        self.assertEqual(ranking[0].seven_day_actual_cost, 12.5)
        self.assertEqual(ranking[1].fourteen_day_actual_cost, 3.25)
        self.assertEqual(ranking[1].thirty_day_actual_cost, 3.25)
        breakdown_calls = [call for call in stub.calls if "/user-breakdown?" in str(call["url"])]
        self.assertEqual(len(breakdown_calls), 4)

    def test_one_account_usage_failure_keeps_other_accounts_in_snapshot(self) -> None:
        client = Sub2APIClient(
            base_url="https://ai.example.com",
            admin_api_key="test-admin-key",
            http_client=PartiallyFailingAccountUsageStub(),
        )

        usages = asyncio.run(client.get_account_usage(force_refresh=True))

        self.assertEqual([usage.account_id for usage in usages], [88, 89])
        self.assertEqual(usages[0].source, "active")
        self.assertIn("backup account usage timed out", usages[1].error)

    def test_empty_account_list_is_a_valid_fresh_result(self) -> None:
        client = Sub2APIClient(
            base_url="https://ai.example.com",
            admin_api_key="test-admin-key",
            http_client=EmptyAccountsStub(),
        )

        self.assertEqual(asyncio.run(client.get_account_usage(force_refresh=True)), [])

    def test_pagination_uses_total_when_server_caps_page_size(self) -> None:
        client = Sub2APIClient(
            base_url="https://ai.example.com",
            admin_api_key="test-admin-key",
            http_client=ServerCappedPageStub(),
        )

        accounts = asyncio.run(client.list_accounts())

        self.assertEqual(len(accounts), 101)
        self.assertEqual(accounts[0]["id"], 1)
        self.assertEqual(accounts[-1]["id"], 101)

    def test_more_than_200_users_fails_instead_of_reporting_unknown_costs_as_zero(self) -> None:
        client = Sub2APIClient(
            base_url="https://ai.example.com",
            admin_api_key="test-admin-key",
            http_client=TooManyUsersStub(),
        )

        with self.assertRaisesRegex(RuntimeError, "最多返回 200 位用户"):
            asyncio.run(client.get_user_usage_ranking())

    def test_user_ranking_uses_four_actual_cost_ranges_and_username_or_masked_email(self) -> None:
        ranking = build_user_usage_ranking(
            [
                {"id": 1, "username": "", "email": "one@example.com"},
                {"id": 2, "username": "two", "email": "two@example.com"},
                {"id": 3, "username": "", "email": "zero@example.com"},
            ],
            [{"user_id": 1, "actual_cost": 5}, {"user_id": 2, "actual_cost": 10}],
            [{"user_id": 1, "actual_cost": 10}, {"user_id": 2, "actual_cost": 10, "cost": 999}],
            [{"user_id": 1, "actual_cost": 20}, {"user_id": 2, "actual_cost": 5}],
            [{"user_id": 1, "actual_cost": 2}, {"user_id": 2, "actual_cost": 5}],
        )

        self.assertEqual([usage.user_id for usage in ranking], [2, 1])
        self.assertEqual(format_sub2api_user_name(ranking[0]), "two")
        self.assertEqual(format_sub2api_user_name(ranking[1]), "o*e@example.com")
        self.assertEqual(mask_sub2api_email("605738729@qq.com"), "605***729@qq.com")
        self.assertEqual(mask_sub2api_email("tursom@foxmail.com"), "tu**om@foxmail.com")
        self.assertEqual(ranking[0].last_24_hours_actual_cost, 10.0)
        self.assertEqual(ranking[0].seven_day_actual_cost, 10.0)

    def test_usage_cache_keeps_one_shared_snapshot(self) -> None:
        cache = Sub2APIUsageCache()
        snapshot = Sub2APIUsageSnapshot(
            accounts=(Sub2APIAccountUsage(account_id=1, name="Main"),),
            accounts_refreshed_at=datetime(2026, 7, 13, tzinfo=timezone.utc),
        )

        cache.set(snapshot)

        self.assertIs(cache.get_latest(), snapshot)

    def test_usage_alert_state_fires_when_crossing_thresholds(self) -> None:
        state: dict[str, set[int]] = {}
        usage_79 = Sub2APIAccountUsage(account_id=1, name="Main", five_hour=Sub2APIUsageWindow(utilization=79.9))
        usage_80 = Sub2APIAccountUsage(account_id=1, name="Main", five_hour=Sub2APIUsageWindow(utilization=80.0))
        usage_92 = Sub2APIAccountUsage(account_id=1, name="Main", five_hour=Sub2APIUsageWindow(utilization=92.0))
        usage_70 = Sub2APIAccountUsage(account_id=1, name="Main", five_hour=Sub2APIUsageWindow(utilization=70.0))

        self.assertEqual(update_sub2api_usage_alert_state([usage_79], state), [])
        self.assertEqual([alert.threshold for alert in update_sub2api_usage_alert_state([usage_80], state)], [80])
        self.assertEqual(update_sub2api_usage_alert_state([usage_80], state), [])
        self.assertEqual([alert.threshold for alert in update_sub2api_usage_alert_state([usage_92], state)], [90])
        self.assertEqual(update_sub2api_usage_alert_state([usage_70], state), [])
        self.assertEqual([alert.threshold for alert in update_sub2api_usage_alert_state([usage_80], state)], [80])

    def test_usage_alert_message_contains_threshold_and_window(self) -> None:
        usage = Sub2APIAccountUsage(
            account_id=1,
            name="Main",
            five_hour=Sub2APIUsageWindow(utilization=95.1),
            updated_at="2026-06-12T12:00:00Z",
        )
        alert = update_sub2api_usage_alert_state([usage], {})[0]

        message = format_sub2api_usage_alert_message(alert)

        self.assertIn("Sub2API 5h 用量提醒：Main 已达到 95%", message)
        self.assertIn("当前 5h：95%", message)

    def test_text_fallback_masks_email_and_reports_stale_errors(self) -> None:
        snapshot = Sub2APIUsageSnapshot(
            accounts=(
                Sub2APIAccountUsage(
                    account_id=1,
                    name="Main",
                    last_used_at="2026-07-15T02:34:16.710391+08:00",
                    updated_at="2026-07-15T02:35:00.831240125+08:00",
                ),
            ),
            users=tuple(build_user_usage_ranking(
                [{"id": 2, "username": "", "email": "bob@example.com"}],
                [{"user_id": 2, "actual_cost": 1}],
                [],
                [],
                [],
            )),
            accounts_error="HTTP 502",
            users_error="timeout",
        )

        message = format_sub2api_usage_response(snapshot)

        self.assertIn("账号刷新失败：HTTP 502", message)
        self.assertIn("用户刷新失败：timeout", message)
        self.assertIn("用户消费（24h / 7d / 14d / 30d）：", message)
        self.assertNotIn("用户实际消费", message)
        self.assertIn("最近使用：2026-07-15 02:34", message)
        self.assertIn("更新时间：2026-07-15 02:35", message)
        self.assertIn("b*b@example.com", message)
        self.assertNotIn("test-admin-key", message)

    def test_format_time_text_uses_sub2api_timezone_and_accepts_nanoseconds(self) -> None:
        self.assertEqual(format_time_text("2026-07-15T02:35:00.831240125+08:00"), "2026-07-15 02:35")
        self.assertEqual(format_time_text("2026-07-14T18:35:00Z"), "2026-07-15 02:35")

    def test_cloudflare_1010_error_message_is_actionable(self) -> None:
        message = format_sub2api_http_error(
            403,
            '{"title":"Error 1010: Access denied","detail":"The site owner has blocked access based on your browser signature."}',
        )

        self.assertIn("Cloudflare", message)
        self.assertIn("Error 1010", message)
        self.assertIn("尚未进入 Admin API Key 鉴权", message)


if __name__ == "__main__":
    unittest.main()
