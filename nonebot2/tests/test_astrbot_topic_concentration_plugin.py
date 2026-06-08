from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "astrbot-local-plugins"))

from astrbot_plugin_topic_concentration.logic import (
    build_decision_provider_ids,
    chat_with_decision_providers,
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


class StubLogger:
    def debug(self, *args, **kwargs) -> None:
        pass

    def info(self, *args, **kwargs) -> None:
        pass

    def warning(self, *args, **kwargs) -> None:
        pass


if __name__ == "__main__":
    unittest.main()
