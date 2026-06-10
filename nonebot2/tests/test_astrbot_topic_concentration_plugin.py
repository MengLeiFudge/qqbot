from __future__ import annotations

import asyncio
from collections import deque
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "astrbot-local-plugins"))

from astrbot_plugin_topic_concentration.logic import (
    TopicWindowMessage,
    active_reply_scope_key,
    build_active_reply_decision_prompt,
    chat_with_current_provider,
    has_strong_topic_signal,
    is_recent_duplicate_observation,
    looks_like_qqbot_fixed_command,
    looks_like_low_information,
    release_active_reply_inflight,
    should_consider_active_window,
    try_acquire_active_reply_inflight,
)
from astrbot_plugin_topic_concentration.twin_scheduler import (
    clear_scheduler_state,
    decide_llm_worker,
    is_worker_busy,
    mark_worker_busy,
    release_worker,
    targeted_twin_ids,
)


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
            now=10.0,
        )
        second = decide_llm_worker(
            self_id="2629227874",
            at_ids=("1443944862",),
            message_key="message:abc:llm",
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
            now=20.0,
        )
        delegated = decide_llm_worker(
            self_id="2629227874",
            at_ids=("1443944862",),
            message_key="message:def:llm",
            now=21.0,
        )

        self.assertFalse(target.should_handle)
        self.assertEqual(target.worker_id, "2629227874")
        self.assertTrue(delegated.should_handle)
        self.assertEqual(delegated.reason, "message_claim_owner")
        self.assertEqual(delegated.worker_id, "2629227874")

    def test_twin_scheduler_releases_busy_worker(self) -> None:
        mark_worker_busy("2629227874", now=10.0, lease_seconds=600.0)
        self.assertTrue(is_worker_busy("2629227874", now=20.0))
        release_worker("2629227874")
        self.assertFalse(is_worker_busy("2629227874", now=20.0))

    def test_twin_scheduler_uses_random_choice_when_no_worker_targeted(self) -> None:
        rng = random.Random(0)
        choices = [
            decide_llm_worker(
                self_id="1443944862",
                message_key=f"message:random-{index}:llm",
                now=10.0 + index,
                rng=rng,
            ).worker_id
            for index in range(6)
        ]

        self.assertEqual(
            choices,
            ["2629227874", "2629227874", "1443944862", "2629227874", "2629227874", "2629227874"],
        )

    def test_fixed_command_detection_skips_llm_worker_gate(self) -> None:
        self.assertTrue(looks_like_qqbot_fixed_command("棉花生图 一只白猫"))
        self.assertTrue(looks_like_qqbot_fixed_command("查询生图积分"))
        self.assertTrue(looks_like_qqbot_fixed_command("菜单Arcaea"))
        self.assertFalse(looks_like_qqbot_fixed_command("生成一张白猫图片"))
        self.assertFalse(looks_like_qqbot_fixed_command("你怎么看这个报错"))

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
