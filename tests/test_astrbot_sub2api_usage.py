from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "astrbot-local-plugins"))

from astrbot_plugin_qqbot_features.sub2api_usage import (  # noqa: E402
    Sub2APIClient,
    Sub2APIAccountUsage,
    Sub2APIUsageWindow,
    Sub2APIUsageCache,
    format_sub2api_usage_alert_message,
    format_sub2api_http_error,
    format_sub2api_usage_message,
    format_sub2api_usage_response,
    load_sub2api_config,
    parse_sub2api_usage_command,
    parse_sub2api_group_ids,
    update_sub2api_usage_alert_state,
)


class StubSub2APIHttpClient:
    def __init__(self, *, multiple_accounts: bool = False) -> None:
        self.calls: list[dict[str, object]] = []
        self.multiple_accounts = multiple_accounts

    async def get_json(self, url: str, *, headers: dict[str, str], timeout: float):
        self.calls.append({"url": url, "headers": headers, "timeout": timeout})
        if "/api/v1/admin/accounts?" in url:
            items = [
                {
                    "id": 88,
                    "name": "Pro",
                    "platform": "openai",
                    "type": "oauth",
                    "status": "active",
                    "last_used_at": "2026-06-12T03:00:00Z",
                    "current_concurrency": 2,
                }
            ]
            if self.multiple_accounts:
                items.append(
                    {
                        "id": 89,
                        "name": "pro",
                        "platform": "claude",
                        "type": "session",
                        "status": "active",
                        "last_used_at": "2026-06-12T03:30:00Z",
                        "current_concurrency": 1,
                    }
                )
            return {
                "code": 0,
                "message": "success",
                "data": {"items": items},
            }
        if "/api/v1/admin/accounts/88/usage?" in url or "/api/v1/admin/accounts/89/usage?" in url:
            is_backup = "/api/v1/admin/accounts/89/usage?" in url
            return {
                "code": 0,
                "message": "success",
                "data": {
                    "source": "active",
                    "updated_at": "2026-06-12T04:30:00Z" if is_backup else "2026-06-12T04:00:00Z",
                    "five_hour": {
                        "utilization": 8.4 if is_backup else 15.4,
                        "remaining_seconds": 3600 if is_backup else 7260,
                        "window_stats": {"requests": 3, "tokens": 6789, "cost": 0.12} if is_backup else {"requests": 7, "tokens": 12345, "cost": 0.42},
                    },
                    "seven_day": {
                        "utilization": 21.2 if is_backup else 34.8,
                        "remaining_seconds": 604800,
                        "window_stats": {"requests": 11, "tokens": 22222, "cost": 0.88} if is_backup else {"requests": 30, "tokens": 98765, "cost": 3.21},
                    },
                },
            }
        raise AssertionError(f"unexpected url: {url}")


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
        self.assertEqual(config.default_account_name, "Pro")
        self.assertEqual(config.timeout_seconds, 90.0)
        self.assertEqual(config.refresh_interval_seconds, 300.0)
        self.assertEqual(config.alert_group_ids, ("123", "456"))

    def test_parse_sub2api_alert_group_ids(self) -> None:
        self.assertEqual(parse_sub2api_group_ids("123, 456，789,abc,123"), ("123", "456", "789"))
        self.assertEqual(parse_sub2api_group_ids(["100", "", "x", 200]), ("100", "200"))

    def test_parse_only_usage_command(self) -> None:
        query = parse_sub2api_usage_command("用量")

        self.assertIsNotNone(query)
        assert query is not None
        self.assertEqual(query.account_name, "Pro")
        self.assertIsNone(parse_sub2api_usage_command("pro"))
        self.assertIsNone(parse_sub2api_usage_command("查询"))
        self.assertIsNone(parse_sub2api_usage_command("用量 Pro2"))

    def test_client_uses_admin_api_key_and_active_force_usage(self) -> None:
        stub = StubSub2APIHttpClient()
        client = Sub2APIClient(
            base_url="https://ai.example.com",
            admin_api_key="test-admin-key",
            timeout_seconds=9.0,
            http_client=stub,
        )

        usages = asyncio.run(client.get_account_usage("Pro", force_refresh=True))

        self.assertEqual(len(usages), 1)
        self.assertEqual(usages[0].account_id, 88)
        self.assertEqual(usages[0].name, "Pro")
        self.assertEqual(usages[0].source, "active")
        self.assertEqual(len(stub.calls), 2)
        headers = stub.calls[0]["headers"]
        self.assertIsInstance(headers, dict)
        assert isinstance(headers, dict)
        self.assertEqual(headers["x-api-key"], "test-admin-key")
        self.assertIn("application/json", headers["Accept"])
        self.assertIn("Mozilla/5.0", headers["User-Agent"])
        self.assertIn("zh-CN", headers["Accept-Language"])
        self.assertIn("search=Pro", str(stub.calls[0]["url"]))
        self.assertIn("source=active", str(stub.calls[1]["url"]))
        self.assertIn("force=true", str(stub.calls[1]["url"]))

    def test_cloudflare_1010_error_message_is_actionable(self) -> None:
        message = format_sub2api_http_error(
            403,
            '{"title":"Error 1010: Access denied","detail":"The site owner has blocked access based on your browser\'s signature."}',
        )

        self.assertIn("Cloudflare", message)
        self.assertIn("Error 1010", message)
        self.assertIn("尚未进入 Admin API Key 鉴权", message)
        self.assertNotIn("test-admin-key", message)

    def test_client_queries_every_matching_account(self) -> None:
        stub = StubSub2APIHttpClient(multiple_accounts=True)
        client = Sub2APIClient(
            base_url="https://ai.example.com",
            admin_api_key="test-admin-key",
            http_client=stub,
        )

        usages = asyncio.run(client.get_account_usage("Pro", force_refresh=True))

        self.assertEqual([usage.account_id for usage in usages], [88, 89])
        self.assertEqual(len(stub.calls), 3)
        self.assertIn("/api/v1/admin/accounts/88/usage?", str(stub.calls[1]["url"]))
        self.assertIn("/api/v1/admin/accounts/89/usage?", str(stub.calls[2]["url"]))

    def test_usage_cache_is_shared_by_sub2api_account_name(self) -> None:
        cache = Sub2APIUsageCache(ttl_seconds=60)
        stub = StubSub2APIHttpClient()
        client = Sub2APIClient(
            base_url="https://ai.example.com",
            admin_api_key="test-admin-key",
            http_client=stub,
        )
        usages = asyncio.run(client.get_account_usage("Pro", force_refresh=True))
        cache.set("Pro", usages, now=10.0)

        self.assertIs(cache.get("pro", now=69.0), usages)
        self.assertIsNone(cache.get("pro", now=70.0))
        self.assertIs(cache.get_latest("pro"), usages)

    def test_usage_alert_state_fires_when_crossing_thresholds(self) -> None:
        state: dict[str, set[int]] = {}
        usage_79 = Sub2APIAccountUsage(account_id=1, name="Pro", five_hour=Sub2APIUsageWindow(utilization=79.9))
        usage_80 = Sub2APIAccountUsage(account_id=1, name="Pro", five_hour=Sub2APIUsageWindow(utilization=80.0))
        usage_92 = Sub2APIAccountUsage(account_id=1, name="Pro", five_hour=Sub2APIUsageWindow(utilization=92.0))
        usage_70 = Sub2APIAccountUsage(account_id=1, name="Pro", five_hour=Sub2APIUsageWindow(utilization=70.0))

        self.assertEqual(update_sub2api_usage_alert_state([usage_79], state), [])
        alerts = update_sub2api_usage_alert_state([usage_80], state)
        self.assertEqual([alert.threshold for alert in alerts], [80])
        self.assertEqual(update_sub2api_usage_alert_state([usage_80], state), [])
        alerts = update_sub2api_usage_alert_state([usage_92], state)
        self.assertEqual([alert.threshold for alert in alerts], [90])
        self.assertEqual(update_sub2api_usage_alert_state([usage_70], state), [])
        alerts = update_sub2api_usage_alert_state([usage_80], state)
        self.assertEqual([alert.threshold for alert in alerts], [80])

    def test_usage_alert_message_contains_threshold_and_window(self) -> None:
        usage = Sub2APIAccountUsage(
            account_id=1,
            name="Pro",
            five_hour=Sub2APIUsageWindow(utilization=95.1),
            updated_at="2026-06-12T12:00:00Z",
        )
        alert = update_sub2api_usage_alert_state([usage], {})[0]

        message = format_sub2api_usage_alert_message(alert)

        self.assertIn("Sub2API 5h 用量提醒：Pro 已达到 95%", message)
        self.assertIn("当前 5h：95%", message)
        self.assertIn("更新时间：", message)

    def test_format_usage_message_hides_secret_values(self) -> None:
        stub = StubSub2APIHttpClient()
        client = Sub2APIClient(
            base_url="https://ai.example.com",
            admin_api_key="test-admin-key",
            http_client=stub,
        )
        usages = asyncio.run(client.get_account_usage("Pro"))

        message = format_sub2api_usage_message(usages[0])

        self.assertIn("Sub2API 用量：Pro", message)
        self.assertIn("状态：openai / oauth / active / 并发 2", message)
        self.assertIn("5h：15%", message)
        self.assertIn("7d：35%", message)
        self.assertIn("12.3K tokens", message)
        self.assertNotIn("test-admin-key", message)

    def test_format_usage_response_lists_multiple_accounts(self) -> None:
        stub = StubSub2APIHttpClient(multiple_accounts=True)
        client = Sub2APIClient(
            base_url="https://ai.example.com",
            admin_api_key="test-admin-key",
            http_client=stub,
        )
        usages = asyncio.run(client.get_account_usage("Pro", force_refresh=True))

        message = format_sub2api_usage_response(usages, "Pro")

        self.assertIn("Sub2API 用量：Pro，共 2 个账号", message)
        self.assertIn("1. Pro", message)
        self.assertIn("2. pro", message)
        self.assertIn("状态：claude / session / active / 并发 1", message)
        self.assertIn("6.8K tokens", message)


if __name__ == "__main__":
    unittest.main()
