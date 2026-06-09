from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "astrbot-local-plugins"))

from astrbot_plugin_qqbot_features.rightcodes_draw_logic import (
    FEATURE_MODE_DUAL,
    FEATURE_MODE_FULL,
    RightCodesDrawClient,
    RightCodesDrawQuotaStore,
    RightCodesDrawRequest,
    format_draw_start_message,
    format_rightcodes_draw_timeout,
    format_rightcodes_draw_missing_prompt_message,
    format_rightcodes_draw_points_status,
    load_rightcodes_config,
    looks_like_rightcodes_draw_invocation,
    looks_like_rightcodes_draw_points_mutation_request,
    looks_like_rightcodes_draw_points_query,
    parse_rightcodes_draw_command,
    should_record_passive_group_points,
)
from astrbot_plugin_qqbot_features.rightcodes_draw_catalog import (
    format_rightcodes_draw_catalog_injection,
    should_inject_rightcodes_draw_catalog,
)


class StubDrawHttpClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def post_json(self, url: str, *, headers: dict[str, str], json: dict[str, object], timeout: float):
        self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return {"data": [{"url": "https://example.invalid/draw.png"}]}


class AstrBotRightCodesDrawPluginTest(unittest.TestCase):
    def test_parse_draw_command_matches_bot1_forms(self) -> None:
        request = parse_rightcodes_draw_command("棉花糖生图 nano-banana-pro 一只白猫")

        self.assertIsNotNone(request)
        assert request is not None
        self.assertEqual(request.model, "nano-banana-pro")
        self.assertEqual(request.prompt, "一只白猫")

    def test_draw_invocation_without_prompt_gets_fixed_hint(self) -> None:
        self.assertTrue(looks_like_rightcodes_draw_invocation("棉花生图"))
        self.assertIsNone(parse_rightcodes_draw_command("棉花生图"))
        self.assertIn("生图需要文字提示词", format_rightcodes_draw_missing_prompt_message())

    def test_rightcodes_draw_catalog_mentions_size_body(self) -> None:
        self.assertTrue(should_inject_rightcodes_draw_catalog("我要 1024x1024 body 里写什么"))
        injection = format_rightcodes_draw_catalog_injection("我要 1024x1024 body 里写什么")
        self.assertIn('"size": "1024x1024"', injection)
        self.assertIn("/v1/images/generations", injection)
        self.assertIn("stream=true", injection)

    def test_points_query_and_mutation_detection(self) -> None:
        self.assertTrue(looks_like_rightcodes_draw_points_query("查询生图积分"))
        self.assertTrue(looks_like_rightcodes_draw_points_query("balance"))
        self.assertTrue(looks_like_rightcodes_draw_points_mutation_request("给我加100积分"))
        self.assertFalse(looks_like_rightcodes_draw_points_query("给我加100积分"))

    def test_dual_mode_does_not_duplicate_bot1_group_points(self) -> None:
        self.assertFalse(
            should_record_passive_group_points(
                feature_mode=FEATURE_MODE_DUAL,
                nonebot2_online=True,
            )
        )
        self.assertTrue(
            should_record_passive_group_points(
                feature_mode=FEATURE_MODE_DUAL,
                nonebot2_online=False,
            )
        )
        self.assertTrue(
            should_record_passive_group_points(
                feature_mode=FEATURE_MODE_FULL,
                nonebot2_online=True,
            )
        )

    def test_default_data_root_reuses_nonebot2_runtime(self) -> None:
        config = load_rightcodes_config({"feature_mode": "full"})

        self.assertEqual(config.feature_mode, FEATURE_MODE_FULL)
        self.assertEqual(config.data_root, ROOT / "data" / "nonebot2" / "run")
        self.assertEqual(config.point_multiplier, 1000)
        self.assertEqual(config.draw_timeout_seconds, 240.0)

    def test_draw_timeout_message_says_refunded(self) -> None:
        message = format_rightcodes_draw_timeout(240.0)

        self.assertIn("超过 240 秒", message)
        self.assertIn("已退回", message)

    def test_quota_store_keeps_bot1_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RightCodesDrawQuotaStore(Path(temp_dir))
            store.record_group_message("10001", amount=45)
            free = store.reserve("10001", model="gpt-image-2", date_key="2026-06-08")
            paid = store.reserve("10001", model="gpt-image-2", date_key="2026-06-08")

            self.assertTrue(free.allowed)
            self.assertTrue(free.used_free)
            self.assertEqual(paid.cost_points, 40)
            self.assertEqual(paid.balance_after, 5)
            self.assertIn("今天第 1 张免费", format_draw_start_message(free))
            self.assertIn("当前生图积分：5", format_rightcodes_draw_points_status(store.get_balance("10001", date_key="2026-06-08")))

    def test_refund_restores_paid_points_and_daily_free_use(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RightCodesDrawQuotaStore(Path(temp_dir))
            free = store.reserve("10001", model="gpt-image-2", date_key="2026-06-08")
            store.refund(free)
            free_again = store.reserve("10001", model="gpt-image-2", date_key="2026-06-08")

            self.assertTrue(free_again.allowed)
            self.assertTrue(free_again.used_free)

            store.record_group_message("10001", amount=40)
            paid = store.reserve("10001", model="gpt-image-2", date_key="2026-06-08")
            store.refund(paid)
            balance = store.get_balance("10001", date_key="2026-06-08")

            self.assertEqual(balance.points, 40)

    def test_draw_client_uses_rightcodes_image_generation_payload(self) -> None:
        stub = StubDrawHttpClient()
        client = RightCodesDrawClient(api_key="test-key", http_client=stub)

        result = asyncio.run(
            client.draw(
                RightCodesDrawRequest(
                    prompt="一只白猫",
                    model="nano-banana-pro",
                    image_urls=("https://example.invalid/ref.png",),
                )
            )
        )

        self.assertEqual(result.image_url, "https://example.invalid/draw.png")
        self.assertEqual(len(stub.calls), 1)
        call = stub.calls[0]
        self.assertEqual(call["url"], "https://www.right.codes/draw/v1/images/generations")
        self.assertEqual(call["headers"], {"Authorization": "Bearer test-key", "Content-Type": "application/json"})
        self.assertEqual(
            call["json"],
            {
                "model": "nano-banana-pro",
                "prompt": "一只白猫",
                "image": ["https://example.invalid/ref.png"],
                "size": "1024x1024",
                "response_format": "url",
            },
        )


if __name__ == "__main__":
    unittest.main()
