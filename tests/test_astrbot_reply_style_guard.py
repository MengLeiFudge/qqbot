from __future__ import annotations

from pathlib import Path
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "astrbot-local-plugins"))


class Plain:
    def __init__(self, text: str = "") -> None:
        self.text = text


class Reply:
    def __init__(self, **kwargs) -> None:
        self.id = kwargs.get("id", "")


class At:
    def __init__(self, **kwargs) -> None:
        self.qq = kwargs.get("qq", "")


class Nodes:
    def __init__(self, nodes=None) -> None:
        self.nodes = nodes or []


class Forward:
    pass


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
        return {"text": "", "forward_ids": []}


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
from astrbot_plugin_qqbot_features.reply_style_guard_logic import build_delegated_reply_instruction_text
from astrbot_plugin_qqbot_features.reply_style_guard_logic import build_both_targeted_reply_instruction_text
from astrbot_plugin_qqbot_features.reply_style_guard_logic import build_delegated_comment_prompt_text
from astrbot_plugin_qqbot_features.reply_style_guard_runtime import decorate_active_reply_source


class AstrBotReplyStyleGuardTest(unittest.TestCase):
    def test_active_reply_source_decorator_prepends_quote_and_at(self) -> None:
        chain = decorate_active_reply_source(
            [Plain("第一条消息"), Plain("第二条消息")],
            quote_message_id="m-100",
            at_user_id="3062317151",
        )

        self.assertIsNotNone(chain)
        self.assertIsInstance(chain[0], Reply)
        self.assertEqual(chain[0].id, "m-100")
        self.assertIsInstance(chain[1], At)
        self.assertEqual(chain[1].qq, "3062317151")
        self.assertEqual(chain[2].text, "第一条消息")
        self.assertEqual(chain[3].text, "第二条消息")

    def test_active_reply_source_decorator_skips_non_plain_chain(self) -> None:
        self.assertIsNone(
            decorate_active_reply_source(
                [Nodes([])],
                quote_message_id="m-100",
                at_user_id="3062317151",
            )
        )

    def test_active_reply_source_decorator_does_not_duplicate_reply(self) -> None:
        self.assertIsNone(
            decorate_active_reply_source(
                [Reply(id="existing"), Plain("正文")],
                quote_message_id="m-100",
                at_user_id="3062317151",
            )
        )

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

    def test_delegated_reply_instruction_mentions_busy_target(self) -> None:
        instruction = build_delegated_reply_instruction_text(
            current_id="1443944862",
            current_name="😇棉花糖😇",
            delegated_from="2629227874",
        )

        self.assertIn("原本被叫到的是 👿棉花糖👿", instruction)
        self.assertIn("现在由 😇棉花糖😇 用自己的身份回答", instruction)
        self.assertIn("不要固定开场", instruction)
        self.assertIn("不要说“我先接一下”", instruction)
        self.assertIn("不要说“我先接一下”“她在忙”", instruction)
        self.assertIn("不要冒充对方", instruction)
        self.assertIn("本轮回复里的“我”必须是当前 bot", instruction)
        self.assertIn("不要编另一个 bot 玩过", instruction)
        self.assertIn("能发截图", instruction)

    def test_both_targeted_instruction_requires_current_bot_to_complete_task(self) -> None:
        instruction = build_both_targeted_reply_instruction_text()

        self.assertIn("也是在叫你本人", instruction)
        self.assertIn("直接完成用户这次请求", instruction)
        self.assertIn("如果用户让讲笑话", instruction)
        self.assertIn("不要把任务转给另一个 bot", instruction)
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

    def test_delegated_comment_prompt_uses_current_target_viewpoint(self) -> None:
        prompt = build_delegated_comment_prompt_text(
            current_id="1443944862",
            responder_id="2629227874",
            original_text="@天使 为什么没有开机指令",
            response_text="姐姐在忙，我替她盯一会儿。",
        )

        self.assertIn("你是 😇棉花糖😇", prompt)
        self.assertIn("原本被用户叫到的姐姐", prompt)
        self.assertIn("👿棉花糖👿 已经用她自己的身份代班回答了", prompt)
        self.assertIn("不要再说自己在忙", prompt)
        self.assertIn("不要把自己描述成正在被别人代班的第三人称", prompt)

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
        self.assertIn("默认只输出一行短气泡", CHAT_BUBBLE_REPLY_INSTRUCTION)
        self.assertIn("最多两行", CHAT_BUBBLE_REPLY_INSTRUCTION)
        self.assertIn("不要把寒暄、免责声明、自嘲、吐槽铺垫或废话评价塞进答案", CHAT_BUBBLE_REPLY_INSTRUCTION)
        self.assertIn("只抓一个最明显的槽点", CHAT_BUBBLE_REPLY_INSTRUCTION)
        self.assertIn("装饰性口癖", CHAT_BUBBLE_REPLY_INSTRUCTION)
        self.assertIn("上下文不完整时保留", CHAT_BUBBLE_REPLY_INSTRUCTION)
        self.assertIn("RC 大概率是 Railcraft", CHAT_BUBBLE_REPLY_INSTRUCTION)

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
