from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
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

# Minimal AstrBot stubs so main.py can be imported for formal side-effect tests.
def _transparent_decorator(*_args, **_kwargs):
    def wrap(fn):
        return fn

    if _args and callable(_args[0]) and len(_args) == 1 and not _kwargs:
        return _args[0]
    return wrap


astrbot_event_stub = types.ModuleType("astrbot.api.event")
astrbot_event_stub.filter = types.SimpleNamespace(
    event_message_type=_transparent_decorator,
    on_waiting_llm_request=_transparent_decorator,
    on_llm_request=_transparent_decorator,
    on_llm_response=_transparent_decorator,
    on_agent_done=_transparent_decorator,
    after_message_sent=_transparent_decorator,
)
sys.modules.setdefault("astrbot.api.event", astrbot_event_stub)

astrbot_components_stub = types.ModuleType("astrbot.api.message_components")


class _StubComponent:
    pass


astrbot_components_stub.At = type("At", (_StubComponent,), {})
astrbot_components_stub.Plain = type("Plain", (_StubComponent,), {})
astrbot_components_stub.Poke = type("Poke", (_StubComponent,), {})
astrbot_components_stub.Reply = type("Reply", (_StubComponent,), {})
sys.modules.setdefault("astrbot.api.message_components", astrbot_components_stub)

astrbot_star_stub = types.ModuleType("astrbot.api.star")


class _StubStar:
    def __init__(self, context=None, config=None):
        self.context = context
        self.config = config


def _register(*_args, **_kwargs):
    def wrap(cls):
        return cls

    return wrap


astrbot_star_stub.Context = object
astrbot_star_stub.Star = _StubStar
astrbot_star_stub.register = _register
sys.modules.setdefault("astrbot.api.star", astrbot_star_stub)

astrbot_core = types.ModuleType("astrbot.core")
astrbot_core_agent = types.ModuleType("astrbot.core.agent")
astrbot_core_agent_message = types.ModuleType("astrbot.core.agent.message")


class _TextPart:
    def __init__(self, text: str = ""):
        self.text = text

    def mark_as_temp(self):
        return self


astrbot_core_agent_message.TextPart = _TextPart
astrbot_core_agent_tool = types.ModuleType("astrbot.core.agent.tool")


class _FunctionTool:
    def __init__(self, name="", description="", parameters=None, handler=None, **_kwargs):
        self.name = name
        self.description = description
        self.parameters = parameters or {}
        self.handler = handler


class _ToolSet:
    def __init__(self):
        self.tools: list[_FunctionTool] = []

    def add_tool(self, tool):
        self.tools.append(tool)

    def names(self):
        return [tool.name for tool in self.tools]

    def openai_schema(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self.tools
        ]


astrbot_core_agent_tool.FunctionTool = _FunctionTool
astrbot_core_agent_tool.ToolSet = _ToolSet
astrbot_core_star = types.ModuleType("astrbot.core.star")
astrbot_core_star_filter = types.ModuleType("astrbot.core.star.filter")
astrbot_core_star_filter_event = types.ModuleType("astrbot.core.star.filter.event_message_type")
astrbot_core_star_filter_event.EventMessageType = types.SimpleNamespace(ALL="ALL")
sys.modules.setdefault("astrbot.core", astrbot_core)
sys.modules.setdefault("astrbot.core.agent", astrbot_core_agent)
sys.modules.setdefault("astrbot.core.agent.message", astrbot_core_agent_message)
sys.modules.setdefault("astrbot.core.agent.tool", astrbot_core_agent_tool)
sys.modules.setdefault("astrbot.core.star", astrbot_core_star)
sys.modules.setdefault("astrbot.core.star.filter", astrbot_core_star_filter)
sys.modules.setdefault("astrbot.core.star.filter.event_message_type", astrbot_core_star_filter_event)

from astrbot_plugin_topic_concentration.logic import (
    ACTIVATION_WINDOW_SECONDS,
    CANDIDATE_MAX_WAIT_SECONDS,
    DEACTIVATE_MARKER,
    POKE_BURST_MAX_TIMESTAMPS,
    POKE_BURST_WINDOW_SECONDS,
    POKE_MUTE_COOLDOWN_SECONDS,
    POKE_MUTE_DURATION_MAX_SECONDS,
    POKE_MUTE_DURATION_MIN_SECONDS,
    POKE_MUTE_MIN_POKES,
    POKE_MUTE_TOOL_NAME,
    POKE_MUTE_TOOL_VALID_SECONDS,
    SKIP_REPLY_MARKER,
    activate_group_chat,
    build_call_intent_prompt,
    build_group_activation_instruction,
    build_poke_interaction_instruction,
    chat_with_current_provider,
    classify_cotton_candy_call,
    clear_group_activations,
    clear_poke_interaction_state,
    deactivate_group_chat,
    has_strong_topic_signal,
    is_candidate_request_current,
    is_poke_mute_tool_eligible,
    is_recent_duplicate_observation,
    looks_like_direct_bot_call,
    looks_like_low_information,
    looks_like_qqbot_fixed_command,
    mark_poke_mute_success,
    parse_call_intent_response,
    parse_reply_control,
    pick_poke_mute_duration,
    read_group_activation,
    read_poke_burst,
    record_poke_burst,
    release_poke_mute_claim,
    renew_group_chat_after_reply,
    retry_explicit_visible_reply,
    rewrite_last_assistant_history,
    should_activate_from_poke,
    should_normalize_empty_mention,
    try_claim_poke_mute,
    validate_poke_mute_execution,
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
    try_mark_worker_busy,
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
    def __init__(
        self,
        provider_id: str,
        *,
        fail: bool = False,
        response_text: str = '{"should_reply": false}',
    ) -> None:
        self.provider_config = {"id": provider_id}
        self.fail = fail
        self.response_text = response_text
        self.prompts: list[str] = []
        self.calls: list[dict] = []

    async def text_chat(self, *, prompt: str, **kwargs):
        self.prompts.append(prompt)
        self.calls.append({"prompt": prompt, **kwargs})
        if self.fail:
            raise RuntimeError(f"{self.provider_config['id']} failed")
        return StubResponse(self.response_text)


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


class StubProviderRequest:
    def __init__(self) -> None:
        self.contexts = [{"role": "user", "content": "上一轮上下文"}]
        self.system_prompt = "保持当前人格"
        self.model = "current-model"

    async def assemble_context(self) -> dict:
        return {"role": "user", "content": "@棉花糖 闭嘴"}


@dataclass(frozen=True, slots=True)
class ObservedMessage:
    text: str
    user_id: str
    created_at: float


class AstrBotTopicConcentrationPluginTest(unittest.TestCase):
    def tearDown(self) -> None:
        clear_group_activations()
        clear_poke_interaction_state()
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

    def test_explicit_visible_reply_retry_reuses_current_provider_context(self) -> None:
        current = StubProvider(
            "current/provider",
            response_text=f"好，我先不说了。{DEACTIVATE_MARKER}",
        )
        fallback = StubProvider("fallback/provider")
        context = StubContext(
            {"current/provider": current, "fallback/provider": fallback},
            current_provider_id="current/provider",
        )

        response = asyncio.run(
            retry_explicit_visible_reply(
                context=context,
                event=StubEvent(),
                request=StubProviderRequest(),
                logger=StubLogger(),
            )
        )

        self.assertEqual(response.completion_text, f"好，我先不说了。{DEACTIVATE_MARKER}")
        self.assertEqual(fallback.calls, [])
        self.assertEqual(current.calls[0]["contexts"][-1]["content"], "@棉花糖 闭嘴")
        self.assertEqual(current.calls[0]["system_prompt"], "保持当前人格")
        self.assertEqual(current.calls[0]["model"], "current-model")
        self.assertIsNone(current.calls[0]["func_tool"])
        self.assertIn("必须重新输出至少一句", current.calls[0]["prompt"])

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

    def test_group_activation_instructions_separate_explicit_and_candidate_routes(self) -> None:
        explicit = build_group_activation_instruction(explicit=True, ordinary_reply_renewals=0)
        empty_mention = build_group_activation_instruction(
            explicit=True,
            ordinary_reply_renewals=0,
            empty_mention=True,
        )
        candidate = build_group_activation_instruction(explicit=False, ordinary_reply_renewals=0)
        repeated = build_group_activation_instruction(explicit=False, ordinary_reply_renewals=4)

        self.assertIn("必须给出至少一句可见的简短回复", explicit)
        self.assertIn(DEACTIVATE_MARKER, explicit)
        self.assertNotIn(SKIP_REPLY_MARKER, explicit)
        self.assertIn("用户只 @ 了你", empty_mention)
        self.assertIn("怎么了？", empty_mention)
        self.assertIn("不要催用户补充具体材料", empty_mention)
        self.assertIn(SKIP_REPLY_MARKER, candidate)
        self.assertIn(DEACTIVATE_MARKER, candidate)
        self.assertIn("连续续期 0 次", candidate)
        self.assertIn("必须返回", repeated)
        self.assertIn("不能只返回跳过标记", repeated)

    def test_reply_control_parser_removes_internal_markers(self) -> None:
        skipped = parse_reply_control(SKIP_REPLY_MARKER)
        self.assertTrue(skipped.skip_reply)
        self.assertFalse(skipped.deactivate)
        self.assertEqual(skipped.cleaned_text, "")

        deactivated = parse_reply_control(f"好，我先不说了。{DEACTIVATE_MARKER}")
        self.assertFalse(deactivated.skip_reply)
        self.assertTrue(deactivated.deactivate)
        self.assertEqual(deactivated.cleaned_text, "好，我先不说了。")

    def test_retry_visible_text_replaces_invalid_assistant_history_without_marker(self) -> None:
        text_part = types.SimpleNamespace(type="text", text=DEACTIVATE_MARKER)
        messages = [
            types.SimpleNamespace(role="user", content="@棉花糖 闭嘴", tool_calls=None),
            types.SimpleNamespace(role="assistant", content=[text_part], tool_calls=None),
        ]

        rewrite_last_assistant_history(messages, replacement_text="好，我先不说了。")

        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[-1].content[0].text, "好，我先不说了。")
        self.assertNotIn(DEACTIVATE_MARKER, messages[-1].content[0].text)

    def test_marker_only_assistant_history_is_removed_without_retry_text(self) -> None:
        messages = [
            types.SimpleNamespace(role="user", content="普通候选", tool_calls=None),
            types.SimpleNamespace(role="assistant", content=SKIP_REPLY_MARKER, tool_calls=None),
        ]

        rewrite_last_assistant_history(messages)

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].role, "user")

    def test_group_activation_state_is_scoped_and_renews_only_after_visible_reply(self) -> None:
        angel = activate_group_chat("10001", "1443944862", now=10.0)
        demon = activate_group_chat("10001", "2629227874", now=20.0)

        self.assertEqual(angel.expires_at, 10.0 + ACTIVATION_WINDOW_SECONDS)
        self.assertEqual(demon.expires_at, 20.0 + ACTIVATION_WINDOW_SECONDS)
        self.assertEqual(angel.generation, 1)
        self.assertEqual(demon.generation, 1)
        self.assertIsNone(read_group_activation("10002", "1443944862", now=30.0))

        renewed = renew_group_chat_after_reply("10001", "1443944862", explicit=False, now=40.0)
        self.assertEqual(renewed.ordinary_reply_renewals, 1)
        self.assertEqual(renewed.expires_at, 40.0 + ACTIVATION_WINDOW_SECONDS)
        self.assertEqual(renewed.generation, angel.generation)

        reset = renew_group_chat_after_reply("10001", "1443944862", explicit=True, now=50.0)
        self.assertEqual(reset.ordinary_reply_renewals, 0)
        self.assertIsNotNone(read_group_activation("10001", "2629227874", now=50.0))

        self.assertTrue(deactivate_group_chat("10001", "1443944862"))
        self.assertIsNone(read_group_activation("10001", "1443944862", now=51.0))
        self.assertIsNotNone(read_group_activation("10001", "2629227874", now=51.0))

    def test_newer_activation_generation_wins_over_late_reply_or_deactivation(self) -> None:
        first = activate_group_chat("10001", "1443944862", now=10.0)
        second = activate_group_chat("10001", "1443944862", now=20.0)

        self.assertGreater(second.generation, first.generation)
        self.assertIsNone(
            renew_group_chat_after_reply(
                "10001",
                "1443944862",
                explicit=False,
                expected_generation=first.generation,
                now=30.0,
            )
        )
        self.assertFalse(
            deactivate_group_chat(
                "10001",
                "1443944862",
                expected_generation=first.generation,
            )
        )
        self.assertEqual(
            read_group_activation("10001", "1443944862", now=31.0).generation,
            second.generation,
        )

        self.assertTrue(
            deactivate_group_chat(
                "10001",
                "1443944862",
                expected_generation=second.generation,
            )
        )
        self.assertIsNone(
            renew_group_chat_after_reply(
                "10001",
                "1443944862",
                explicit=False,
                expected_generation=second.generation,
                now=40.0,
            )
        )

    def test_group_activation_expires_after_three_minutes(self) -> None:
        activate_group_chat("10001", "1443944862", now=10.0)

        self.assertIsNotNone(read_group_activation("10001", "1443944862", now=189.9))
        self.assertIsNone(read_group_activation("10001", "1443944862", now=190.0))

    def test_poke_activates_only_the_human_targeted_current_bot(self) -> None:
        bot_ids = frozenset({"1443944862", "2629227874"})

        self.assertTrue(
            should_activate_from_poke(
                self_id="2629227874",
                user_id="3062317151",
                target_id="2629227874",
                bot_ids=bot_ids,
            )
        )
        self.assertFalse(
            should_activate_from_poke(
                self_id="2629227874",
                user_id="3062317151",
                target_id="1443944862",
                bot_ids=bot_ids,
            )
        )
        self.assertFalse(
            should_activate_from_poke(
                self_id="2629227874",
                user_id="1443944862",
                target_id="2629227874",
                bot_ids=bot_ids,
            )
        )

    def test_poke_burst_window_counts_and_isolates_keys(self) -> None:
        first = record_poke_burst("10001", "2629227874", "3062317151", now=10.0)
        second = record_poke_burst("10001", "2629227874", "3062317151", now=40.0)
        other_user = record_poke_burst("10001", "2629227874", "1111111111", now=41.0)
        other_bot = record_poke_burst("10001", "1443944862", "3062317151", now=42.0)
        other_group = record_poke_burst("10002", "2629227874", "3062317151", now=43.0)

        self.assertEqual(first.count, 1)
        self.assertEqual(second.count, 2)
        self.assertEqual(other_user.count, 1)
        self.assertEqual(other_bot.count, 1)
        self.assertEqual(other_group.count, 1)

        after_first_expires = read_poke_burst(
            "10001",
            "2629227874",
            "3062317151",
            now=10.0 + POKE_BURST_WINDOW_SECONDS + 0.1,
        )
        self.assertIsNotNone(after_first_expires)
        self.assertEqual(after_first_expires.count, 1)
        self.assertEqual(after_first_expires.observed_at, 40.0)

        expired = read_poke_burst(
            "10001",
            "2629227874",
            "3062317151",
            now=40.0 + POKE_BURST_WINDOW_SECONDS + 0.1,
        )
        self.assertIsNone(expired)

        rolled = record_poke_burst(
            "10001",
            "2629227874",
            "3062317151",
            now=40.0 + POKE_BURST_WINDOW_SECONDS + 1.0,
        )
        self.assertEqual(rolled.count, 1)

        # Global expiry cleanup: unrelated stale keys are dropped on later record/read.
        record_poke_burst("20001", "2629227874", "3062317151", now=1.0)
        record_poke_burst("20002", "2629227874", "3062317151", now=2.0)
        alive = record_poke_burst("20003", "2629227874", "3062317151", now=1000.0)
        self.assertEqual(alive.count, 1)
        self.assertIsNone(read_poke_burst("20001", "2629227874", "3062317151", now=1000.0))
        self.assertIsNone(read_poke_burst("20002", "2629227874", "3062317151", now=1000.0))

        # Per-key window history is capped.
        clear_poke_interaction_state()
        last = None
        for index in range(POKE_BURST_MAX_TIMESTAMPS + 5):
            last = record_poke_burst("30001", "2629227874", "3062317151", now=float(index))
        self.assertIsNotNone(last)
        self.assertEqual(last.count, POKE_BURST_MAX_TIMESTAMPS)

    def test_poke_interaction_prompt_branches_and_hides_internal_rules(self) -> None:
        single = build_poke_interaction_instruction(poke_count=1, mute_tool_available=False)
        light = build_poke_interaction_instruction(poke_count=3, mute_tool_available=True)
        heavy = build_poke_interaction_instruction(poke_count=8, mute_tool_available=True)

        self.assertIn("具体次数与内部重复等级只供你把握互动节奏", single)
        self.assertIn("不得直接报出数字次数", single)
        self.assertIn("首次拍击", single)
        self.assertIn("不必强制不耐烦", single)
        self.assertIn("不要机械复用最近回复", single)
        self.assertIn("可参考当前时间", single)
        self.assertIn("不能每次机械复述时段", single)
        self.assertIn("没有开放额外管理工具", single)
        self.assertNotIn(POKE_MUTE_TOOL_NAME, single)
        self.assertNotIn("第 1 次", single)
        self.assertNotIn("第1次", single)

        self.assertIn("刚开始重复拍击", light)
        self.assertIn("可略带不耐烦", light)
        self.assertIn(POKE_MUTE_TOOL_NAME, light)
        self.assertIn("同一请求最多调用一次", light)
        self.assertIn("是否调用完全由你自主决定", light)
        self.assertNotIn("非常频繁", light)
        self.assertNotIn("第 3 次", light)
        self.assertNotIn("第3次", light)
        self.assertNotIn("60 秒", light)
        self.assertNotIn(str(POKE_MUTE_MIN_POKES), light)

        self.assertIn("非常频繁", heavy)
        self.assertIn("更明显的不耐烦", heavy)
        self.assertNotEqual(light, heavy)
        self.assertNotIn("第 8 次", heavy)
        self.assertNotIn("第8次", heavy)
        self.assertNotIn(" 8 ", heavy)
        self.assertNotIn("60 秒", heavy)

    def test_poke_mute_eligibility_claim_cooldown_and_duration_bounds(self) -> None:
        group_id = "10001"
        self_id = "2629227874"
        sender_id = "3062317151"
        observed_at = 100.0

        self.assertFalse(
            is_poke_mute_tool_eligible(
                poke_count=1,
                observed_at=observed_at,
                group_id=group_id,
                self_id=self_id,
                sender_id=sender_id,
                now=100.0,
            )
        )
        self.assertTrue(
            is_poke_mute_tool_eligible(
                poke_count=2,
                observed_at=observed_at,
                group_id=group_id,
                self_id=self_id,
                sender_id=sender_id,
                now=100.0,
            )
        )
        self.assertFalse(
            is_poke_mute_tool_eligible(
                poke_count=2,
                observed_at=observed_at,
                group_id=group_id,
                self_id=self_id,
                sender_id=sender_id,
                now=observed_at + POKE_MUTE_TOOL_VALID_SECONDS + 0.1,
            )
        )
        self.assertFalse(
            is_poke_mute_tool_eligible(
                poke_count=2,
                observed_at=observed_at + 10.0,
                group_id=group_id,
                self_id=self_id,
                sender_id=sender_id,
                now=observed_at,
            )
        )

        self.assertEqual(
            validate_poke_mute_execution(
                event_group_id=group_id,
                event_self_id=self_id,
                event_sender_id=sender_id,
                captured_sender_id=sender_id,
                captured_count=2,
                observed_at=observed_at,
                now=101.0,
            ),
            "",
        )
        self.assertEqual(
            validate_poke_mute_execution(
                event_group_id=group_id,
                event_self_id=self_id,
                event_sender_id=sender_id,
                captured_sender_id=sender_id,
                captured_count=2,
                observed_at=observed_at + 50.0,
                now=101.0,
            ),
            "observation_in_future",
        )

        # Expired cooldown keys are pruned on later eligibility checks.
        mark_poke_mute_success(group_id, self_id, "777777777", now=50.0, cooldown_seconds=10.0)
        self.assertTrue(
            is_poke_mute_tool_eligible(
                poke_count=2,
                observed_at=70.0,
                group_id=group_id,
                self_id=self_id,
                sender_id="777777777",
                now=70.0,
            )
        )
        self.assertEqual(
            validate_poke_mute_execution(
                event_group_id=group_id,
                event_self_id=self_id,
                event_sender_id="999",
                captured_sender_id=sender_id,
                captured_count=2,
                observed_at=observed_at,
                now=101.0,
            ),
            "sender_mismatch",
        )

        self.assertTrue(try_claim_poke_mute(group_id, self_id, sender_id))
        self.assertFalse(try_claim_poke_mute(group_id, self_id, sender_id))
        self.assertFalse(
            is_poke_mute_tool_eligible(
                poke_count=2,
                observed_at=observed_at,
                group_id=group_id,
                self_id=self_id,
                sender_id=sender_id,
                now=101.0,
            )
        )
        self.assertEqual(
            validate_poke_mute_execution(
                event_group_id=group_id,
                event_self_id=self_id,
                event_sender_id=sender_id,
                captured_sender_id=sender_id,
                captured_count=2,
                observed_at=observed_at,
                now=101.0,
            ),
            "claim_busy",
        )

        release_poke_mute_claim(group_id, self_id, sender_id)
        self.assertTrue(
            is_poke_mute_tool_eligible(
                poke_count=2,
                observed_at=observed_at,
                group_id=group_id,
                self_id=self_id,
                sender_id=sender_id,
                now=101.0,
            )
        )

        self.assertTrue(try_claim_poke_mute(group_id, self_id, sender_id))
        mark_poke_mute_success(group_id, self_id, sender_id, now=110.0)
        self.assertFalse(
            is_poke_mute_tool_eligible(
                poke_count=3,
                observed_at=110.0,
                group_id=group_id,
                self_id=self_id,
                sender_id=sender_id,
                now=110.0 + POKE_MUTE_COOLDOWN_SECONDS - 1.0,
            )
        )
        self.assertEqual(
            validate_poke_mute_execution(
                event_group_id=group_id,
                event_self_id=self_id,
                event_sender_id=sender_id,
                captured_sender_id=sender_id,
                captured_count=3,
                observed_at=110.0,
                now=110.0 + POKE_MUTE_COOLDOWN_SECONDS - 1.0,
            ),
            "cooldown_active",
        )
        self.assertTrue(
            is_poke_mute_tool_eligible(
                poke_count=3,
                observed_at=110.0 + POKE_MUTE_COOLDOWN_SECONDS,
                group_id=group_id,
                self_id=self_id,
                sender_id=sender_id,
                now=110.0 + POKE_MUTE_COOLDOWN_SECONDS,
            )
        )

        # Isolation: another group/self/sender remains eligible while this key cools down.
        mark_poke_mute_success(group_id, self_id, sender_id, now=200.0)
        self.assertTrue(
            is_poke_mute_tool_eligible(
                poke_count=2,
                observed_at=200.0,
                group_id="10002",
                self_id=self_id,
                sender_id=sender_id,
                now=200.0,
            )
        )

        fixed = pick_poke_mute_duration(rng=random.Random(0))
        self.assertGreaterEqual(fixed, POKE_MUTE_DURATION_MIN_SECONDS)
        self.assertLessEqual(fixed, POKE_MUTE_DURATION_MAX_SECONDS)
        for seed in range(8):
            value = pick_poke_mute_duration(rng=random.Random(seed))
            self.assertGreaterEqual(value, POKE_MUTE_DURATION_MIN_SECONDS)
            self.assertLessEqual(value, POKE_MUTE_DURATION_MAX_SECONDS)

    def test_poke_mute_main_attach_and_side_effects(self) -> None:
        import time as time_mod

        from astrbot_plugin_topic_concentration import main as topic_main

        plugin = topic_main.TopicConcentrationPlugin(context=object())
        group_id = "10001"
        self_id = "2629227874"
        sender_id = "3062317151"
        observed_at = time_mod.monotonic()

        class MuteEvent:
            def __init__(self) -> None:
                self._extras: dict[str, object] = {}
                self.bot = types.SimpleNamespace(call_action=self._call_action)
                self._private = False
                self.calls: list[dict] = []
                self.fail_with: BaseException | None = None

            def get_group_id(self):
                return group_id

            def get_self_id(self):
                return self_id

            def get_sender_id(self):
                return sender_id

            def is_private_chat(self):
                return self._private

            def get_extra(self, key, default=""):
                return self._extras.get(key, default)

            def set_extra(self, key, value):
                self._extras[key] = value

            async def _call_action(self, action, **kwargs):
                self.calls.append({"action": action, **kwargs})
                if self.fail_with is not None:
                    raise self.fail_with

        class MuteReq:
            def __init__(self) -> None:
                self.func_tool = None
                self.extra_user_content_parts: list = []

        # First poke: tool not attached.
        first_event = MuteEvent()
        first_event.set_extra(topic_main.POKE_INTERACTION_EXTRA, "1")
        first_event.set_extra(topic_main.POKE_SENDER_EXTRA, sender_id)
        first_event.set_extra(topic_main.POKE_COUNT_EXTRA, 1)
        first_event.set_extra(topic_main.POKE_OBSERVED_AT_EXTRA, observed_at)
        first_req = MuteReq()
        self.assertFalse(
            topic_main._maybe_attach_poke_mute_tool(plugin, first_event, first_req, poke_count=1)
        )
        self.assertIsNone(first_req.func_tool)

        # Repeated poke: request-level tool with locked schema.
        event = MuteEvent()
        event.set_extra(topic_main.POKE_INTERACTION_EXTRA, "1")
        event.set_extra(topic_main.POKE_SENDER_EXTRA, sender_id)
        event.set_extra(topic_main.POKE_COUNT_EXTRA, 3)
        event.set_extra(topic_main.POKE_OBSERVED_AT_EXTRA, observed_at)
        event.set_extra(topic_main.LLM_ROUTE_EXTRA, topic_main.ROUTE_EXPLICIT)
        req = MuteReq()
        self.assertTrue(topic_main._maybe_attach_poke_mute_tool(plugin, event, req, poke_count=3))
        self.assertIsNotNone(req.func_tool)
        self.assertEqual(req.func_tool.names(), [POKE_MUTE_TOOL_NAME])
        schema = req.func_tool.tools[0].parameters
        self.assertEqual(schema.get("additionalProperties"), False)
        self.assertEqual(set(schema.get("properties", {})), {"reason"})
        self.assertNotIn("user_id", schema.get("properties", {}))
        self.assertNotIn("group_id", schema.get("properties", {}))
        self.assertNotIn("duration", schema.get("properties", {}))

        # Success: fixed sender, duration bounds, cooldown, event attempt gate.
        result = asyncio.run(plugin.qqbot_mute_repeated_poker(event, reason="too many"))
        self.assertTrue(result.startswith("mute_success: duration_seconds="))
        duration = int(result.rsplit("=", 1)[-1])
        self.assertGreaterEqual(duration, POKE_MUTE_DURATION_MIN_SECONDS)
        self.assertLessEqual(duration, POKE_MUTE_DURATION_MAX_SECONDS)
        self.assertEqual(len(event.calls), 1)
        self.assertEqual(event.calls[0]["action"], "set_group_ban")
        self.assertEqual(event.calls[0]["group_id"], int(group_id))
        self.assertEqual(event.calls[0]["user_id"], int(sender_id))
        self.assertEqual(event.calls[0]["duration"], duration)
        self.assertEqual(event.get_extra(topic_main.POKE_MUTE_ATTEMPTED_EXTRA, ""), "1")
        self.assertFalse(
            is_poke_mute_tool_eligible(
                poke_count=4,
                observed_at=observed_at,
                group_id=group_id,
                self_id=self_id,
                sender_id=sender_id,
                now=observed_at + 1.0,
            )
        )

        # Same event second call: stable already_attempted, no extra API call.
        second = asyncio.run(plugin.qqbot_mute_repeated_poker(event, reason="retry"))
        self.assertEqual(second, "mute_rejected: already_attempted")
        self.assertEqual(len(event.calls), 1)

        # Ordinary failure releases global claim; new event can re-decide without cooldown
        # only after claim release — cooldown only on success. Use a fresh key.
        clear_poke_interaction_state()
        fail_event = MuteEvent()
        fail_event.set_extra(topic_main.POKE_INTERACTION_EXTRA, "1")
        fail_event.set_extra(topic_main.POKE_SENDER_EXTRA, sender_id)
        fail_event.set_extra(topic_main.POKE_COUNT_EXTRA, 2)
        fail_event.set_extra(topic_main.POKE_OBSERVED_AT_EXTRA, observed_at)
        fail_event.set_extra(topic_main.LLM_ROUTE_EXTRA, topic_main.ROUTE_EXPLICIT)
        fail_event.fail_with = RuntimeError("ban_failed")
        failed = asyncio.run(plugin.qqbot_mute_repeated_poker(fail_event))
        self.assertEqual(failed, "mute_failed: RuntimeError")
        self.assertEqual(fail_event.get_extra(topic_main.POKE_MUTE_ATTEMPTED_EXTRA, ""), "1")
        self.assertEqual(
            validate_poke_mute_execution(
                event_group_id=group_id,
                event_self_id=self_id,
                event_sender_id=sender_id,
                captured_sender_id=sender_id,
                captured_count=2,
                observed_at=observed_at,
                now=observed_at + 1.0,
            ),
            "",
        )
        # Same event cannot re-call API after failure gate.
        again = asyncio.run(plugin.qqbot_mute_repeated_poker(fail_event))
        self.assertEqual(again, "mute_rejected: already_attempted")
        self.assertEqual(len(fail_event.calls), 1)

        # CancelledError propagates and still releases claim / marks attempted.
        clear_poke_interaction_state()
        cancel_event = MuteEvent()
        cancel_event.set_extra(topic_main.POKE_INTERACTION_EXTRA, "1")
        cancel_event.set_extra(topic_main.POKE_SENDER_EXTRA, sender_id)
        cancel_event.set_extra(topic_main.POKE_COUNT_EXTRA, 2)
        cancel_event.set_extra(topic_main.POKE_OBSERVED_AT_EXTRA, observed_at)
        cancel_event.set_extra(topic_main.LLM_ROUTE_EXTRA, topic_main.ROUTE_EXPLICIT)
        cancel_event.fail_with = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            asyncio.run(plugin.qqbot_mute_repeated_poker(cancel_event))
        self.assertEqual(cancel_event.get_extra(topic_main.POKE_MUTE_ATTEMPTED_EXTRA, ""), "1")
        self.assertEqual(
            validate_poke_mute_execution(
                event_group_id=group_id,
                event_self_id=self_id,
                event_sender_id=sender_id,
                captured_sender_id=sender_id,
                captured_count=2,
                observed_at=observed_at,
                now=observed_at + 1.0,
            ),
            "",
        )

        # Representative rejection paths.
        clear_poke_interaction_state()
        private = MuteEvent()
        private._private = True
        private.set_extra(topic_main.LLM_ROUTE_EXTRA, topic_main.ROUTE_EXPLICIT)
        private.set_extra(topic_main.POKE_INTERACTION_EXTRA, "1")
        private.set_extra(topic_main.POKE_SENDER_EXTRA, sender_id)
        private.set_extra(topic_main.POKE_COUNT_EXTRA, 2)
        private.set_extra(topic_main.POKE_OBSERVED_AT_EXTRA, observed_at)
        self.assertEqual(
            asyncio.run(plugin.qqbot_mute_repeated_poker(private)),
            "mute_rejected: invalid_route",
        )

        non_poke = MuteEvent()
        non_poke.set_extra(topic_main.LLM_ROUTE_EXTRA, topic_main.ROUTE_EXPLICIT)
        non_poke.set_extra(topic_main.POKE_SENDER_EXTRA, sender_id)
        non_poke.set_extra(topic_main.POKE_COUNT_EXTRA, 2)
        non_poke.set_extra(topic_main.POKE_OBSERVED_AT_EXTRA, observed_at)
        self.assertEqual(
            asyncio.run(plugin.qqbot_mute_repeated_poker(non_poke)),
            "mute_rejected: not a repeated poke request",
        )

        mismatch = MuteEvent()
        mismatch.set_extra(topic_main.LLM_ROUTE_EXTRA, topic_main.ROUTE_EXPLICIT)
        mismatch.set_extra(topic_main.POKE_INTERACTION_EXTRA, "1")
        mismatch.set_extra(topic_main.POKE_SENDER_EXTRA, "999")
        mismatch.set_extra(topic_main.POKE_COUNT_EXTRA, 2)
        mismatch.set_extra(topic_main.POKE_OBSERVED_AT_EXTRA, observed_at)
        self.assertEqual(
            asyncio.run(plugin.qqbot_mute_repeated_poker(mismatch)),
            "mute_rejected: sender_mismatch",
        )

        expired = MuteEvent()
        expired.set_extra(topic_main.LLM_ROUTE_EXTRA, topic_main.ROUTE_EXPLICIT)
        expired.set_extra(topic_main.POKE_INTERACTION_EXTRA, "1")
        expired.set_extra(topic_main.POKE_SENDER_EXTRA, sender_id)
        expired.set_extra(topic_main.POKE_COUNT_EXTRA, 2)
        expired.set_extra(
            topic_main.POKE_OBSERVED_AT_EXTRA,
            observed_at - POKE_MUTE_TOOL_VALID_SECONDS - 1.0,
        )
        self.assertEqual(
            asyncio.run(plugin.qqbot_mute_repeated_poker(expired)),
            "mute_rejected: observation_expired",
        )

    def test_only_current_bot_at_without_content_is_normalized_as_empty_mention(self) -> None:
        self.assertTrue(
            should_normalize_empty_mention(
                self_id="1443944862",
                at_target_ids=("1443944862",),
                has_other_content=False,
            )
        )
        self.assertFalse(
            should_normalize_empty_mention(
                self_id="1443944862",
                at_target_ids=("2629227874",),
                has_other_content=False,
            )
        )
        self.assertFalse(
            should_normalize_empty_mention(
                self_id="1443944862",
                at_target_ids=("1443944862", "2629227874"),
                has_other_content=False,
            )
        )
        self.assertFalse(
            should_normalize_empty_mention(
                self_id="1443944862",
                at_target_ids=("1443944862",),
                has_other_content=True,
            )
        )

    def test_shipped_config_disables_astrbot_empty_mention_waiter(self) -> None:
        config = json.loads((ROOT / "config" / "astrbot" / "cmd_config.example.json").read_text(encoding="utf-8"))

        self.assertFalse(config["platform_settings"]["empty_mention_waiting"])
        self.assertFalse(config["platform_settings"]["empty_mention_waiting_need_reply"])

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

    def test_twin_scheduler_forces_explicit_target_even_while_busy(self) -> None:
        mark_worker_busy("2629227874", now=10.0, lease_seconds=600.0)

        target = decide_llm_worker(
            self_id="2629227874",
            at_ids=("2629227874",),
            message_key="message:explicit-busy:llm",
            group_id="1163635014",
            allow_delegation=False,
            force_targeted=True,
            now=20.0,
        )
        other = decide_llm_worker(
            self_id="1443944862",
            at_ids=("2629227874",),
            message_key="message:explicit-busy:llm",
            group_id="1163635014",
            allow_delegation=False,
            force_targeted=True,
            now=21.0,
        )

        self.assertTrue(target.should_handle)
        self.assertEqual(target.worker_id, "2629227874")
        self.assertEqual(target.reason, "target_forced")
        self.assertFalse(other.should_handle)
        self.assertEqual(other.reason, "message_claimed_by_other_worker")

    def test_twin_scheduler_forces_untargeted_named_call_when_both_workers_busy(self) -> None:
        mark_worker_busy("1443944862", now=10.0, lease_seconds=600.0)
        mark_worker_busy("2629227874", now=10.0, lease_seconds=600.0)

        selected = decide_llm_worker(
            self_id="1443944862",
            message_key="message:named-busy:llm",
            group_id="1163635014",
            force_untargeted=True,
            now=20.0,
            rng=random.Random(1),
        )
        other = decide_llm_worker(
            self_id="2629227874",
            message_key="message:named-busy:llm",
            group_id="1163635014",
            force_untargeted=True,
            now=21.0,
            rng=random.Random(1),
        )

        self.assertTrue(selected.should_handle)
        self.assertEqual(selected.worker_id, "1443944862")
        self.assertEqual(selected.reason, "untargeted_forced")
        self.assertFalse(other.should_handle)
        self.assertEqual(other.reason, "message_claimed_by_other_worker")

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

    def test_twin_scheduler_candidate_reservation_requires_idle_worker(self) -> None:
        self.assertTrue(try_mark_worker_busy("2629227874", now=10.0, lease_seconds=600.0))
        self.assertFalse(try_mark_worker_busy("2629227874", now=11.0, lease_seconds=600.0))
        release_worker("2629227874")
        self.assertTrue(try_mark_worker_busy("2629227874", now=12.0, lease_seconds=600.0))

    def test_candidate_request_requires_current_generation_and_short_wait(self) -> None:
        first = activate_group_chat("1163635014", "2629227874", now=10.0)
        assert first is not None

        self.assertTrue(
            is_candidate_request_current(
                "1163635014",
                "2629227874",
                expected_generation=first.generation,
                queued_at=12.0,
                now=12.0 + CANDIDATE_MAX_WAIT_SECONDS,
            )
        )
        self.assertFalse(
            is_candidate_request_current(
                "1163635014",
                "2629227874",
                expected_generation=first.generation,
                queued_at=12.0,
                now=12.001 + CANDIDATE_MAX_WAIT_SECONDS,
            )
        )

        second = activate_group_chat("1163635014", "2629227874", now=20.0)
        assert second is not None
        self.assertFalse(
            is_candidate_request_current(
                "1163635014",
                "2629227874",
                expected_generation=first.generation,
                queued_at=20.0,
                now=21.0,
            )
        )

    def test_twin_scheduler_keeps_worker_busy_until_all_concurrent_requests_finish(self) -> None:
        mark_worker_busy("2629227874", now=10.0, lease_seconds=600.0)
        mark_worker_busy("2629227874", now=11.0, lease_seconds=600.0)

        release_worker("2629227874")
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
        self.assertTrue(looks_like_qqbot_fixed_command("积分排行"))
        self.assertTrue(looks_like_qqbot_fixed_command("积分 排行榜"))
        self.assertTrue(looks_like_qqbot_fixed_command("切换生图模型nano-banana-2"))
        self.assertTrue(looks_like_qqbot_fixed_command("切换 生图 模型 nano-banana-2"))
        self.assertTrue(looks_like_qqbot_fixed_command("生图模型 nano-banana-2"))
        self.assertTrue(looks_like_qqbot_fixed_command("用量"))
        self.assertTrue(looks_like_qqbot_fixed_command("菜单Arcaea"))
        self.assertTrue(looks_like_qqbot_fixed_command("JM1244589"))
        self.assertTrue(looks_like_qqbot_fixed_command("jm1244589"))
        self.assertTrue(looks_like_qqbot_fixed_command("JM 1244589"))
        self.assertFalse(looks_like_qqbot_fixed_command("请问 JM1244589 是哪部作品"))
        self.assertFalse(looks_like_qqbot_fixed_command("推荐一本 JM 1244589 相关的漫画"))
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
