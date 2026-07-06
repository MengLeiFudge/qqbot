from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
import random
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins"))


class StubAstrBotLogger:
    def debug(self, *args, **kwargs) -> None:
        pass

    def info(self, *args, **kwargs) -> None:
        pass

    def warning(self, *args, **kwargs) -> None:
        pass

    def error(self, *args, **kwargs) -> None:
        pass


astrbot_api_stub = types.ModuleType("astrbot.api")
astrbot_api_stub.logger = StubAstrBotLogger()
sys.modules.setdefault("astrbot", types.ModuleType("astrbot"))
sys.modules.setdefault("astrbot.api", astrbot_api_stub)

from astrbot_plugin_topic_concentration.logic import (
    FOLLOWUP_END_MARKER,
    build_call_intent_prompt,
    build_followup_instruction,
    chat_with_current_provider,
    classify_cotton_candy_call,
    has_strong_topic_signal,
    is_recent_duplicate_observation,
    looks_like_direct_bot_call,
    looks_like_low_information,
    looks_like_qqbot_fixed_command,
    parse_call_intent_response,
    strip_followup_end_marker,
)
from astrbot_plugin_topic_concentration.twin_scheduler import (
    calculate_angel_probability,
    clear_scheduler_state,
    complete_claim_response,
    decide_llm_worker,
    is_worker_busy,
    mark_claim_processing,
    mark_worker_busy,
    pop_pending_delegated_comment,
    read_group_balance,
    record_worker_handled,
    release_worker,
    set_group_balance,
    targeted_twin_ids,
)
from astrbot_plugin_qqbot_features.request_context import build_current_request_context
from astrbot_plugin_qqbot_features.source_knowledge import load_source_knowledge_config
from astrbot_plugin_qqbot_features.twin_interaction_logic import collect_target_twin_ids
from astrbot_plugin_qqbot_features.twin_interaction_logic import requires_target_twin_to_handle
from astrbot_plugin_qqbot_features.twin_interaction_logic import should_allow_twin_delegation


class StubResponse:
    def __init__(self, text: str) -> None:
        self.completion_text = text


class StubProvider:
    def __init__(self, provider_id: str, *, fail: bool = False) -> None:
        self.provider_config = {"id": provider_id}
        self.fail = fail
        self.prompts: list[str] = []

    async def text_chat(self, *, prompt: str, session_id: str, persist: bool):
        self.prompts.append(prompt)
        if self.fail:
            raise RuntimeError(f"{self.provider_config['id']} failed")
        return StubResponse('{"should_reply": false}')


class StubContext:
    def __init__(self, providers: dict[str, StubProvider], current_provider_id: str = "") -> None:
        self.providers = providers
        self.current_provider_id = current_provider_id

    def get_provider_by_id(self, provider_id: str):
        return self.providers.get(provider_id)

    def get_using_provider(self, umo: str):
        return self.providers.get(self.current_provider_id)


class StubEvent:
    unified_msg_origin = "aiocqhttp:GroupMessage:10001"

    def __init__(self, text: str = "") -> None:
        self._text = text

    def get_group_id(self) -> str:
        return "10001"

    def get_sender_id(self) -> str:
        return "3062317151"


class Plain:
    def __init__(self, text: str) -> None:
        self.text = text


class Reply:
    def __init__(self, message_str: str = "", chain: list[object] | None = None) -> None:
        self.message_str = message_str
        self.chain = chain or []
        self.id = ""


class StubRequestEvent:
    def __init__(self, messages: list[object]) -> None:
        self._messages = messages

    def get_messages(self) -> list[object]:
        return self._messages

    def get_group_id(self) -> str:
        return "1163635014"


@dataclass(frozen=True, slots=True)
class ObservedMessage:
    text: str
    user_id: str
    created_at: float


class AstrBotTopicConcentrationPluginTest(unittest.TestCase):
    def tearDown(self) -> None:
        clear_scheduler_state()

    def test_decision_uses_only_astrbot_current_provider(self) -> None:
        current = StubProvider("current/provider")
        fallback = StubProvider("fallback/provider")
        context = StubContext(
            {"current/provider": current, "fallback/provider": fallback},
            current_provider_id="current/provider",
        )

        response = asyncio.run(
            chat_with_current_provider(
                context=context,
                event=StubEvent(),
                prompt="prompt",
                logger=StubLogger(),
            )
        )

        self.assertIsNotNone(response)
        self.assertEqual(response.completion_text, '{"should_reply": false}')
        self.assertEqual(current.prompts, ["prompt"])
        self.assertEqual(fallback.prompts, [])

    def test_decision_does_not_fallback_when_current_provider_fails(self) -> None:
        current = StubProvider("current/provider", fail=True)
        fallback = StubProvider("fallback/provider")
        context = StubContext(
            {"current/provider": current, "fallback/provider": fallback},
            current_provider_id="current/provider",
        )

        response = asyncio.run(
            chat_with_current_provider(
                context=context,
                event=StubEvent(),
                prompt="prompt",
                logger=StubLogger(),
            )
        )

        self.assertIsNone(response)
        self.assertEqual(current.prompts, ["prompt"])
        self.assertEqual(fallback.prompts, [])

    def test_short_interjection_question_is_low_information_not_strong_topic(self) -> None:
        self.assertTrue(looks_like_low_information("咪？"))
        self.assertFalse(has_strong_topic_signal("咪？"))
        self.assertTrue(has_strong_topic_signal("矿物利用怎么只有11级？"))

    def test_named_call_local_classification(self) -> None:
        self.assertEqual(classify_cotton_candy_call("棉花糖"), "call")
        self.assertEqual(classify_cotton_candy_call("棉花糖在吗"), "call")
        self.assertEqual(classify_cotton_candy_call("棉花糖，帮我生成一张图片"), "call")
        self.assertEqual(classify_cotton_candy_call("棉花糖这个图片是哪个角色"), "ambiguous")
        self.assertEqual(classify_cotton_candy_call("棉花糖很好吃"), "non_call")
        self.assertEqual(classify_cotton_candy_call("草莓棉花糖在哪买"), "non_call")
        self.assertEqual(classify_cotton_candy_call("棉花糖生图 一只白猫"), "non_call")
        self.assertTrue(looks_like_direct_bot_call("棉花糖无限制推荐一首好歌"))

    def test_call_intent_prompt_is_json_only_and_separates_food_from_call(self) -> None:
        prompt = build_call_intent_prompt("棉花糖很好吃")

        self.assertIn("必须只返回 JSON", prompt)
        self.assertIn("棉花糖很好吃 => false", prompt)
        self.assertIn("棉花糖，帮我生成一张图片 => true", prompt)

    def test_parse_call_intent_response_accepts_wrapped_json(self) -> None:
        decision = parse_call_intent_response('```json\n{"should_reply": true, "reason": "用户在叫机器人"}\n```')

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertTrue(decision.should_reply)
        self.assertEqual(decision.reason, "用户在叫机器人")

    def test_followup_instruction_and_marker_are_internal(self) -> None:
        instruction = build_followup_instruction()
        self.assertIn("3 分钟 follow-up", instruction)
        self.assertIn(FOLLOWUP_END_MARKER, instruction)

        cleaned, ended = strip_followup_end_marker(f"处理完了{FOLLOWUP_END_MARKER}")
        self.assertTrue(ended)
        self.assertEqual(cleaned, "处理完了")

    def test_request_context_treats_image_placeholder_as_unresolved_media(self) -> None:
        context = build_current_request_context(
            StubRequestEvent(
                [
                    Reply("[图片]"),
                    Plain("匠魂吗还是"),
                ]
            )
        )

        self.assertEqual(context.current_text, "匠魂吗还是")
        self.assertEqual(context.reply_texts, ())
        self.assertTrue(context.unresolved_media_context)

    def test_dual_platform_duplicate_observation(self) -> None:
        window = [ObservedMessage(text="把你朋友送我", user_id="1798140670", created_at=100.0)]

        self.assertTrue(
            is_recent_duplicate_observation(
                window,
                text="把你朋友送我",
                user_id="1798140670",
                now=101.0,
            )
        )
        self.assertFalse(
            is_recent_duplicate_observation(
                window,
                text="把你朋友送我",
                user_id="1908401664",
                now=101.0,
            )
        )

    def test_twin_scheduler_claims_same_message_for_one_worker(self) -> None:
        first = decide_llm_worker(
            self_id="1443944862",
            at_ids=("1443944862",),
            message_key="message:abc:llm",
            group_id="10001",
            now=10.0,
        )
        second = decide_llm_worker(
            self_id="2629227874",
            at_ids=("1443944862",),
            message_key="message:abc:llm",
            group_id="10001",
            now=11.0,
        )

        self.assertTrue(first.should_handle)
        self.assertEqual(first.worker_id, "1443944862")
        self.assertFalse(second.should_handle)
        self.assertEqual(second.reason, "message_claimed_by_other_worker")

    def test_twin_scheduler_delegates_when_target_worker_busy_if_allowed(self) -> None:
        mark_worker_busy("1443944862", now=10.0, lease_seconds=600.0)

        target = decide_llm_worker(
            self_id="1443944862",
            at_ids=("1443944862",),
            message_key="message:def:llm",
            group_id="10001",
            original_text="@天使 配置怎么看",
            allow_delegation=True,
            now=20.0,
        )
        delegated = decide_llm_worker(
            self_id="2629227874",
            at_ids=("1443944862",),
            message_key="message:def:llm",
            group_id="10001",
            original_text="@天使 配置怎么看",
            allow_delegation=True,
            now=21.0,
        )

        self.assertFalse(target.should_handle)
        self.assertEqual(target.worker_id, "2629227874")
        self.assertTrue(delegated.should_handle)
        self.assertEqual(delegated.reason, "message_claim_owner")
        self.assertEqual(delegated.worker_id, "2629227874")
        self.assertEqual(delegated.delegated_from, "1443944862")

        mark_claim_processing("message:def:llm", "2629227874", now=22.0)
        comment = complete_claim_response("message:def:llm", "2629227874", "这个配置要先看端口", now=30.0)
        self.assertIsNotNone(comment)
        assert comment is not None
        self.assertEqual(comment.commenter_id, "1443944862")
        self.assertEqual(comment.responder_id, "2629227874")
        self.assertEqual(comment.original_text, "@天使 配置怎么看")
        self.assertEqual(read_group_balance("10001"), 1.0)

        popped = pop_pending_delegated_comment(
            group_id="10001",
            commenter_id="1443944862",
            responder_id="2629227874",
            now=31.0,
        )
        self.assertEqual(popped, comment)

    def test_twin_scheduler_blocks_delegation_for_targeted_message_when_disabled(self) -> None:
        mark_worker_busy("2629227874", now=10.0, lease_seconds=600.0)

        target = decide_llm_worker(
            self_id="2629227874",
            at_ids=("2629227874",),
            message_key="message:hug-sister:llm",
            group_id="1163635014",
            original_text="棉花糖,和你妹妹抱抱",
            allow_delegation=False,
            now=20.0,
        )
        delegated = decide_llm_worker(
            self_id="1443944862",
            at_ids=("2629227874",),
            message_key="message:hug-sister:llm",
            group_id="1163635014",
            original_text="棉花糖,和你妹妹抱抱",
            allow_delegation=False,
            now=21.0,
        )

        self.assertFalse(target.should_handle)
        self.assertEqual(target.worker_id, "2629227874")
        self.assertEqual(target.reason, "target_busy_no_delegation")
        self.assertFalse(delegated.should_handle)
        self.assertEqual(delegated.worker_id, "2629227874")
        self.assertEqual(delegated.reason, "target_busy_no_delegation")

    def test_twin_scheduler_still_delegates_general_targeted_question_when_allowed(self) -> None:
        mark_worker_busy("2629227874", now=10.0, lease_seconds=600.0)
        self.assertFalse(requires_target_twin_to_handle("配置怎么看", ("2629227874",)))
        self.assertTrue(should_allow_twin_delegation("配置怎么看", ("2629227874",)))

        delegated = decide_llm_worker(
            self_id="1443944862",
            at_ids=("2629227874",),
            message_key="message:general-question:llm",
            group_id="1163635014",
            original_text="配置怎么看",
            allow_delegation=True,
            now=21.0,
        )

        self.assertTrue(delegated.should_handle)
        self.assertEqual(delegated.worker_id, "1443944862")
        self.assertEqual(delegated.delegated_from, "2629227874")

    def test_twin_delegation_blocks_low_value_watercooler_banter(self) -> None:
        target_ids = ("2629227874",)

        self.assertFalse(should_allow_twin_delegation("对", target_ids))
        self.assertFalse(should_allow_twin_delegation("？？", target_ids))
        self.assertFalse(should_allow_twin_delegation("标点符号？", target_ids))
        self.assertFalse(should_allow_twin_delegation("我要玩棉花糖工厂", target_ids))
        self.assertFalse(should_allow_twin_delegation("有人想玩异性工厂", target_ids))
        self.assertTrue(should_allow_twin_delegation("配置错了怎么办", target_ids))

    def test_twin_delegation_uses_quoted_twin_as_effective_target(self) -> None:
        target_ids = collect_target_twin_ids((), "2629227874")

        self.assertEqual(target_ids, ("2629227874",))
        self.assertFalse(should_allow_twin_delegation("？？", target_ids))

    def test_twin_scheduler_allows_both_workers_for_dual_target_chat(self) -> None:
        angel = decide_llm_worker(
            self_id="1443944862",
            at_ids=("1443944862", "2629227874"),
            message_key="message:both:llm",
            group_id="10001",
            allow_multi_target=True,
            now=20.0,
        )
        demon = decide_llm_worker(
            self_id="2629227874",
            at_ids=("1443944862", "2629227874"),
            message_key="message:both:llm",
            group_id="10001",
            allow_multi_target=True,
            now=21.0,
        )

        self.assertTrue(angel.should_handle)
        self.assertTrue(demon.should_handle)
        self.assertTrue(angel.both_targeted)
        self.assertTrue(demon.both_targeted)
        self.assertNotEqual(angel.claim_key, demon.claim_key)
        self.assertTrue(angel.claim_key.endswith(":worker:1443944862"))
        self.assertTrue(demon.claim_key.endswith(":worker:2629227874"))

    def test_twin_scheduler_releases_busy_worker(self) -> None:
        mark_worker_busy("2629227874", now=10.0, lease_seconds=600.0)
        self.assertTrue(is_worker_busy("2629227874", now=20.0))
        release_worker("2629227874")
        self.assertFalse(is_worker_busy("2629227874", now=20.0))

    def test_twin_scheduler_uses_group_balance_probability_when_no_worker_targeted(self) -> None:
        self.assertEqual(calculate_angel_probability(0.0), 0.5)
        self.assertEqual(calculate_angel_probability(99.0), 0.8)
        self.assertEqual(calculate_angel_probability(-99.0), 0.2)

        set_group_balance("10001", 8.0)
        angel = decide_llm_worker(
            self_id="1443944862",
            message_key="message:weighted-angel:llm",
            group_id="10001",
            now=10.0,
            rng=random.Random(1),
        )
        self.assertEqual(angel.worker_id, "1443944862")
        self.assertEqual(angel.angel_probability, 0.8)

        set_group_balance("10001", -8.0)
        demon = decide_llm_worker(
            self_id="2629227874",
            message_key="message:weighted-demon:llm",
            group_id="10001",
            now=20.0,
            rng=random.Random(0),
        )
        self.assertEqual(demon.worker_id, "2629227874")
        self.assertEqual(demon.angel_probability, 0.2)

    def test_record_worker_handled_pulls_group_balance_toward_other_worker(self) -> None:
        self.assertEqual(record_worker_handled("10001", "1443944862"), -1.0)
        self.assertEqual(record_worker_handled("10001", "2629227874"), 0.0)

    def test_twin_scheduler_private_chat_always_uses_current_worker(self) -> None:
        rng = random.Random(0)

        angel = decide_llm_worker(
            self_id="1443944862",
            message_key="private:605738729:摸摸头喵",
            private_chat=True,
            now=10.0,
            rng=rng,
        )
        demon = decide_llm_worker(
            self_id="2629227874",
            message_key="private:605738729:摸摸头喵",
            private_chat=True,
            now=11.0,
            rng=rng,
        )

        self.assertTrue(angel.should_handle)
        self.assertEqual(angel.worker_id, "1443944862")
        self.assertEqual(angel.reason, "private_chat_current_worker")
        self.assertTrue(demon.should_handle)
        self.assertEqual(demon.worker_id, "2629227874")
        self.assertEqual(demon.reason, "private_chat_current_worker")

    def test_fixed_command_detection_skips_llm_worker_gate(self) -> None:
        self.assertTrue(looks_like_qqbot_fixed_command("棉花生图 一只白猫"))
        self.assertTrue(looks_like_qqbot_fixed_command("查询生图积分"))
        self.assertTrue(looks_like_qqbot_fixed_command("用量"))
        self.assertTrue(looks_like_qqbot_fixed_command("菜单Arcaea"))
        self.assertFalse(looks_like_qqbot_fixed_command("生成一张白猫图片"))
        self.assertFalse(looks_like_qqbot_fixed_command("查询"))
        self.assertFalse(looks_like_qqbot_fixed_command("查询 戴森球蓝图怎么导出"))
        self.assertFalse(looks_like_qqbot_fixed_command("你怎么看这个报错"))

    def test_twin_target_detection_ignores_normal_group_member_mentions(self) -> None:
        self.assertEqual(targeted_twin_ids(["1443944862", "10001"]), {"1443944862"})
        self.assertEqual(targeted_twin_ids(["10001", "10002"]), set())

    def test_source_defaults_are_cost_capped(self) -> None:
        source = load_source_knowledge_config({"source_roots": "shapez=/tmp/not-exists"})

        self.assertEqual(source.max_results, 4)
        self.assertEqual(source.max_chars, 2600)
        self.assertEqual(source.max_files_per_domain, 80)
        self.assertEqual(source.max_file_bytes, 220000)


class StubLogger:
    def debug(self, *args, **kwargs) -> None:
        pass

    def info(self, *args, **kwargs) -> None:
        pass

    def warning(self, *args, **kwargs) -> None:
        pass


if __name__ == "__main__":
    unittest.main()
