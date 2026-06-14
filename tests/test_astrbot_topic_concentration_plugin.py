from __future__ import annotations

import asyncio
from collections import deque
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "astrbot-local-plugins"))

from astrbot_plugin_topic_concentration.logic import (
    TopicWindowMessage,
    active_reply_scope_key,
    build_active_reply_decision_prompt,
    build_batch_active_reply_decision_prompt,
    chat_with_current_provider,
    has_strong_topic_signal,
    is_recent_duplicate_observation,
    is_effective_batch_message,
    looks_like_direct_bot_call,
    looks_like_qqbot_fixed_command,
    looks_like_low_information,
    should_run_batch_decision,
    should_skip_unresolved_media_active_reply,
    should_force_active_reply_for_named_call,
    release_active_reply_inflight,
    should_consider_active_window,
    try_acquire_active_reply_inflight,
)
from astrbot_plugin_topic_concentration.twin_scheduler import (
    calculate_angel_probability,
    clear_scheduler_state,
    complete_claim_response,
    decide_llm_worker,
    is_worker_busy,
    mark_worker_busy,
    mark_claim_processing,
    pop_pending_delegated_comment,
    release_worker,
    record_worker_handled,
    read_group_balance,
    set_group_balance,
    targeted_twin_ids,
)
from astrbot_plugin_qqbot_features.request_context import build_current_request_context


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


class StubGroupMessageEvent:
    def __init__(
        self,
        *,
        group_id: str,
        sender_id: str,
        self_id: str,
        text: str,
        unified_msg_origin: str,
    ) -> None:
        self._group_id = group_id
        self._sender_id = sender_id
        self._self_id = self_id
        self._text = text
        self.unified_msg_origin = unified_msg_origin

    def get_group_id(self) -> str:
        return self._group_id

    def get_sender_id(self) -> str:
        return self._sender_id

    def get_self_id(self) -> str:
        return self._self_id


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

    def test_named_call_allows_llm_to_decide_even_when_low_information(self) -> None:
        window = deque(
            [
                TopicWindowMessage(
                    text="呼叫棉花糖",
                    user_id="3062317151",
                    at_bot=False,
                    reply_bot=False,
                    created_at=10.0,
                )
            ]
        )

        self.assertTrue(should_consider_active_window(window, named_call=True))

    def test_batch_decision_waits_for_time_and_message_threshold(self) -> None:
        window = deque(
            TopicWindowMessage(
                text=f"图灵完备线路怎么接第{i}句",
                user_id=str(1000 + i),
                at_bot=False,
                reply_bot=False,
                created_at=float(i),
            )
            for i in range(20)
        )

        young = should_run_batch_decision(window, now=120.0, last_decision_at=0.0)
        ready = should_run_batch_decision(window, now=360.0, last_decision_at=0.0)
        throttled = should_run_batch_decision(window, now=500.0, last_decision_at=300.0)

        self.assertFalse(young.should_run)
        self.assertEqual(young.reason, "batch_window_too_young")
        self.assertTrue(ready.should_run)
        self.assertEqual(ready.reason, "timed_message_threshold")
        self.assertFalse(throttled.should_run)
        self.assertEqual(throttled.reason, "batch_interval")

    def test_batch_decision_can_run_early_for_many_effective_messages(self) -> None:
        window = deque(
            TopicWindowMessage(
                text=f"分馏塔配方讨论第{i}句",
                user_id=str(1000 + i % 5),
                at_bot=False,
                reply_bot=False,
                created_at=float(i),
            )
            for i in range(50)
        )

        result = should_run_batch_decision(window, now=80.0, last_decision_at=0.0)
        throttled = should_run_batch_decision(window, now=80.0, last_decision_at=70.0)

        self.assertTrue(result.should_run)
        self.assertEqual(result.reason, "early_message_threshold")
        self.assertEqual(result.effective_count, 50)
        self.assertFalse(throttled.should_run)
        self.assertEqual(throttled.reason, "batch_interval")

    def test_batch_effective_messages_filter_low_info_media_and_direct_targets(self) -> None:
        effective = TopicWindowMessage(
            text="ProjectGenesis 氯化钠堵了还在生产",
            user_id="10001",
            at_bot=False,
            reply_bot=False,
            created_at=1.0,
        )
        low_info = TopicWindowMessage(
            text="？",
            user_id="10002",
            at_bot=False,
            reply_bot=False,
            created_at=2.0,
        )
        media = TopicWindowMessage(
            text="这个怎么做",
            user_id="10003",
            at_bot=False,
            reply_bot=False,
            unresolved_media_context=True,
            created_at=3.0,
        )
        direct = TopicWindowMessage(
            text="帮我看一下",
            user_id="10004",
            at_bot=True,
            reply_bot=False,
            created_at=4.0,
        )

        self.assertTrue(is_effective_batch_message(effective))
        self.assertFalse(is_effective_batch_message(low_info))
        self.assertFalse(is_effective_batch_message(media))
        self.assertFalse(is_effective_batch_message(direct))

    def test_batch_prompt_asks_for_topic_classification(self) -> None:
        window = deque(
            [
                TopicWindowMessage(
                    text="图灵完备这个线路是不是少了门",
                    user_id="10001",
                    at_bot=False,
                    reply_bot=False,
                    created_at=1.0,
                ),
                TopicWindowMessage(
                    text="我也卡在这个门上",
                    user_id="10002",
                    at_bot=False,
                    reply_bot=False,
                    created_at=2.0,
                ),
            ]
        )

        prompt = build_batch_active_reply_decision_prompt(window)

        self.assertIn("先归类话题", prompt)
        self.assertIn("effective_message_count=2", prompt)
        self.assertIn("图灵完备这个线路是不是少了门", prompt)
        self.assertIn("topic_key", prompt)

    def test_direct_named_call_forces_active_reply_without_decision_provider(self) -> None:
        window = deque(
            [
                TopicWindowMessage(
                    text="棉花糖",
                    user_id="3062317151",
                    at_bot=False,
                    reply_bot=False,
                    created_at=10.0,
                )
            ]
        )

        self.assertTrue(looks_like_direct_bot_call("棉花糖"))
        self.assertTrue(looks_like_direct_bot_call("棉花糖在吗"))
        self.assertFalse(looks_like_direct_bot_call("棉花糖生图 一只白猫"))
        self.assertTrue(should_force_active_reply_for_named_call(window))

    def test_presence_probe_after_named_call_forces_active_reply(self) -> None:
        window = deque(
            [
                TopicWindowMessage(
                    text="棉花糖",
                    user_id="3062317151",
                    at_bot=False,
                    reply_bot=False,
                    created_at=10.0,
                ),
                TopicWindowMessage(
                    text="在吗",
                    user_id="3062317151",
                    at_bot=False,
                    reply_bot=False,
                    created_at=13.0,
                ),
            ]
        )

        self.assertTrue(should_force_active_reply_for_named_call(window))

    def test_presence_probe_without_named_call_does_not_force_active_reply(self) -> None:
        window = deque(
            [
                TopicWindowMessage(
                    text="在吗",
                    user_id="3062317151",
                    at_bot=False,
                    reply_bot=False,
                    created_at=10.0,
                )
            ]
        )

        self.assertFalse(should_force_active_reply_for_named_call(window))

    def test_active_reply_prompt_uses_group_history_and_quoted_source(self) -> None:
        window = deque(
            [
                TopicWindowMessage(
                    text="回答一下",
                    user_id="3062317151",
                    at_bot=False,
                    reply_bot=True,
                    created_at=10.0,
                )
            ]
        )
        prompt = build_active_reply_decision_prompt(
            window,
            current_query="被引用消息1：如何生成画图支持分辨率：1K、2K、4K\n当前消息：回答一下",
            named_call=False,
            has_reply_source=True,
            latest_text="回答一下",
            history_lines=[
                "[san ji/12:37:37]: 如何生成画图支持分辨率：1K、2K、4K",
                "[萌泪酱/12:38:55]: 回答一下",
            ],
            active_interest=None,
        )

        self.assertIn("插件只提供上下文", prompt)
        self.assertIn("被引用消息1：如何生成画图支持分辨率：1K、2K、4K", prompt)
        self.assertIn("AstrBot 群聊上下文节选", prompt)
        self.assertIn("[san ji/12:37:37]", prompt)

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

    def test_unresolved_image_context_blocks_short_active_reply_guess(self) -> None:
        window = deque(
            [
                TopicWindowMessage(
                    text="",
                    user_id="2026961588",
                    at_bot=False,
                    reply_bot=False,
                    unresolved_media_context=True,
                    created_at=10.0,
                ),
                TopicWindowMessage(
                    text="这个末影之眼升级啥了",
                    user_id="3189534564",
                    at_bot=False,
                    reply_bot=False,
                    unresolved_media_context=True,
                    created_at=20.0,
                ),
                TopicWindowMessage(
                    text="百分之百不碎（）",
                    user_id="3055289971",
                    at_bot=False,
                    reply_bot=False,
                    created_at=30.0,
                ),
                TopicWindowMessage(
                    text="匠魂吗还是",
                    user_id="3189534564",
                    at_bot=False,
                    reply_bot=False,
                    created_at=40.0,
                ),
            ]
        )

        self.assertTrue(
            should_skip_unresolved_media_active_reply(
                window,
                latest_text="匠魂吗还是",
            )
        )

    def test_unresolved_image_context_does_not_block_named_call(self) -> None:
        window = deque(
            [
                TopicWindowMessage(
                    text="",
                    user_id="2026961588",
                    at_bot=False,
                    reply_bot=False,
                    unresolved_media_context=True,
                    created_at=10.0,
                ),
                TopicWindowMessage(
                    text="棉花糖看一下这个",
                    user_id="3189534564",
                    at_bot=False,
                    reply_bot=False,
                    created_at=20.0,
                ),
            ]
        )

        self.assertFalse(
            should_skip_unresolved_media_active_reply(
                window,
                latest_text="棉花糖看一下这个",
                named_call=True,
            )
        )

    def test_dual_platform_events_share_group_scope_and_deduplicate_same_message(self) -> None:
        group_id = "746497406"
        scope_key = f"group:{group_id}"
        first = StubGroupMessageEvent(
            group_id=group_id,
            sender_id="1798140670",
            self_id="2629227874",
            text="把你朋友送我",
            unified_msg_origin="aiocqhttp:demon:746497406",
        )
        second = StubGroupMessageEvent(
            group_id=group_id,
            sender_id="1798140670",
            self_id="1443944862",
            text="把你朋友送我",
            unified_msg_origin="aiocqhttp:angel:746497406",
        )

        window = deque(
            [
                TopicWindowMessage(
                    text="把你朋友送我",
                    user_id="1798140670",
                    at_bot=False,
                    reply_bot=False,
                    created_at=100.0,
                )
            ]
        )

        self.assertEqual(active_reply_scope_key(first), scope_key)
        self.assertEqual(active_reply_scope_key(second), scope_key)
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

    def test_active_reply_inflight_blocks_parallel_decisions_but_expires(self) -> None:
        inflight: dict[str, float] = {}

        self.assertTrue(try_acquire_active_reply_inflight(inflight, "group:10001", now=10.0))
        self.assertFalse(try_acquire_active_reply_inflight(inflight, "group:10001", now=12.0))
        self.assertTrue(try_acquire_active_reply_inflight(inflight, "group:10002", now=12.0))

        release_active_reply_inflight(inflight, "group:10001")
        self.assertTrue(try_acquire_active_reply_inflight(inflight, "group:10001", now=13.0))

        inflight["group:10003"] = 0.0
        self.assertTrue(
            try_acquire_active_reply_inflight(
                inflight,
                "group:10003",
                now=700.0,
                lease_seconds=600.0,
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

    def test_twin_scheduler_delegates_when_target_worker_busy(self) -> None:
        mark_worker_busy("1443944862", now=10.0, lease_seconds=600.0)

        target = decide_llm_worker(
            self_id="1443944862",
            at_ids=("1443944862",),
            message_key="message:def:llm",
            group_id="10001",
            original_text="@天使 配置怎么看",
            now=20.0,
        )
        delegated = decide_llm_worker(
            self_id="2629227874",
            at_ids=("1443944862",),
            message_key="message:def:llm",
            group_id="10001",
            original_text="@天使 配置怎么看",
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
        self.assertTrue(looks_like_direct_bot_call("棉花糖无限制推荐一首好歌"))

    def test_twin_target_detection_ignores_normal_group_member_mentions(self) -> None:
        self.assertEqual(targeted_twin_ids(["1443944862", "10001"]), {"1443944862"})
        self.assertEqual(targeted_twin_ids(["10001", "10002"]), set())


class StubLogger:
    def debug(self, *args, **kwargs) -> None:
        pass

    def info(self, *args, **kwargs) -> None:
        pass

    def warning(self, *args, **kwargs) -> None:
        pass


if __name__ == "__main__":
    unittest.main()
