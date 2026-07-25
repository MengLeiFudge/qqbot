from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins"))

from astrbot_plugin_qqbot_features.sub2api_usage import (  # noqa: E402
    SUB2API_TIMEZONE,
    Sub2APIAccountSevenDayRanking,
    Sub2APIAccountUsage,
    Sub2APIAccountUserUsage,
    Sub2APIClient,
    Sub2APIUsageCache,
    Sub2APIUsageSnapshot,
    Sub2APIUserUsage,
    Sub2APIUsageWindow,
    build_account_user_ranking,
    build_rolling_user_costs,
    build_user_usage_ranking,
    format_sub2api_http_error,
    format_sub2api_user_name,
    format_sub2api_usage_alert_message,
    format_sub2api_usage_response,
    format_time_text,
    find_account_seven_day_ranking,
    load_sub2api_config,
    mask_sub2api_email,
    parse_sub2api_group_ids,
    parse_sub2api_usage_command,
    retain_failed_account_ranking,
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
            query = parse_qs(urlparse(url).query)
            account_id = int(query["account_id"][0]) if "account_id" in query else None
            if account_id is not None:
                actual_costs = {
                    88: {1: 20.0, 2: 5.0},
                    89: {1: 2.0, 2: 3.0},
                }.get(account_id, {})
                return {
                    "code": 0,
                    "data": {
                        "users": [
                            {"user_id": user_id, "actual_cost": actual_cost}
                            for user_id, actual_cost in actual_costs.items()
                        ]
                    },
                }
            raise AssertionError(f"ordinary rolling windows must not call user-breakdown: {url}")
        if "/api/v1/admin/accounts/" in url and "/usage?" in url:
            return {
                "code": 0,
                "data": {
                    "source": "active",
                    "updated_at": "2026-07-13T04:00:00Z",
                    "five_hour": {"utilization": 15.4, "remaining_seconds": 7260},
                    "seven_day": {
                        "utilization": 34.8,
                        "resets_at": "2026-07-20T12:17:00+08:00",
                        "remaining_seconds": 604800,
                    },
                },
            }
        if "/api/v1/admin/dashboard/snapshot-v2?" in url:
            query = parse_qs(urlparse(url).query)
            account_id = int(query["account_id"][0]) if "account_id" in query else None
            if account_id is not None:
                hourly_costs = {
                    (88, 1): 1.0,
                    (88, 2): 0.5,
                    (89, 1): 0.5,
                    (89, 2): 1.0,
                }
                trend = [
                    {"date": "2026-07-13 12:00", "user_id": 1, "actual_cost": 999.0},
                    {"date": "2026-07-13 13:00", "user_id": 1, "actual_cost": hourly_costs.get((account_id, 1), 0.0)},
                    {"date": "2026-07-13 13:00", "user_id": 2, "actual_cost": hourly_costs.get((account_id, 2), 0.0)},
                ]
            else:
                start_date = query["start_date"][0]
                if query["granularity"] == ["day"]:
                    trend = [
                        {"date": "2026-06-18", "user_id": 1, "actual_cost": 160.0},
                        {"date": "2026-06-18", "user_id": 2, "actual_cost": 16.0},
                        {"date": "2026-07-04", "user_id": 1, "actual_cost": 70.0},
                        {"date": "2026-07-04", "user_id": 2, "actual_cost": 7.0},
                        {"date": "2026-07-11", "user_id": 1, "actual_cost": 60.0},
                        {"date": "2026-07-11", "user_id": 2, "actual_cost": 6.0},
                        {"date": "2026-07-17", "user_id": 1, "actual_cost": 10.0},
                        {"date": "2026-07-17", "user_id": 2, "actual_cost": 1.0},
                    ]
                else:
                    hourly_costs = {
                        "2026-07-16": {1: 1.0, 2: 0.1},
                        "2026-07-10": {1: 2.0, 2: 0.2},
                        "2026-07-03": {1: 3.0, 2: 0.3},
                        "2026-06-17": {1: 4.0, 2: 0.4},
                    }.get(start_date, {})
                    trend = [
                        {"date": f"{start_date} 12:00", "user_id": 1, "actual_cost": 999.0},
                        *(
                            {"date": f"{start_date} 13:00", "user_id": user_id, "actual_cost": actual_cost}
                            for user_id, actual_cost in hourly_costs.items()
                        ),
                    ]
            return {"code": 0, "data": {"users_trend": trend}}
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
    """Verify Sub2API cache, aggregation, formatting, and alert contracts."""

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

    def test_client_merges_four_rolling_windows_and_hides_zero_spend_users(self) -> None:
        stub = StubSub2APIHttpClient()
        client = Sub2APIClient(
            base_url="https://ai.example.com",
            admin_api_key="test-admin-key",
            http_client=stub,
        )

        ranking = asyncio.run(
            client.get_user_usage_ranking(
                now=datetime(2026, 7, 17, 4, 37, tzinfo=timezone.utc),
            )
        )

        self.assertEqual([usage.user_id for usage in ranking], [1, 2])
        self.assertEqual(ranking[0].last_24_hours_actual_cost, 11.0)
        self.assertEqual(ranking[0].seven_day_actual_cost, 72.0)
        self.assertEqual(ranking[0].fourteen_day_actual_cost, 143.0)
        self.assertEqual(ranking[0].thirty_day_actual_cost, 304.0)
        self.assertAlmostEqual(ranking[1].last_24_hours_actual_cost, 1.1)
        self.assertAlmostEqual(ranking[1].seven_day_actual_cost, 7.2)
        self.assertAlmostEqual(ranking[1].fourteen_day_actual_cost, 14.3)
        self.assertAlmostEqual(ranking[1].thirty_day_actual_cost, 30.4)

        hourly_calls = [
            call for call in stub.calls
            if "/dashboard/snapshot-v2?" in str(call["url"])
            and "granularity=hour" in str(call["url"])
            and "account_id=" not in str(call["url"])
        ]
        self.assertEqual(len(hourly_calls), 4)
        self.assertEqual(
            {
                parse_qs(urlparse(str(call["url"])).query)["start_date"][0]
                for call in hourly_calls
            },
            {"2026-07-16", "2026-07-10", "2026-07-03", "2026-06-17"},
        )
        for call in hourly_calls:
            query = parse_qs(urlparse(str(call["url"])).query)
            self.assertEqual(query["start_date"], query["end_date"])
            self.assertEqual(query["granularity"], ["hour"])
            self.assertEqual(query["include_users_trend"], ["true"])

        daily_calls = [
            call for call in stub.calls
            if "/dashboard/snapshot-v2?" in str(call["url"])
            and "granularity=day" in str(call["url"])
            and "account_id=" not in str(call["url"])
        ]
        self.assertEqual(len(daily_calls), 1)
        daily_query = parse_qs(urlparse(str(daily_calls[0]["url"])).query)
        self.assertEqual(daily_query["start_date"], ["2026-06-18"])
        self.assertEqual(daily_query["end_date"], ["2026-07-17"])
        self.assertEqual(daily_query["include_users_trend"], ["true"])
        self.assertLess(
            max(stub.calls.index(call) for call in hourly_calls),
            stub.calls.index(daily_calls[0]),
        )
        self.assertFalse(any(
            "/user-breakdown?" in str(call["url"])
            and "account_id=" not in str(call["url"])
            for call in stub.calls
        ))

    def test_rolling_window_includes_an_exact_start_hour(self) -> None:
        client = Sub2APIClient(
            base_url="https://ai.example.com",
            admin_api_key="test-admin-key",
            http_client=StubSub2APIHttpClient(),
        )

        window_started_at = datetime(2026, 7, 16, 12, 0, tzinfo=SUB2API_TIMEZONE)
        end_time = datetime(2026, 7, 17, 12, 0, tzinfo=SUB2API_TIMEZONE)
        hourly_costs = asyncio.run(
            client.fetch_hourly_user_costs(
                date_value=window_started_at.date(),
                start_hour=window_started_at,
                end_time=end_time,
            )
        )
        costs = build_rolling_user_costs(
            window_started_at=window_started_at,
            end_time=end_time,
            hourly_costs=hourly_costs,
            daily_costs_by_date={
                end_time.date(): {1: 10.0, 2: 1.0},
            },
        )

        self.assertEqual(costs[1], 1010.0)
        self.assertAlmostEqual(costs[2], 1.1)

    def test_client_builds_separate_rankings_for_each_account(self) -> None:
        """Each account ID produces its own ordered actual-cost rows and requests."""
        stub = StubSub2APIHttpClient()
        client = Sub2APIClient(
            base_url="https://ai.example.com",
            admin_api_key="test-admin-key",
            http_client=stub,
        )
        accounts = tuple(asyncio.run(client.get_account_usage(force_refresh=True)))
        users = (
            Sub2APIUserUsage(user_id=1, username="alice"),
            Sub2APIUserUsage(user_id=2, username="bob"),
        )
        now = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)

        rankings = {
            account.account_id: asyncio.run(
                client.get_account_seven_day_ranking(account, users, now=now)
            )
            for account in accounts
        }

        self.assertEqual(
            [(usage.user_id, usage.actual_cost) for usage in rankings[88]],
            [(1, 21.0), (2, 5.5)],
        )
        self.assertEqual(
            [(usage.user_id, usage.actual_cost) for usage in rankings[89]],
            [(2, 4.0), (1, 2.5)],
        )
        hourly_calls = [
            call for call in stub.calls
            if "/api/v1/admin/dashboard/snapshot-v2?" in str(call["url"])
            and "account_id=" in str(call["url"])
        ]
        self.assertEqual(len(hourly_calls), 2)
        self.assertEqual(
            {
                parse_qs(urlparse(str(call["url"])).query)["account_id"][0]
                for call in hourly_calls
            },
            {"88", "89"},
        )
        for call in hourly_calls:
            query = parse_qs(urlparse(str(call["url"])).query)
            self.assertEqual(query["start_date"], ["2026-07-13"])
            self.assertEqual(query["end_date"], ["2026-07-13"])
            self.assertEqual(query["granularity"], ["hour"])
            self.assertEqual(query["include_users_trend"], ["true"])
            self.assertNotIn("user_id", query)
        full_day_calls = [
            call
            for call in stub.calls
            if "/api/v1/admin/dashboard/user-breakdown?" in str(call["url"])
            and "account_id=" in str(call["url"])
        ]
        self.assertEqual(len(full_day_calls), 2)
        for call in full_day_calls:
            query = parse_qs(urlparse(str(call["url"])).query)
            self.assertEqual(query["start_date"], ["2026-07-14"])
            self.assertEqual(query["end_date"], ["2026-07-17"])

    def test_account_cycle_includes_an_exact_start_hour(self) -> None:
        """An exact reset-derived start hour is included rather than rounded away."""
        client = Sub2APIClient(
            base_url="https://ai.example.com",
            admin_api_key="test-admin-key",
            http_client=StubSub2APIHttpClient(),
        )
        account = Sub2APIAccountUsage(
            account_id=88,
            name="Main",
            seven_day=Sub2APIUsageWindow(resets_at="2026-07-20T12:00:00+08:00"),
        )
        users = (
            Sub2APIUserUsage(user_id=1),
            Sub2APIUserUsage(user_id=2),
        )

        ranking = asyncio.run(
            client.get_account_seven_day_ranking(
                account,
                users,
                now=datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc),
            )
        )

        self.assertEqual(ranking[0].user_id, 1)
        self.assertEqual(ranking[0].actual_cost, 1020.0)
        self.assertEqual(ranking[1].actual_cost, 5.5)

    def test_account_ranking_filters_zero_costs_and_uses_stable_ties(self) -> None:
        """Account rankings contain every positive user with deterministic ties."""
        users = (
            Sub2APIUserUsage(user_id=3, username="three"),
            Sub2APIUserUsage(user_id=2, username="zero"),
            Sub2APIUserUsage(user_id=1, username="one"),
        )

        ranking = build_account_user_ranking(users, {1: 5.0, 2: 0.0, 3: 5.0})

        self.assertEqual([usage.user_id for usage in ranking], [1, 3])

    def test_failed_account_keeps_only_its_own_cached_ranking(self) -> None:
        """A failed refresh cannot borrow rows from another stable account ID."""
        refreshed_at = datetime(2026, 7, 15, tzinfo=timezone.utc)
        previous = Sub2APIAccountSevenDayRanking(
            account_id=88,
            users=(Sub2APIAccountUserUsage(user_id=1, actual_cost=12.5),),
            refreshed_at=refreshed_at,
        )

        failed = retain_failed_account_ranking(88, previous, "stats timeout")
        new_account_failed = retain_failed_account_ranking(89, None, "missing reset")
        mismatched_cache = retain_failed_account_ranking(89, previous, "renamed account")

        self.assertEqual(failed.users, previous.users)
        self.assertEqual(failed.refreshed_at, refreshed_at)
        self.assertEqual(failed.error, "stats timeout")
        self.assertEqual(new_account_failed.users, ())
        self.assertIsNone(new_account_failed.refreshed_at)
        self.assertEqual(mismatched_cache.users, ())
        self.assertIsNone(mismatched_cache.refreshed_at)
        self.assertIs(find_account_seven_day_ranking((failed,), 88), failed)
        self.assertIsNone(find_account_seven_day_ranking((failed,), 89))

    def test_expired_account_reset_time_fails_instead_of_overcounting_old_window(self) -> None:
        """An expired cycle boundary fails instead of reporting the previous cycle."""
        client = Sub2APIClient(
            base_url="https://ai.example.com",
            admin_api_key="test-admin-key",
            http_client=StubSub2APIHttpClient(),
        )
        accounts = (
            Sub2APIAccountUsage(
                account_id=88,
                name="Main",
                seven_day=Sub2APIUsageWindow(resets_at="2026-07-17T11:59:00+00:00"),
            ),
        )
        users = (Sub2APIUserUsage(user_id=1),)

        with self.assertRaisesRegex(RuntimeError, "7d 重置时间已过期"):
            asyncio.run(
                client.get_account_seven_day_ranking(
                    accounts[0],
                    users,
                    now=datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc),
                )
            )

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

    def test_user_ranking_uses_four_actual_cost_windows_and_username_or_masked_email(self) -> None:
        ranking = build_user_usage_ranking(
            [
                {"id": 1, "username": "", "email": "one@example.com"},
                {"id": 2, "username": "two", "email": "two@example.com"},
                {"id": 3, "username": "", "email": "zero@example.com"},
            ],
            {1: 5.0, 2: 10.0},
            {1: 10.0, 2: 10.0},
            {1: 20.0, 2: 5.0},
            {1: 2.0, 2: 5.0},
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

    def test_text_fallback_masks_email_and_reports_per_account_stale_errors(self) -> None:
        """Text fallback mirrors per-account stale state and the global four-window table."""
        snapshot = Sub2APIUsageSnapshot(
            accounts=(
                Sub2APIAccountUsage(
                    account_id=1,
                    name="Main",
                    last_used_at="2026-07-15T02:34:16.710391+08:00",
                    updated_at="2026-07-15T02:35:00.831240125+08:00",
                ),
            ),
            account_seven_day_rankings=(
                Sub2APIAccountSevenDayRanking(
                    account_id=1,
                    users=(
                        Sub2APIAccountUserUsage(
                            user_id=2,
                            email="bob@example.com",
                            actual_cost=0.75,
                        ),
                    ),
                    refreshed_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
                    error="stats timeout",
                ),
            ),
            users=tuple(build_user_usage_ranking(
                [{"id": 2, "username": "", "email": "bob@example.com"}],
                {2: 1.0},
                {},
                {},
                {},
            )),
            accounts_error="HTTP 502",
            users_error="timeout",
        )
        message = format_sub2api_usage_response(snapshot)

        self.assertIn("账号刷新失败：HTTP 502", message)
        self.assertIn("Main 当前账号7d周期消费榜：", message)
        self.assertIn("刷新失败，已保留上次成功缓存：stats timeout", message)
        self.assertIn("b*b@example.com：$0.75", message)
        self.assertIn("用户刷新失败：timeout", message)
        self.assertIn("全账号滚动消费榜（24h / 7d / 14d / 30d）：", message)
        self.assertIn("b*b@example.com：24h $1.00", message)
        self.assertNotIn("用户消费（账号7d", message)
        self.assertIn("最近使用：2026-07-15 02:34", message)
        self.assertIn("更新时间：2026-07-15 02:35", message)
        self.assertNotIn("test-admin-key", message)

    def test_text_fallback_does_not_claim_stale_cache_for_first_failure(self) -> None:
        """A first failed account refresh reports no data instead of claiming a retained cache."""
        snapshot = Sub2APIUsageSnapshot(
            accounts=(Sub2APIAccountUsage(account_id=1, name="New"),),
            account_seven_day_rankings=(
                Sub2APIAccountSevenDayRanking(
                    account_id=1,
                    error="missing reset",
                ),
            ),
        )

        message = format_sub2api_usage_response(snapshot)

        self.assertIn("刷新：暂无成功数据", message)
        self.assertIn("刷新失败：missing reset", message)
        self.assertNotIn("已保留上次成功缓存", message)

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
