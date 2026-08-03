from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins"))

from astrbot_plugin_qqbot_features.twin_interaction_logic import (
    TwinInteractionConfig,
    build_direct_twin_prompt,
    build_identity_fact_injection,
    build_twin_injection,
    is_bare_dual_bot_call,
    is_bot_sender_id,
    is_twin_related_text,
    read_profile,
    read_profile_for_self_id,
    should_handle_direct_twin_request,
)


class AstrBotTwinInteractionPluginTest(unittest.TestCase):
    def test_detects_twin_related_text_without_generic_noise(self) -> None:
        profile = read_profile("angel")

        self.assertTrue(is_twin_related_text("云栖你怎么看夜凛刚才那句", profile))
        self.assertTrue(is_twin_related_text("你们姐妹今天谁值班", profile))
        self.assertFalse(is_twin_related_text("普通 Factorio 下载链接", profile))

    def test_direct_request_requires_private_wake_or_current_bot_mention(self) -> None:
        profile = read_profile("angel")

        self.assertTrue(
            should_handle_direct_twin_request(
                "云栖你点评一下夜凛刚才那句",
                profile,
                is_private=False,
                is_at_or_wake_command=False,
            )
        )
        self.assertTrue(
            should_handle_direct_twin_request(
                "夜凛刚才那句怎么理解",
                profile,
                is_private=False,
                is_at_or_wake_command=True,
            )
        )
        self.assertFalse(
            should_handle_direct_twin_request(
                "夜凛刚才那句怎么理解",
                profile,
                is_private=False,
                is_at_or_wake_command=False,
            )
        )

    def test_bare_dual_bot_call_is_treated_as_calling_current_bot(self) -> None:
        profile = read_profile("angel")

        self.assertTrue(is_bare_dual_bot_call("@云栖 @夜凛", profile))
        self.assertTrue(is_bare_dual_bot_call("[At:1443944862] [At:2629227874]", profile))
        self.assertFalse(is_bare_dual_bot_call("云栖 夜凛 说句话", profile))

        config = TwinInteractionConfig(
            enabled_groups=set(),
            direct_handler_enabled=True,
            max_context_chars=2000,
        )
        injection = build_twin_injection(
            text="[At:1443944862] [At:2629227874]",
            group_id="123",
            profile=profile,
            config=config,
        )

        self.assertIn("当前消息没有实质文本，只是在同时叫两个 bot", injection)
        self.assertIn("表示用户也在叫你", injection)

    def test_dual_target_task_requires_current_bot_to_answer_itself(self) -> None:
        profile = read_profile("angel")
        config = TwinInteractionConfig(
            enabled_groups=set(),
            direct_handler_enabled=True,
            max_context_chars=2000,
        )
        injection = build_twin_injection(
            text="[At:1443944862] [At:2629227874] 讲一个笑话",
            group_id="123",
            profile=profile,
            config=config,
        )

        self.assertIn("你要用当前 bot 身份完成自己的那份请求", injection)
        self.assertIn("不要转给另一个 bot", injection)
        self.assertIn("是不是该睡觉了", injection)
        self.assertIn("直接给用户一句建议", injection)
        self.assertIn("不要把问题改成评价另一个 bot", injection)
        self.assertIn("最多两句短句", injection)
        self.assertIn("不要展开长理由", injection)
        self.assertIn("晚安收尾或颜文字", injection)
        self.assertIn("该睡。再拖明天就起不来了。", injection)
        self.assertIn("只能代表当前 bot 作出自己的回应", injection)
        self.assertIn("不要追加“不过/但是”转折", injection)
        self.assertIn("不要把普通请求说成要另一个 bot 自己回应", injection)
        self.assertIn("绝对不要输出括号舞台说明", injection)

    def test_bot_sender_ids_are_never_eligible_for_direct_handling(self) -> None:
        profile = read_profile("angel")

        self.assertTrue(is_bot_sender_id(profile.bot_id, "999", profile))
        self.assertTrue(is_bot_sender_id(profile.other_bot_id, "999", profile))
        self.assertTrue(is_bot_sender_id("333", "333", profile))
        self.assertFalse(is_bot_sender_id("333", "999", profile))

    def test_profile_can_be_inferred_from_event_self_id(self) -> None:
        self.assertEqual(read_profile_for_self_id("1443944862").profile, "angel")
        self.assertEqual(read_profile_for_self_id("2629227874").profile, "demon")
        self.assertEqual(read_profile_for_self_id("missing", "angel").profile, "angel")

    def test_identity_fact_keeps_current_self_id_as_viewpoint(self) -> None:
        angel = read_profile_for_self_id("1443944862")
        demon = read_profile_for_self_id("2629227874")

        angel_injection = build_identity_fact_injection(angel)
        demon_injection = build_identity_fact_injection(demon)

        self.assertIn("你现在就是 云栖 / QQ 1443944862", angel_injection)
        self.assertIn("四姐妹顺序固定：云栖是大姐，夜凛是二姐，星遥是三妹，月澄是四妹", angel_injection)
        self.assertIn("另一位 bot 是 夜凛 / QQ 2629227874，是你的二妹", angel_injection)
        self.assertIn("星遥 / QQ 3056830689 是三妹", angel_injection)
        self.assertIn("月澄 / QQ 3109326090 是四妹", angel_injection)
        self.assertIn("不能把自己说成 夜凛", angel_injection)
        self.assertIn("你现在就是 夜凛 / QQ 2629227874", demon_injection)
        self.assertIn("另一位 bot 是 云栖 / QQ 1443944862，是你的大姐", demon_injection)
        self.assertIn("不能把自己说成 云栖", demon_injection)

    def test_injection_and_direct_prompt_keep_identity_boundary(self) -> None:
        profile = read_profile("angel")
        config = TwinInteractionConfig(
            enabled_groups=set(),
            direct_handler_enabled=True,
            max_context_chars=2000,
        )

        injection = build_twin_injection(
            text="云栖让你妹妹说句话",
            group_id="123",
            profile=profile,
            config=config,
        )
        prompt = build_direct_twin_prompt(
            text="云栖让你妹妹说句话",
            group_id="123",
            profile=profile,
            config=config,
        )

        self.assertIn("当前 bot：云栖 / QQ 1443944862", injection)
        self.assertIn("另一位 bot：夜凛 / QQ 2629227874", injection)
        self.assertIn("星遥 / QQ 3056830689 是三妹", injection)
        self.assertIn("月澄 / QQ 3109326090 是四妹", injection)
        self.assertIn("禁止：冒充另一个 bot 输出", injection)
        self.assertIn("除非用户明确要求代发/代答", prompt)
        self.assertIn("用户原话：云栖让你妹妹说句话", prompt)


if __name__ == "__main__":
    unittest.main()
