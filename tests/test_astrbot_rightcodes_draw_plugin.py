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
    RIGHTCODES_DRAW_DEFAULT_MODEL,
    RightCodesDrawClient,
    RightCodesDrawQuotaStore,
    RightCodesDrawRequest,
    calculate_rightcodes_draw_model_points,
    extract_removed_rightcodes_draw_temporary_model,
    format_draw_start_message,
    format_rightcodes_draw_failure,
    format_rightcodes_draw_model_help,
    format_rightcodes_draw_model_switch_success,
    format_rightcodes_draw_timeout,
    format_rightcodes_draw_missing_prompt_message,
    format_rightcodes_draw_points_ranking,
    format_rightcodes_draw_points_status,
    format_rightcodes_draw_suggestion_message,
    load_rightcodes_config,
    looks_like_rightcodes_draw_feature_request,
    looks_like_rightcodes_draw_invocation,
    looks_like_rightcodes_draw_model_switch,
    looks_like_rightcodes_draw_points_mutation_request,
    looks_like_rightcodes_draw_points_query,
    looks_like_rightcodes_draw_points_ranking,
    looks_like_rightcodes_draw_suggestion,
    parse_rightcodes_draw_command,
    parse_rightcodes_draw_model_switch,
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
    def test_draw_command_rejects_removed_temporary_model_forms(self) -> None:
        for command in (
            "棉花糖生图 nano-banana-pro 一只白猫",
            "棉花糖生图 [nano-banana-pro] 一只白猫",
        ):
            with self.subTest(command=command):
                self.assertEqual(extract_removed_rightcodes_draw_temporary_model(command), "nano-banana-pro")
                self.assertIsNone(parse_rightcodes_draw_command(command))
        request = parse_rightcodes_draw_command("棉花糖生图 一只白猫")
        self.assertIsNotNone(request)
        assert request is not None
        self.assertEqual(request.model, RIGHTCODES_DRAW_DEFAULT_MODEL)
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
        self.assertTrue(looks_like_rightcodes_draw_feature_request("切换生图模型nano-banana-2"))
        self.assertTrue(looks_like_rightcodes_draw_feature_request("积分排行榜"))

    def test_rightcodes_draw_catalog_mentions_size_body(self) -> None:
        self.assertTrue(should_inject_rightcodes_draw_catalog("我要 1024x1024 body 里写什么"))
        injection = format_rightcodes_draw_catalog_injection("我要 1024x1024 body 里写什么")
        self.assertIn('"size": "1024x1024"', injection)
        self.assertIn("/v1/images/generations", injection)
        self.assertIn("stream=true", injection)
        self.assertIn("nano-banana-2-lite", injection)
        self.assertIn("$0.05/次", injection)
        self.assertIn("官方已停止 2K、4K", injection)

    def test_points_query_and_mutation_detection(self) -> None:
        self.assertTrue(looks_like_rightcodes_draw_points_query("查询生图积分"))
        self.assertTrue(looks_like_rightcodes_draw_points_query("balance"))
        self.assertTrue(looks_like_rightcodes_draw_points_ranking("积分排行"))
        self.assertTrue(looks_like_rightcodes_draw_points_ranking("积分 排行榜"))
        self.assertTrue(looks_like_rightcodes_draw_points_mutation_request("给我加100积分"))
        self.assertFalse(looks_like_rightcodes_draw_points_query("给我加100积分"))

    def test_model_switch_accepts_spaced_and_compact_commands(self) -> None:
        commands = (
            "切换生图模型 nano-banana-2",
            "切换生图模型nano-banana-2",
            "切换 生图 模型 nano-banana-2",
            "生图模型 nano-banana-2",
            "生图模型nano-banana-2",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertTrue(looks_like_rightcodes_draw_model_switch(command))
                self.assertEqual(parse_rightcodes_draw_model_switch(command), "nano-banana-2")
        self.assertTrue(looks_like_rightcodes_draw_model_switch("切换生图模型 unknown"))
        self.assertIsNone(parse_rightcodes_draw_model_switch("切换生图模型 unknown"))

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
        self.assertIn("切换生图模型", message)
        self.assertIn("已退回", format_rightcodes_draw_failure(RuntimeError("上游失败")))

    def test_quota_store_charges_first_draw_and_reports_current_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RightCodesDrawQuotaStore(Path(temp_dir))
            store.record_group_message("10001", amount=45)
            paid = store.reserve("10001", model="gpt-image-2")
            denied = store.reserve("10001", model="gpt-image-2")

            self.assertTrue(paid.allowed)
            self.assertEqual(paid.cost_points, 40)
            self.assertEqual(paid.balance_after, 5)
            self.assertFalse(denied.allowed)
            self.assertIn("扣 40 积分", format_draw_start_message(paid))
            status = format_rightcodes_draw_points_status(store.get_balance("10001"))
            self.assertIn("当前生图积分：5", status)
            self.assertIn("当前生图模型：gpt-image-2", status)
            self.assertIn("当前模型消耗：40 积分/次", status)
            self.assertIn("生图模型", status)
            self.assertIn("切换生图模型", status)
            self.assertNotIn("也可", status)

    def test_model_selection_persists_and_refund_restores_points(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RightCodesDrawQuotaStore(Path(temp_dir))
            store.record_group_message("10001", amount=200)
            selected = store.set_model("10001", "nano-banana-2-lite")
            paid = store.reserve("10001", model=selected.model)
            store.refund(paid)
            balance = store.get_balance("10001")

            self.assertEqual(selected.model, "nano-banana-2-lite")
            self.assertEqual(paid.cost_points, 50)
            self.assertEqual(balance.points, 200)
            self.assertEqual(balance.model, "nano-banana-2-lite")
            self.assertIn("单次消耗：50 积分", format_rightcodes_draw_model_switch_success(balance))

    def test_legacy_daily_free_state_is_removed_during_normalization(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RightCodesDrawQuotaStore(Path(temp_dir))
            store.store.write(
                "rightcodes.draw_points",
                {
                    "schema_version": 1,
                    "users": {
                        "10001": {
                            "points": 80,
                            "free_gpt_image_2_date": "2026-07-13",
                        }
                    },
                },
            )

            balance = store.get_balance("10001")
            normalized = store.store.read("rightcodes.draw_points", {})

            self.assertEqual(balance.model, RIGHTCODES_DRAW_DEFAULT_MODEL)
            self.assertEqual(normalized["schema_version"], 2)
            self.assertNotIn("free_gpt_image_2_date", normalized["users"]["10001"])
            self.assertEqual(normalized["users"]["10001"]["model"], RIGHTCODES_DRAW_DEFAULT_MODEL)

    def test_points_ranking_returns_global_top_ten_with_stable_ties(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RightCodesDrawQuotaStore(Path(temp_dir))
            for user_id, points in (
                ("1000000012", 30),
                ("1000000011", 30),
                ("1000000020", 20),
                ("1000000021", 19),
                ("1000000022", 18),
                ("1000000023", 17),
                ("1000000024", 16),
                ("1000000025", 15),
                ("1000000026", 14),
                ("1000000027", 13),
                ("1000000028", 12),
                ("1000000029", 11),
            ):
                store.record_group_message(user_id, amount=points)

            ranking = store.get_points_ranking(limit=10)
            message = format_rightcodes_draw_points_ranking(
                ranking,
                resolve_display_name=lambda user_id: {
                    "1000000011": "棉花糖用户",
                }.get(user_id, user_id),
            )

            self.assertEqual(len(ranking), 10)
            self.assertEqual([ranking[0].user_id, ranking[1].user_id], ["1000000011", "1000000012"])
            self.assertIn("棉花糖用户：30 积分", message)
            self.assertNotIn("QQ 1000000011", message)
            self.assertIn("QQ 100****012：30 积分", message)
            self.assertNotIn("1000000029", message)
            self.assertIn("全群生图积分排行榜", message)

    def test_legacy_global_nickname_is_removed_from_draw_points(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RightCodesDrawQuotaStore(Path(temp_dir))
            store.store.write(
                "rightcodes.draw_points",
                {
                    "schema_version": 2,
                    "users": {
                        "10001": {
                            "points": 80,
                            "model": RIGHTCODES_DRAW_DEFAULT_MODEL,
                            "nickname": "旧全局昵称",
                        }
                    },
                },
            )

            store.get_balance("10001")
            normalized = store.store.read("rightcodes.draw_points", {})

            self.assertNotIn("nickname", normalized["users"]["10001"])

    def test_model_price_table_matches_current_rightcodes_prices(self) -> None:
        self.assertEqual(calculate_rightcodes_draw_model_points("gpt-image-2"), 40)
        self.assertEqual(calculate_rightcodes_draw_model_points("gpt-image-2-vip"), 130)
        self.assertEqual(calculate_rightcodes_draw_model_points("nano-banana"), 140)
        self.assertEqual(calculate_rightcodes_draw_model_points("nano-banana-2"), 120)
        self.assertEqual(calculate_rightcodes_draw_model_points("nano-banana-2-lite"), 50)
        self.assertEqual(calculate_rightcodes_draw_model_points("nano-banana-pro"), 180)
        help_text = format_rightcodes_draw_model_help("nano-banana-2-lite")
        self.assertIn("nano-banana-2-lite（当前）", help_text)
        self.assertIn("官方已停止 2K、4K", help_text)
        self.assertIn(
            "nano-banana-2-lite（当前）：$0.05/次，100 积分",
            format_rightcodes_draw_model_help("nano-banana-2-lite", multiplier=2000),
        )

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
