from __future__ import annotations

import asyncio
from collections import deque
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "astrbot-local-plugins"))

from astrbot_plugin_topic_concentration.logic import (
    TopicWindowMessage,
    active_reply_scope_key,
    build_decision_provider_ids,
    chat_with_decision_providers,
    has_strong_topic_signal,
    is_recent_duplicate_observation,
    looks_like_low_information,
    normalize_provider_order,
    read_decision_provider_order,
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
    def __init__(self, providers: dict[str, StubProvider], config: dict, current_provider_id: str = "") -> None:
        self.providers = providers
        self.config = config
        self.current_provider_id = current_provider_id

    def get_provider_by_id(self, provider_id: str):
        return self.providers.get(provider_id)

    def get_using_provider(self, umo: str):
        return self.providers.get(self.current_provider_id)

    def get_config(self, umo: str | None = None):
        return self.config


class StubEvent:
    unified_msg_origin = "aiocqhttp:GroupMessage:10001"


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
    def test_explicit_decision_provider_order_is_array_and_deduplicated(self) -> None:
        order = read_decision_provider_order(
            {
                "decision_provider_order": [
                    "packyapi-gemini/gemini-3-flash-preview",
                    "",
                    "codex-everywhere/gpt-5.4-mini",
                    "packyapi-gemini/gemini-3-flash-preview",
                ]
            }
        )

        self.assertEqual(
            order,
            (
                "packyapi-gemini/gemini-3-flash-preview",
                "codex-everywhere/gpt-5.4-mini",
            ),
        )

    def test_default_order_uses_current_default_and_fallback_models(self) -> None:
        provider_ids = build_decision_provider_ids(
            configured_order=(),
            current_provider_id="packyapi-gemini/gemini-3-flash-preview",
            provider_settings={
                "default_provider_id": "packyapi-gemini/gemini-3-flash-preview",
                "fallback_chat_models": [
                    "codex-everywhere/gpt-5.4-mini",
                    "openrouter_icu/gpt-5.4-mini",
                ],
            },
        )

        self.assertEqual(
            provider_ids,
            (
                "packyapi-gemini/gemini-3-flash-preview",
                "codex-everywhere/gpt-5.4-mini",
                "openrouter_icu/gpt-5.4-mini",
            ),
        )

    def test_string_order_is_only_backward_compatible_input(self) -> None:
        self.assertEqual(
            normalize_provider_order("a/b, c/d\n a/b"),
            ("a/b", "c/d"),
        )

    def test_chat_tries_configured_providers_top_down_until_success(self) -> None:
        bad = StubProvider("bad/provider", fail=True)
        good = StubProvider("good/provider")
        skipped = StubProvider("skipped/provider")
        context = StubContext(
            {
                "bad/provider": bad,
                "good/provider": good,
                "skipped/provider": skipped,
            },
            config={"provider_settings": {}},
        )

        response = asyncio.run(
            chat_with_decision_providers(
                context=context,
                event=StubEvent(),
                prompt="prompt",
                configured_order=("bad/provider", "good/provider", "skipped/provider"),
                logger=StubLogger(),
            )
        )

        self.assertIsNotNone(response)
        self.assertEqual(response.completion_text, '{"should_reply": false}')
        self.assertEqual(bad.prompts, ["prompt"])
        self.assertEqual(good.prompts, ["prompt"])
        self.assertEqual(skipped.prompts, [])

    def test_short_interjection_question_is_low_information_not_strong_topic(self) -> None:
        self.assertTrue(looks_like_low_information("咪？"))
        self.assertFalse(has_strong_topic_signal("咪？"))
        self.assertTrue(has_strong_topic_signal("矿物利用怎么只有11级？"))

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


class StubLogger:
    def debug(self, *args, **kwargs) -> None:
        pass

    def info(self, *args, **kwargs) -> None:
        pass

    def warning(self, *args, **kwargs) -> None:
        pass


if __name__ == "__main__":
    unittest.main()
