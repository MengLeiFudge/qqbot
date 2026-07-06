from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins"))

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
    format_rightcodes_draw_suggestion_message,
    load_rightcodes_config,
    looks_like_rightcodes_draw_feature_request,
    looks_like_rightcodes_draw_invocation,
    looks_like_rightcodes_draw_points_mutation_request,
    looks_like_rightcodes_draw_points_query,
    looks_like_rightcodes_draw_suggestion,
    parse_rightcodes_draw_command,
    should_record_passive_group_points,
)
from astrbot_plugin_qqbot_features.rightcodes_draw_catalog import (
    format_rightcodes_draw_catalog_injection,
    should_inject_rightcodes_draw_catalog,
)
from astrbot_plugin_qqbot_features.rightcodes_draw_rewrite import (
    RightCodesDrawRewriteInput,
    build_rightcodes_draw_rewrite_prompt,
    format_rightcodes_draw_rewrite_missing_context,
    merge_rewritten_draw_request,
    parse_rightcodes_draw_rewrite_response,
    should_rewrite_rightcodes_draw_prompt,
)


class StubDrawHttpClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def post_json(self, url: str, *, headers: dict[str, str], json: dict[str, object], timeout: float):
        self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return {"data": [{"url": "https://example.invalid/draw.png"}]}


class AstrBotRightCodesDrawPluginTest(unittest.TestCase):
    def test_parse_draw_command_matches_migrated_forms(self) -> None:
        request = parse_rightcodes_draw_command("棉花糖生图 nano-banana-pro 一只白猫")

        self.assertIsNotNone(request)
        assert request is not None
        self.assertEqual(request.model, "nano-banana-pro")
        self.assertEqual(request.prompt, "一只白猫")

    def test_draw_invocation_without_prompt_gets_fixed_hint(self) -> None:
        self.assertTrue(looks_like_rightcodes_draw_invocation("棉花生图"))
        self.assertIsNone(parse_rightcodes_draw_command("棉花生图"))
        self.assertIn("生图需要文字提示词", format_rightcodes_draw_missing_prompt_message())

    def test_natural_draw_request_only_gets_command_suggestion(self) -> None:
        self.assertIsNone(parse_rightcodes_draw_command("生成一张白猫图片"))
        self.assertFalse(looks_like_rightcodes_draw_invocation("生成一张白猫图片"))
        self.assertTrue(looks_like_rightcodes_draw_suggestion("生成一张白猫图片"))
        self.assertFalse(looks_like_rightcodes_draw_feature_request("生成一张白猫图片"))
        self.assertTrue(looks_like_rightcodes_draw_feature_request("生成一张白猫图片", is_direct_or_private=True))
        self.assertIn("棉花糖生图 提示词", format_rightcodes_draw_suggestion_message())
        self.assertIn("消耗生图积分", format_rightcodes_draw_suggestion_message())

    def test_plain_chat_does_not_enter_rightcodes_feature_route(self) -> None:
        self.assertFalse(looks_like_rightcodes_draw_feature_request("刚回到"))
        self.assertFalse(looks_like_rightcodes_draw_feature_request("扣1就开"))
        self.assertFalse(looks_like_rightcodes_draw_feature_request("无限手套你也干了吗"))
        self.assertTrue(looks_like_rightcodes_draw_feature_request("棉花糖生图 一只白猫"))
        self.assertTrue(looks_like_rightcodes_draw_feature_request("查询生图积分"))
        self.assertTrue(looks_like_rightcodes_draw_feature_request("生图模型说明"))

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

    def test_group_points_ignore_legacy_runtime_state(self) -> None:
        self.assertTrue(
            should_record_passive_group_points(
                feature_mode=FEATURE_MODE_DUAL,
                legacy_runtime_online=True,
            )
        )
        self.assertTrue(
            should_record_passive_group_points(
                feature_mode=FEATURE_MODE_DUAL,
                legacy_runtime_online=False,
            )
        )
        self.assertTrue(
            should_record_passive_group_points(
                feature_mode=FEATURE_MODE_FULL,
                legacy_runtime_online=True,
            )
        )

    def test_default_data_root_uses_astrbot_plugin_runtime(self) -> None:
        config = load_rightcodes_config({"feature_mode": "dual", "api_key": "test-key"})

        self.assertEqual(config.feature_mode, FEATURE_MODE_FULL)
        self.assertEqual(config.data_root, ROOT / "data" / "astrbot" / "data" / "plugin_data" / "qqbot_features_runtime")
        self.assertEqual(config.api_key, "test-key")
        self.assertEqual(config.point_multiplier, 1000)
        self.assertEqual(config.draw_timeout_seconds, 240.0)

    def test_draw_timeout_message_says_refunded(self) -> None:
        message = format_rightcodes_draw_timeout(240.0)

        self.assertIn("超过 240 秒", message)
        self.assertIn("已退回", message)

    def test_quota_store_keeps_migrated_rules(self) -> None:
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

    def test_draw_prompt_rewrite_only_triggers_for_contextual_prompt(self) -> None:
        plain = RightCodesDrawRequest(prompt="一只白猫，水彩风，干净背景")
        contextual = RightCodesDrawRequest(prompt="仿照上面的图片生成头像")
        short_with_quote = RightCodesDrawRequest(prompt="照这个")

        self.assertFalse(should_rewrite_rightcodes_draw_prompt(plain))
        self.assertTrue(should_rewrite_rightcodes_draw_prompt(contextual))
        self.assertTrue(
            should_rewrite_rightcodes_draw_prompt(
                short_with_quote,
                reply_texts=("一只戴红围巾的白猫",),
            )
        )
        self.assertTrue(
            should_rewrite_rightcodes_draw_prompt(
                plain,
                image_urls=("https://example.invalid/ref.png",),
            )
        )

    def test_draw_prompt_rewrite_prompt_contains_context_and_reference_images(self) -> None:
        prompt = build_rightcodes_draw_rewrite_prompt(
            RightCodesDrawRewriteInput(
                prompt="仿照上面的图片生成",
                model="nano-banana-pro",
                current_text="棉花生图 仿照上面的图片生成",
                reply_texts=("群友：做成复古海报风",),
                image_urls=("https://example.invalid/ref.png",),
            )
        )

        self.assertIn("用户原始生图提示词：仿照上面的图片生成", prompt)
        self.assertIn("被引用消息1：群友：做成复古海报风", prompt)
        self.assertIn("https://example.invalid/ref.png", prompt)

    def test_parse_draw_prompt_rewrite_json_response(self) -> None:
        result = parse_rightcodes_draw_rewrite_response(
            '{"prompt":"参考图中的白猫，改成赛博朋克头像","image_urls":["https://example.invalid/ref.png"]}'
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.prompt, "参考图中的白猫，改成赛博朋克头像")
        self.assertEqual(result.image_urls, ("https://example.invalid/ref.png",))

    def test_parse_draw_prompt_rewrite_error_response_blocks_draw(self) -> None:
        self.assertIsNone(parse_rightcodes_draw_rewrite_response('{"error":"缺少可用参考图"}'))
        self.assertIn("拿不到可用引用", format_rightcodes_draw_rewrite_missing_context())

    def test_merge_rewritten_draw_request_keeps_model_and_updates_prompt(self) -> None:
        original = RightCodesDrawRequest(prompt="仿照上面", model="nano-banana-pro")
        rewrite = parse_rightcodes_draw_rewrite_response(
            '{"prompt":"参考图中的白猫，改成油画头像","image_urls":["https://example.invalid/ref.png"]}'
        )

        self.assertIsNotNone(rewrite)
        assert rewrite is not None
        merged = merge_rewritten_draw_request(original, rewrite)

        self.assertEqual(merged.model, "nano-banana-pro")
        self.assertEqual(merged.prompt, "参考图中的白猫，改成油画头像")
        self.assertEqual(merged.image_urls, ("https://example.invalid/ref.png",))


if __name__ == "__main__":
    unittest.main()
