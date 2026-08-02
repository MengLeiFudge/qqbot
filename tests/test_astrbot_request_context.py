from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins"))

from astrbot_plugin_qqbot_features.request_context import build_current_request_context
from astrbot_plugin_qqbot_features.request_context import canonical_event_claim_key
from astrbot_plugin_qqbot_features.request_context import extract_image_sources
from astrbot_plugin_qqbot_features.request_context import extract_reply_source_messages
from astrbot_plugin_qqbot_features.request_context import format_source_messages


class Plain:
    def __init__(self, text: str) -> None:
        self.text = text


class Reply:
    def __init__(
        self,
        *,
        message_str: str = "",
        reply_id: str = "",
        chain: list[object] | None = None,
        sender_id: object = "",
    ) -> None:
        self.message_str = message_str
        self.text = message_str
        self.id = reply_id
        self.chain = chain or []
        self.sender_id = sender_id


class Node:
    def __init__(self, *, uin: object = "", content: object = None) -> None:
        self.uin = uin
        self.content = [] if content is None else content


class Nodes:
    def __init__(self, nodes: list[object] | None = None) -> None:
        self.nodes = nodes or []


class Forward:
    def __init__(self, forward_id: object = "") -> None:
        self.id = forward_id


class At:
    def __init__(self, qq: str) -> None:
        self.qq = qq


class Image:
    def __init__(self, *, url: str = "", file: str = "", path: str = "") -> None:
        self.url = url
        self.file = file
        self.path = path


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

    def test_reply_source_tree_preserves_reply_and_node_qq(self) -> None:
        event = StubEvent(
            [
                Reply(
                    sender_id="11101",
                    message_str="顶层引用",
                    chain=[
                        Plain("顶层引用"),
                        Nodes(
                            [
                                Node(uin="22202", content=[Plain("第一条")]),
                                Node(
                                    uin=33303,
                                    content=[Plain("第二条"), Forward("nested-forward")],
                                ),
                            ]
                        ),
                    ],
                )
            ]
        )

        sources = extract_reply_source_messages(event)
        text = format_source_messages(sources)

        self.assertEqual(sources[0].sender_qq, "11101")
        self.assertEqual(sources[0].text, "顶层引用")
        self.assertEqual([child.sender_qq for child in sources[0].children], ["22202", "33303"])
        self.assertEqual(sources[0].children[1].children[0].forward_id, "nested-forward")
        self.assertIn("发送者 QQ：11101", text)
        self.assertIn("发送者 QQ：22202", text)
        self.assertIn("发送者 QQ：33303", text)
        self.assertIn("第一条", text)
        self.assertIn("第二条", text)

    def test_unknown_or_zero_sender_is_not_guessed(self) -> None:
        event = StubEvent(
            [
                Reply(
                    sender_id=0,
                    message_str="未知顶层",
                    chain=[Node(uin="", content=[Plain("未知内层")])],
                )
            ]
        )

        text = format_source_messages(extract_reply_source_messages(event))

        self.assertNotIn("发送者 QQ", text)
        self.assertIn("未知顶层", text)
        self.assertIn("未知内层", text)

    def test_source_formatter_bounds_depth_and_text_growth(self) -> None:
        event = StubEvent(
            [
                Reply(
                    sender_id="1",
                    message_str="root",
                    chain=[Node(uin="2", content=[Node(uin="3", content=[Plain("deep")])])],
                )
            ]
        )

        text = format_source_messages(
            extract_reply_source_messages(event),
            max_depth=1,
            max_chars=30,
        )

        self.assertLessEqual(len(text), 30)
        self.assertNotIn("发送者 QQ：3", text)

    def test_named_call_is_detected_from_current_text(self) -> None:
        event = StubEvent([Plain("呼叫棉花糖")])

        context = build_current_request_context(event)

        self.assertTrue(context.named_call)

    def test_extract_image_sources_from_current_and_quoted_message(self) -> None:
        event = StubEvent(
            [
                Reply(chain=[Image(url="https://example.invalid/quoted.png")]),
                Plain("棉花生图 仿照上面的图片"),
                Image(file="https://example.invalid/current.png"),
                Image(file="https://example.invalid/current.png"),
            ]
        )

        self.assertEqual(
            extract_image_sources(event),
            (
                "https://example.invalid/quoted.png",
                "https://example.invalid/current.png",
            ),
        )

    def test_canonical_claim_key_ignores_platform_specific_message_id_when_text_exists(self) -> None:
        first = StubEvent([At("1443944862"), Plain("回答一下")], message_id="demon-msg", timestamp=100)
        second = StubEvent([At("1443944862"), Plain("回答一下")], message_id="angel-msg", timestamp=105)

        self.assertEqual(
            canonical_event_claim_key(first, purpose="llm"),
            canonical_event_claim_key(second, purpose="llm"),
        )

    def test_canonical_claim_key_uses_reply_text_instead_of_platform_reply_id(self) -> None:
        first = StubEvent(
            [
                Reply(message_str="上一条模型价格回答", reply_id="angel-reply-id"),
                At("1443944862"),
                Plain("我买了10块钱的一小时用完了喵"),
            ],
            timestamp=100,
        )
        second = StubEvent(
            [
                Reply(message_str="上一条模型价格回答", reply_id="demon-reply-id"),
                At("1443944862"),
                Plain("我买了10块钱的一小时用完了喵"),
            ],
            timestamp=105,
        )

        self.assertEqual(
            canonical_event_claim_key(first, purpose="llm"),
            canonical_event_claim_key(second, purpose="llm"),
        )

    def test_canonical_claim_key_keeps_different_reply_texts_separate(self) -> None:
        first = StubEvent(
            [Reply(message_str="上一条模型价格回答", reply_id="same-id"), At("1443944862"), Plain("回答一下")],
            timestamp=100,
        )
        second = StubEvent(
            [Reply(message_str="另一条上下文", reply_id="same-id"), At("1443944862"), Plain("回答一下")],
            timestamp=105,
        )

        self.assertNotEqual(
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
