from __future__ import annotations

from pathlib import Path
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins"))


class Plain:
    def __init__(self, text: str = "") -> None:
        self.text = text


class Reply:
    def __init__(self, **kwargs) -> None:
        self.id = kwargs.get("id", "")
        self.chain = kwargs.get("chain", [])
        self.sender_id = kwargs.get("sender_id", "")
        self.message_str = kwargs.get("message_str", "")
        self.text = self.message_str


class At:
    def __init__(self, **kwargs) -> None:
        self.qq = kwargs.get("qq", "")


class Nodes:
    def __init__(self, nodes=None) -> None:
        self.nodes = nodes or []


class Forward:
    def __init__(self, forward_id: str = "") -> None:
        self.id = forward_id


class Node:
    pass


components_stub = types.ModuleType("astrbot.core.message.components")
components_stub.Plain = Plain
components_stub.Reply = Reply
components_stub.At = At
components_stub.Nodes = Nodes
components_stub.Node = Node
components_stub.Forward = Forward
sys.modules.setdefault("astrbot", types.ModuleType("astrbot"))
sys.modules.setdefault("astrbot.core", types.ModuleType("astrbot.core"))
sys.modules.setdefault("astrbot.core.message", types.ModuleType("astrbot.core.message"))
sys.modules["astrbot.core.message.components"] = components_stub

chain_parser_stub = types.ModuleType("astrbot.core.utils.quoted_message.chain_parser")


class OneBotPayloadParser:
    def parse_get_forward_payload(self, payload):
        return payload


chain_parser_stub.OneBotPayloadParser = OneBotPayloadParser
sys.modules.setdefault("astrbot.core.utils", types.ModuleType("astrbot.core.utils"))
sys.modules.setdefault(
    "astrbot.core.utils.quoted_message",
    types.ModuleType("astrbot.core.utils.quoted_message"),
)
sys.modules["astrbot.core.utils.quoted_message.chain_parser"] = chain_parser_stub

from astrbot_plugin_qqbot_features.reply_style_guard_logic import sanitize_reply_plain_text
from astrbot_plugin_qqbot_features.reply_style_guard_logic import should_reply_too_long_to_read
from astrbot_plugin_qqbot_features.reply_style_guard_logic import CHAT_BUBBLE_REPLY_INSTRUCTION
from astrbot_plugin_qqbot_features.reply_style_guard_logic import STYLE_IMMUTABILITY_INSTRUCTION
from astrbot_plugin_qqbot_features.reply_style_guard_logic import is_dangerous_local_tool_name
from astrbot_plugin_qqbot_features.reply_style_guard_logic import split_chat_bubble_lines
from astrbot_plugin_qqbot_features.reply_style_guard_logic import strip_decorative_tail
from astrbot_plugin_qqbot_features.reply_style_guard_logic import split_forward_text
from astrbot_plugin_qqbot_features.reply_style_guard_logic import should_fold_long_reply
from astrbot_plugin_qqbot_features.reply_style_guard_logic import should_disable_segmented_reply_for_text
from astrbot_plugin_qqbot_features.reply_style_guard_logic import strip_permission_escalation_advice
from astrbot_plugin_qqbot_features.reply_style_guard_logic import strip_followup_tail
from astrbot_plugin_qqbot_features.reply_style_guard_logic import strip_markdown_syntax
from astrbot_plugin_qqbot_features.reply_style_guard_logic import should_disable_model_regex_segmenting
from astrbot_plugin_qqbot_features.reply_style_guard_logic import build_both_targeted_reply_instruction_text
from astrbot_plugin_qqbot_features.request_context import format_source_messages
from astrbot_plugin_qqbot_features.request_context import collect_source_image_sources
from astrbot_plugin_qqbot_features.reply_style_guard_runtime import extract_onebot_forward_sources
from astrbot_plugin_qqbot_features.reply_style_guard_runtime import extract_onebot_forward_text
from astrbot_plugin_qqbot_features.reply_style_guard_runtime import extract_onebot_source_tree
from astrbot_plugin_qqbot_features.reply_style_guard_runtime import has_forward_message


class ForwardEvent:
    def __init__(self, forward_ids: list[str], payloads: dict[str, object], *, in_reply: bool = False) -> None:
        forwards = [Forward(forward_id) for forward_id in forward_ids]
        self._messages = [Reply(chain=forwards)] if in_reply else forwards
        self._payloads = payloads
        self.calls: list[str] = []
        self.bot = types.SimpleNamespace(call_action=self.call_action)

    def get_messages(self):
        return self._messages

    async def call_action(self, action: str, **params):
        self.assert_action(action)
        forward_id = str(params.get("message_id", params.get("id", "")))
        self.calls.append(forward_id)
        result = self._payloads[forward_id]
        if isinstance(result, Exception):
            raise result
        return result

    @staticmethod
    def assert_action(action: str) -> None:
        if action != "get_forward_msg":
            raise AssertionError(f"unexpected OneBot action: {action}")


class SourceTreeEvent:
    def __init__(self, messages: list[object], payloads: dict[str, object]) -> None:
        self._messages = messages
        self._payloads = payloads
        self.calls: list[str] = []
        self.bot = types.SimpleNamespace(api=types.SimpleNamespace(call_action=self.call_action))

    def get_messages(self):
        return self._messages

    async def call_action(self, action: str, **params):
        ForwardEvent.assert_action(action)
        forward_id = str(params.get("message_id", params.get("id", "")))
        self.calls.append(forward_id)
        result = self._payloads[forward_id]
        if isinstance(result, Exception):
            raise result
        return result


class AstrBotForwardMessageTest(unittest.IsolatedAsyncioTestCase):
    async def test_extracts_top_level_forward_as_one_text(self) -> None:
        event = ForwardEvent(
            ["outer"],
            {"outer": {"text": "第一条\n第二条", "forward_ids": []}},
        )

        text = await extract_onebot_forward_text(event)

        self.assertEqual(text, "第一条\n第二条")
        self.assertEqual(event.calls, ["outer"])

    async def test_nested_failure_keeps_readable_outer_text(self) -> None:
        event = ForwardEvent(
            ["outer"],
            {
                "outer": {"text": "外层正文", "forward_ids": ["inner"]},
                "inner": RuntimeError("forward message expired"),
            },
        )

        text = await extract_onebot_forward_text(event)

        self.assertEqual(text, "外层正文")
        self.assertEqual(event.calls[0], "outer")
        self.assertIn("inner", event.calls)

    async def test_top_level_failure_returns_empty_text(self) -> None:
        event = ForwardEvent(
            ["expired"],
            {"expired": RuntimeError("forward message expired")},
        )

        text = await extract_onebot_forward_text(event)

        self.assertEqual(text, "")
        self.assertTrue(event.calls)
        self.assertEqual(set(event.calls), {"expired"})

    async def test_source_tree_top_level_failure_returns_no_sources(self) -> None:
        event = ForwardEvent(
            ["expired"],
            {"expired": RuntimeError("forward message expired")},
        )

        sources = await extract_onebot_source_tree(event)

        self.assertEqual(format_source_messages(sources), "")
        self.assertEqual(set(event.calls), {"expired"})

    async def test_aggregates_multiple_forwards_and_readable_nested_content(self) -> None:
        event = ForwardEvent(
            ["first", "second"],
            {
                "first": {"text": "第一组", "forward_ids": ["inner"]},
                "second": {"text": "第二组", "forward_ids": []},
                "inner": {"text": "内层补充", "forward_ids": []},
            },
        )

        text = await extract_onebot_forward_text(event)

        self.assertEqual(text, "第一组\n第二组\n内层补充")
        self.assertEqual(event.calls, ["first", "second", "inner"])

    async def test_complete_tree_keeps_reply_sender_above_nested_forward_senders(self) -> None:
        event = SourceTreeEvent(
            [Reply(sender_id="111", message_str="引用根", chain=[Forward("outer")])],
            {
                "outer": {
                    "messages": [
                        {
                            "sender": {"user_id": "222"},
                            "content": [
                                {"type": "text", "data": {"text": "外层转发"}},
                                {"type": "forward", "data": {"id": "inner"}},
                            ],
                        }
                    ]
                },
                "inner": {
                    "nodeList": [
                        {
                            "sender": {"user_id": "333"},
                            "content": [{"type": "text", "data": {"text": "内层转发"}}],
                        }
                    ]
                },
            },
        )

        tree = await extract_onebot_source_tree(event)

        self.assertEqual(len(tree), 1)
        self.assertEqual(tree[0].sender_qq, "111")
        self.assertEqual(tree[0].text, "引用根")
        self.assertEqual(tree[0].children[0].sender_qq, "222")
        self.assertEqual(tree[0].children[0].text, "外层转发")
        self.assertEqual(tree[0].children[0].children[0].sender_qq, "333")
        self.assertEqual(tree[0].children[0].children[0].text, "内层转发")
        self.assertEqual(event.calls, ["outer", "inner"])

    async def test_formatted_source_tree_keeps_qq_and_current_message_separate(self) -> None:
        event = SourceTreeEvent(
            [Reply(sender_id="111", message_str="引用根", chain=[Forward("outer")])],
            {
                "outer": {
                    "messages": [
                        {
                            "sender": {"user_id": "222"},
                            "content": [{"type": "text", "data": {"text": "转发正文"}}],
                        }
                    ]
                }
            },
        )

        source_text = format_source_messages(await extract_onebot_source_tree(event))
        injection = f"来源消息：\n{source_text}\n当前消息：请解释这段"

        self.assertIn("发送者 QQ：111", injection)
        self.assertIn("引用根", injection)
        self.assertIn("发送者 QQ：222", injection)
        self.assertIn("转发正文", injection)
        self.assertIn("当前消息：请解释这段", injection)
        self.assertNotIn("当前 bot", injection)
        self.assertNotIn("云栖", injection)
        self.assertNotIn("夜凛", injection)
        self.assertEqual(event.calls, ["outer"])

    async def test_multiple_reply_and_forward_roots_keep_their_own_subtrees(self) -> None:
        event = SourceTreeEvent(
            [
                Reply(sender_id="111", message_str="第一引用", chain=[Forward("first")]),
                Reply(sender_id="444", message_str="第二引用", chain=[Forward("second")]),
                Forward("top"),
            ],
            {
                "first": {
                    "message": [
                        {
                            "sender": {"user_id": "222"},
                            "content": [{"type": "text", "data": {"text": "第一子树"}}],
                        }
                    ]
                },
                "second": {
                    "nodes": [
                        {
                            "sender": {"user_id": "555"},
                            "content": [{"type": "text", "data": {"text": "第二子树"}}],
                        }
                    ]
                },
                "top": {
                    "nodeList": [
                        {
                            "sender": {"user_id": "666"},
                            "content": [{"type": "text", "data": {"text": "顶层转发"}}],
                        }
                    ]
                },
            },
        )

        tree = await extract_onebot_source_tree(event)

        self.assertEqual([root.sender_qq for root in tree], ["111", "444", "666"])
        self.assertEqual(tree[0].children[0].sender_qq, "222")
        self.assertEqual(tree[0].children[0].text, "第一子树")
        self.assertEqual(tree[1].children[0].sender_qq, "555")
        self.assertEqual(tree[1].children[0].text, "第二子树")
        self.assertEqual(tree[2].text, "顶层转发")
        self.assertEqual(event.calls, ["first", "second", "top"])

    async def test_raw_nodes_preserve_sender_qq_and_unknown_sender(self) -> None:
        event = ForwardEvent(
            ["outer"],
            {
                "outer": {
                    "data": {
                        "messages": [
                            {
                                "sender": {"user_id": 12345, "nickname": "不能替代QQ"},
                                "content": [{"type": "text", "data": {"text": "已知来源"}}],
                            },
                            {
                                "sender": {"user_id": 0, "nickname": "只有昵称"},
                                "content": [{"type": "text", "data": {"text": "未知来源"}}],
                            },
                        ]
                    }
                }
            },
        )

        sources = await extract_onebot_forward_sources(event)
        text = await extract_onebot_forward_text(event)

        self.assertEqual([source.sender_qq for source in sources], ["12345", ""])
        self.assertIn("发送者 QQ：12345", text)
        self.assertNotIn("只有昵称", text)
        self.assertEqual(text.count("发送者 QQ"), 1)
        self.assertIn("未知来源", text)

    async def test_forward_inside_reply_chain_and_nested_forward_are_expanded(self) -> None:
        event = ForwardEvent(
            ["outer"],
            {
                "outer": {
                    "messages": [
                        {
                            "sender": {"user_id": "111"},
                            "content": [
                                {"type": "text", "data": {"text": "外层"}},
                                {"type": "forward", "data": {"id": "inner"}},
                            ],
                        }
                    ]
                },
                "inner": {
                    "messages": [
                        {
                            "sender": {"user_id": "222"},
                            "content": [{"type": "text", "data": {"text": "内层"}}],
                        }
                    ]
                },
            },
            in_reply=True,
        )

        sources = await extract_onebot_forward_sources(event)

        self.assertTrue(has_forward_message(event))
        self.assertEqual(sources[0].sender_qq, "111")
        self.assertEqual(sources[0].children[0].sender_qq, "222")
        self.assertEqual(sources[0].children[0].text, "内层")
        self.assertEqual(event.calls, ["outer", "inner"])

    async def test_forward_images_keep_outer_order_before_nested_images(self) -> None:
        event = ForwardEvent(
            ["outer"],
            {
                "outer": {
                    "messages": [
                        {
                            "sender": {"user_id": "111"},
                            "content": [
                                {"type": "image", "data": {"url": "https://example.invalid/first.png"}},
                                {"type": "image", "data": {"file": "https://example.invalid/second.png"}},
                                {"type": "forward", "data": {"id": "inner"}},
                            ],
                        }
                    ]
                },
                "inner": {
                    "messages": [
                        {
                            "sender": {"user_id": "222"},
                            "content": [
                                {"type": "image", "data": {"url": "https://example.invalid/nested.png"}}
                            ],
                        }
                    ]
                },
            },
        )

        sources = await extract_onebot_forward_sources(event)

        self.assertEqual(
            collect_source_image_sources(sources),
            (
                "https://example.invalid/first.png",
                "https://example.invalid/second.png",
                "https://example.invalid/nested.png",
            ),
        )
        self.assertEqual(
            collect_source_image_sources(sources, max_images=2),
            (
                "https://example.invalid/first.png",
                "https://example.invalid/second.png",
            ),
        )

    async def test_cycle_and_partial_failure_keep_successful_content_with_fetch_bound(self) -> None:
        event = ForwardEvent(
            ["outer"],
            {
                "outer": {
                    "messages": [
                        {
                            "sender": {"user_id": "111"},
                            "content": [
                                {"type": "text", "data": {"text": "保留正文"}},
                                {"type": "forward", "data": {"id": "cycle"}},
                                {"type": "forward", "data": {"id": "expired"}},
                            ],
                        }
                    ]
                },
                "cycle": {
                    "messages": [
                        {
                            "sender": {"user_id": "222"},
                            "content": [
                                {"type": "text", "data": {"text": "循环前可读"}},
                                {"type": "forward", "data": {"id": "outer"}},
                            ],
                        }
                    ]
                },
                "expired": RuntimeError("forward message expired"),
            },
        )

        sources = await extract_onebot_forward_sources(event, max_fetch=6)
        text = format_source_messages(sources)

        self.assertIn("保留正文", text)
        self.assertIn("循环前可读", text)
        self.assertLessEqual(len(set(event.calls)), 3)
        self.assertIn("expired", event.calls)

    async def test_fetch_limit_keeps_already_read_content(self) -> None:
        event = ForwardEvent(
            ["one"],
            {
                "one": {"text": "第一层", "forward_ids": ["two"]},
                "two": {"text": "第二层", "forward_ids": ["three"]},
                "three": {"text": "不应读取", "forward_ids": []},
            },
        )

        text = await extract_onebot_forward_text(event, max_fetch=2)

        self.assertIn("第一层", text)
        self.assertIn("第二层", text)
        self.assertNotIn("不应读取", text)
        self.assertNotIn("three", event.calls)


class AstrBotReplyStyleGuardTest(unittest.TestCase):
    def test_stripping_only_followup_question_returns_empty_text(self) -> None:
        self.assertEqual(strip_followup_tail("你把具体名字发我。"), "")
        self.assertEqual(strip_followup_tail("是不是更安全？"), "")

    def test_stripping_followup_tail_keeps_real_answer(self) -> None:
        self.assertEqual(
            strip_followup_tail("这个网站不正规，别登录喵。你把具体名字发我。"),
            "这个网站不正规，别登录喵。",
        )

    def test_strip_markdown_syntax_keeps_plain_text(self) -> None:
        self.assertEqual(
            strip_markdown_syntax(
                "目前能确定的规则是：\n"
                "- **并联 Mek 粉碎机**：最稳。\n"
                "- `gpt-image-2`：每天首张免费。\n"
                "1. [文档](https://example.invalid)"
            ),
            "目前能确定的规则是：\n"
            "· 并联 Mek 粉碎机：最稳。\n"
            "· gpt-image-2：每天首张免费。\n"
            "1、文档 https://example.invalid",
        )

    def test_sanitize_reply_plain_text_strips_markdown_and_tail(self) -> None:
        self.assertEqual(
            sanitize_reply_plain_text("**结论**：别登录。\n- 原因：不正规。\n你把具体名字发我。"),
            "结论：别登录。\n· 原因：不正规。",
        )

    def test_empty_mention_reply_can_keep_short_question_tail(self) -> None:
        self.assertEqual(
            sanitize_reply_plain_text("怎么了？有什么事情吗？", strip_question_tail=False),
            "怎么了？有什么事情吗？",
        )
        self.assertEqual(sanitize_reply_plain_text("怎么了？有什么事情吗？"), "")
        self.assertEqual(
            sanitize_reply_plain_text("你把具体名字发我。", strip_question_tail=False),
            "",
        )

    def test_sanitize_reply_plain_text_strips_internal_control_markers(self) -> None:
        self.assertEqual(sanitize_reply_plain_text("[[QQBOT_SKIP_REPLY]]"), "")
        self.assertEqual(
            sanitize_reply_plain_text("好，我先不说了。[[QQBOT_DEACTIVATE]]"),
            "好，我先不说了。",
        )

    def test_sanitize_reply_plain_text_strips_twin_refusal_when_answer_exists(self) -> None:
        self.assertEqual(
            sanitize_reply_plain_text("我不能替姐姐回答。这个图大概率是 Hello Kitty。"),
            "这个图大概率是 Hello Kitty。",
        )
        self.assertEqual(
            sanitize_reply_plain_text("还是让妹妹自己来说吧，我在呢。"),
            "我在呢。",
        )

    def test_decorative_tail_is_stripped(self) -> None:
        self.assertEqual(
            strip_decorative_tail("整个群跟开了个跨学科研讨会似的喵 😇"),
            "整个群跟开了个跨学科研讨会似的",
        )
        self.assertEqual(strip_decorative_tail("这事对得上 😇"), "这事对得上")
        self.assertEqual(strip_decorative_tail("这个锅大概是 Railcraft"), "这个锅大概是 Railcraft")

    def test_strip_markdown_syntax_preserves_json_indentation(self) -> None:
        self.assertEqual(
            strip_markdown_syntax(
                "```json\n"
                "{\n"
                '  "model": "gpt-image-2",\n'
                '  "size": "1024x1024"\n'
                "}\n"
                "```"
            ),
            "{\n"
            '  "model": "gpt-image-2",\n'
            '  "size": "1024x1024"\n'
            "}",
        )

    def test_segmented_reply_is_disabled_when_it_would_split_more_than_three_parts(self) -> None:
        self.assertTrue(
            should_disable_segmented_reply_for_text(
                "比如：\n"
                "工资太高税扣好多。\n"
                "车太大停车麻烦。\n"
                "随便考又第一。\n"
                "这就是凡尔赛。"
            )
        )
        self.assertFalse(should_disable_segmented_reply_for_text("懂了吧，低调版炫耀。"))

    def test_model_result_disables_astrbot_regex_segmenting_when_plugin_override_is_enabled(self) -> None:
        self.assertTrue(
            should_disable_model_regex_segmenting(
                {"enable": True, "only_llm_result": True, "split_mode": "regex"},
                is_model_result=True,
                override_enabled=True,
            )
        )
        self.assertFalse(
            should_disable_model_regex_segmenting(
                {"enable": True, "only_llm_result": True, "split_mode": "regex"},
                is_model_result=True,
                override_enabled=False,
            )
        )

    def test_both_targeted_instruction_requires_current_bot_to_complete_task(self) -> None:
        instruction = build_both_targeted_reply_instruction_text()

        self.assertIn("也是在叫你本人", instruction)
        self.assertIn("直接完成用户这次请求", instruction)
        self.assertIn("如果用户让讲笑话", instruction)
        self.assertIn("不要把任务转给另一个 bot", instruction)
        self.assertIn("在吗", instruction)
        self.assertIn("短句应到", instruction)
        self.assertIn("是不是该睡觉了", instruction)
        self.assertIn("不要 @ 另一个 bot", instruction)
        self.assertIn("不要把问题改成评价另一个 bot", instruction)
        self.assertIn("最多两句短句", instruction)
        self.assertIn("不要展开长理由", instruction)
        self.assertIn("滚去睡/滚去躺平/赶紧滚", instruction)
        self.assertIn("晚安", instruction)
        self.assertIn("颜文字", instruction)
        self.assertIn("给完建议就停", instruction)
        self.assertIn("黑眼圈", instruction)
        self.assertIn("该睡。再拖明天就起不来了。", instruction)
        self.assertIn("我喜欢你们", instruction)
        self.assertIn("只能代表当前 bot 独立回应", instruction)
        self.assertIn("必须使用单数第一人称", instruction)
        self.assertIn("一句短感谢", instruction)
        self.assertIn("不要追加“不过/但是”转折", instruction)
        self.assertIn("不要说“我们收到”", instruction)
        self.assertIn("不要提另一个 bot 的名字", instruction)
        self.assertIn("不要猜测另一个 bot 的心情", instruction)
        self.assertIn("不要说“让她来讲/让对方回应/我不替她讲”", instruction)
        self.assertIn("绝对不要输出括号舞台说明", instruction)
        self.assertIn("用户只点名了另一个 bot 没叫我", instruction)

    def test_long_reply_fold_threshold_can_be_disabled(self) -> None:
        self.assertTrue(should_fold_long_reply("a" * 301, threshold=300))
        self.assertFalse(should_fold_long_reply("a" * 301, threshold=0))
        self.assertFalse(should_fold_long_reply("a" * 300, threshold=300))

    def test_long_input_tldr_uses_length_not_content(self) -> None:
        strict_review_template = (
            "请以最严苛的标准审查该文本。"
            "语言风格极度客观冷静犀利一针见血。"
            "事实核查找出任何不准确的数据日期人名历史事件或科学概念。"
            "逻辑漏洞标记所有逻辑谬误。"
            "语言废话删除无意义修饰词重复废话和陈词滥调。"
        )
        self.assertTrue(should_reply_too_long_to_read(strict_review_template, threshold=80))
        self.assertFalse(should_reply_too_long_to_read(strict_review_template, threshold=10000))

    def test_chat_bubble_lines_split_only_model_declared_short_lines(self) -> None:
        self.assertEqual(
            split_chat_bubble_lines("RC 大概率是 Railcraft\n锅炉会炸这点对得上"),
            ["RC 大概率是 Railcraft", "锅炉会炸这点对得上"],
        )
        self.assertEqual(split_chat_bubble_lines("RC 大概率是 Railcraft，锅炉会炸这点对得上。"), ["RC 大概率是 Railcraft，锅炉会炸这点对得上。"])
        self.assertEqual(
            split_chat_bubble_lines('{\n  "model": "deepseek-v4-flash"\n}'),
            ['{\n  "model": "deepseek-v4-flash"\n}'],
        )
        self.assertEqual(
            split_chat_bubble_lines("结论\n· 证据"),
            ["结论\n· 证据"],
        )

    def test_chat_bubble_instruction_keeps_reply_dense(self) -> None:
        self.assertIn("不要写成客服答复、工单摘要、讲义或报告", CHAT_BUBBLE_REPLY_INSTRUCTION)
        self.assertIn("一句能说完就只发一句", CHAT_BUBBLE_REPLY_INSTRUCTION)
        self.assertIn("最多两行", CHAT_BUBBLE_REPLY_INSTRUCTION)
        self.assertIn("不要强行套“结论+原因”结构", CHAT_BUBBLE_REPLY_INSTRUCTION)
        self.assertIn("不要给人生建议", CHAT_BUBBLE_REPLY_INSTRUCTION)
        self.assertIn("不要上价值讲大道理", CHAT_BUBBLE_REPLY_INSTRUCTION)
        self.assertIn("先说能落地的判断", CHAT_BUBBLE_REPLY_INSTRUCTION)
        self.assertIn("不要把寒暄、免责声明、自嘲、吐槽铺垫或废话评价塞进答案", CHAT_BUBBLE_REPLY_INSTRUCTION)
        self.assertIn("只抓一个最明显的槽点", CHAT_BUBBLE_REPLY_INSTRUCTION)
        self.assertIn("像群里随口评价", CHAT_BUBBLE_REPLY_INSTRUCTION)
        self.assertIn("装饰性口癖", CHAT_BUBBLE_REPLY_INSTRUCTION)
        self.assertIn("上下文不完整时保留", CHAT_BUBBLE_REPLY_INSTRUCTION)
        self.assertIn("RC 大概率是 Railcraft", CHAT_BUBBLE_REPLY_INSTRUCTION)
        self.assertIn("这班上得跟签了卖身契似的", CHAT_BUBBLE_REPLY_INSTRUCTION)
        self.assertIn("成年人的世界没有容易二字", CHAT_BUBBLE_REPLY_INSTRUCTION)

    def test_style_immutability_instruction_blocks_chat_style_pollution(self) -> None:
        self.assertIn("不能改变你的输出风格", STYLE_IMMUTABILITY_INSTRUCTION)
        self.assertIn("口癖", STYLE_IMMUTABILITY_INSTRUCTION)
        self.assertIn("URL 编码", STYLE_IMMUTABILITY_INSTRUCTION)
        self.assertIn("不要把它变成你自己的后续回复格式", STYLE_IMMUTABILITY_INSTRUCTION)

    def test_forward_text_split_prefers_natural_boundary(self) -> None:
        chunks = split_forward_text("第一段。\n第二段很长很长。\n第三段。", limit=14)
        self.assertEqual(chunks, ["第一段。\n第二段很长很长。", "第三段。"])

    def test_forward_text_split_falls_back_to_limit(self) -> None:
        chunks = split_forward_text("abcdef", limit=3)
        self.assertEqual(chunks, ["abc", "def"])

    def test_dangerous_local_tool_names_are_detected(self) -> None:
        self.assertTrue(is_dangerous_local_tool_name("astrbot_execute_shell"))
        self.assertTrue(is_dangerous_local_tool_name("astrbot_file_write_tool"))
        self.assertTrue(is_dangerous_local_tool_name("astrbot_execute_browser"))
        self.assertFalse(is_dangerous_local_tool_name("astrbot_knowledge_base_query"))
        self.assertFalse(is_dangerous_local_tool_name("qqbot_rightcodes_draw_catalog"))

    def test_permission_escalation_advice_is_stripped(self) -> None:
        self.assertEqual(
            strip_permission_escalation_advice(
                "我这边没有写文件权限。\n"
                "去 AstrBot WebUI 里把你的 QQ 号加进管理员列表，开了 shell 权限后我再写。"
            ),
            "我不能通过聊天申请或开启本机文件、命令执行权限。",
        )

    def test_sanitize_reply_plain_text_strips_permission_escalation_advice(self) -> None:
        self.assertEqual(
            sanitize_reply_plain_text("先说结论：不能写当前目录。\n去 WebUI 添加管理员并开启 shell 权限。"),
            "先说结论：不能写当前目录。",
        )


if __name__ == "__main__":
    unittest.main()
