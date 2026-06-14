from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "astrbot-local-plugins"))

from astrbot_plugin_qqbot_features.request_context import build_current_request_context
from astrbot_plugin_qqbot_features.request_context import canonical_event_claim_key


class Plain:
    def __init__(self, text: str) -> None:
        self.text = text


class Reply:
    def __init__(self, *, message_str: str = "", reply_id: str = "") -> None:
        self.message_str = message_str
        self.text = message_str
        self.id = reply_id
        self.chain = []


class At:
    def __init__(self, qq: str) -> None:
        self.qq = qq


class MessageObj:
    def __init__(self, *, message_id: str = "", timestamp: int = 0) -> None:
        self.message_id = message_id
        self.timestamp = timestamp


class StubEvent:
    def __init__(
        self,
        messages: list[object],
        *,
        message_id: str = "",
        timestamp: int = 0,
        group_id: str = "10001",
        sender_id: str = "3062317151",
        self_id: str = "2629227874",
    ) -> None:
        self._messages = messages
        self.message_obj = MessageObj(message_id=message_id, timestamp=timestamp)
        self._group_id = group_id
        self._sender_id = sender_id
        self._self_id = self_id

    def get_messages(self) -> list[object]:
        return self._messages

    def get_message_str(self) -> str:
        return "".join(getattr(message, "text", "") for message in self._messages)

    def get_group_id(self) -> str:
        return self._group_id

    def get_sender_id(self) -> str:
        return self._sender_id

    def get_self_id(self) -> str:
        return self._self_id


class AstrBotRequestContextTest(unittest.TestCase):
    def test_quoted_message_is_combined_with_current_text(self) -> None:
        event = StubEvent(
            [
                Reply(message_str="如何生成画图支持分辨率：1K、2K、4K", reply_id="m1"),
                Plain("回答一下"),
            ]
        )

        context = build_current_request_context(event)

        self.assertEqual(context.current_text, "回答一下")
        self.assertEqual(context.reply_texts, ("如何生成画图支持分辨率：1K、2K、4K",))
        self.assertIn("被引用消息1：如何生成画图支持分辨率：1K、2K、4K", context.combined_query)
        self.assertIn("当前消息：回答一下", context.combined_query)

    def test_named_call_is_detected_from_current_text(self) -> None:
        event = StubEvent([Plain("呼叫棉花糖")])

        context = build_current_request_context(event)

        self.assertTrue(context.named_call)

    def test_canonical_claim_key_ignores_platform_specific_message_id_when_text_exists(self) -> None:
        first = StubEvent([At("1443944862"), Plain("回答一下")], message_id="demon-msg", timestamp=100)
        second = StubEvent([At("1443944862"), Plain("回答一下")], message_id="angel-msg", timestamp=105)

        self.assertEqual(
            canonical_event_claim_key(first, purpose="llm"),
            canonical_event_claim_key(second, purpose="llm"),
        )

    def test_private_command_claim_key_can_be_scoped_by_current_bot(self) -> None:
        angel = StubEvent(
            [Plain("用量")],
            timestamp=100,
            group_id="",
            sender_id="605738729",
            self_id="1443944862",
        )
        demon = StubEvent(
            [Plain("用量")],
            timestamp=100,
            group_id="",
            sender_id="605738729",
            self_id="2629227874",
        )

        self.assertEqual(
            canonical_event_claim_key(angel, purpose="command:sub2api_usage"),
            canonical_event_claim_key(demon, purpose="command:sub2api_usage"),
        )
        self.assertNotEqual(
            canonical_event_claim_key(
                angel,
                purpose="command:sub2api_usage",
                include_private_self_id=True,
            ),
            canonical_event_claim_key(
                demon,
                purpose="command:sub2api_usage",
                include_private_self_id=True,
            ),
        )


if __name__ == "__main__":
    unittest.main()
