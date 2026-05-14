from pathlib import Path
import asyncio
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.config import RuntimeSettings
from qqbot.plugins.ai_test import (
    build_ai_context,
    build_memory_retrieval_plan_context,
    build_ai_system_context,
    build_ai_reply_message,
    build_ai_reply_notice_message,
    format_ai_response,
    format_draw_quota_exceeded_message,
    format_draw_start_message,
    format_local_ai_result,
    format_memory_context,
    should_omit_ai_history_for_scope_query,
)
from qqbot.services.ai_gateway import AiMetrics, AiResponse
from qqbot.services.ai_group_context_store import AiGroupContextStore
from qqbot.services.ai_orchestrator import AiOrchestrator, AiOrchestratorContext
from qqbot.services.ai_orchestrator import AiOrchestratorResult
from qqbot.services.chat_memory_store import ChatMemoryFact, ChatMemoryRecord, ChatMemoryStore
from qqbot.services.group_nick_store import GroupNickStore
from qqbot.services.message_normalizer import NormalizedMessage, normalize_onebot_message
from qqbot.services.settings_store import SettingsStore


class FakeGroupEvent:
    message_type = "group"

    def __init__(
        self,
        user_id: str = "605738729",
        text: str = "总结一下群聊内容",
        reply=None,
        sender=None,
        message=None,
        group_id: int = 516286670,
        self_id: int = 1443944862,
    ) -> None:
        self.group_id = group_id
        self.user_id = user_id
        self.self_id = self_id
        self.text = text
        self.reply = reply
        self.sender = sender or FakeSender(user_id=int(user_id), card="萌泪", nickname="MLJ")
        self._message = message

    def get_user_id(self) -> str:
        return self.user_id

    def get_plaintext(self) -> str:
        return self.text

    @property
    def original_message(self):
        if self._message is not None:
            return self._message
        return FakeMessage(self.text)

    @property
    def message(self):
        return self.original_message


class FakePrivateEvent:
    message_type = "private"

    def __init__(
        self,
        user_id: str = "605738729",
        text: str = "你好",
        message=None,
    ) -> None:
        self.user_id = user_id
        self.text = text
        self.sender = FakeSender(user_id=int(user_id), card="", nickname=user_id)
        self._message = message

    def get_user_id(self) -> str:
        return self.user_id

    def get_plaintext(self) -> str:
        return self.text

    @property
    def original_message(self):
        if self._message is not None:
            return self._message
        return FakeMessage(self.text)

    @property
    def message(self):
        return self.original_message


class FakeSender:
    def __init__(
        self,
        user_id: int = 10001,
        card: str = "",
        nickname: str = "用户A",
    ) -> None:
        self.user_id = user_id
        self.card = card
        self.nickname = nickname


class FakeReply:
    def __init__(self, message, sender: FakeSender | None = None) -> None:
        self.message = message
        self.sender = sender or FakeSender()


class FakeSegment:
    def __init__(self, segment_type: str, data: dict[str, str] | None = None) -> None:
        self.type = segment_type
        self.data = data or {}


class FakeMessage:
    def __init__(self, text: str = "", segments: list[FakeSegment] | None = None) -> None:
        self.text = text
        self.segments = segments or []

    def extract_plain_text(self) -> str:
        return self.text

    def __iter__(self):
        if self.segments:
            return iter(self.segments)
        if self.text:
            return iter([FakeSegment("text", {"text": self.text})])
        return iter(())


def test_format_ai_response_hides_metrics_by_default() -> None:
    response = AiResponse(
        text="我是萌萌棉花糖♪。",
        metrics=AiMetrics(
            first_token_seconds=1.64,
            total_seconds=2.01,
            completion_tokens=37,
            output_chars=23,
        ),
    )

    assert format_ai_response("xiaomi", response) == "我是萌萌棉花糖♪。"


def test_format_ai_response_can_show_metrics_for_debug() -> None:
    response = AiResponse(
        text="我是萌萌棉花糖♪。",
        metrics=AiMetrics(
            first_token_seconds=1.64,
            total_seconds=2.01,
            completion_tokens=37,
            output_chars=23,
        ),
    )

    formatted = format_ai_response("xiaomi", response, show_metrics=True)

    assert formatted.startswith("[xiaomi] TTFT 1.64s / total 2.01s")
    assert formatted.endswith("我是萌萌棉花糖♪。")
    assert "\n\n" not in formatted


def test_build_ai_reply_message_quotes_and_mentions_group_sender() -> None:
    message = build_ai_reply_message(
        "你好呀",
        group_id=516286670,
        message_id=12345,
        user_id="605738729",
    )

    assert str(message).startswith("[CQ:reply,id=12345][CQ:at,qq=605738729] ")
    assert str(message).endswith("你好呀")


def test_build_ai_reply_message_keeps_private_response_plain() -> None:
    assert build_ai_reply_message(
        "你好呀",
        group_id=None,
        message_id=12345,
        user_id="605738729",
    ) == "你好呀"


def test_format_local_ai_result_keeps_image_text_without_extra_newline() -> None:
    message = format_local_ai_result(
        AiOrchestratorResult(
            True,
            "✨ 生成成功！",
            image_path="https://example.com/a.png",
        )
    )

    rendered = str(message)
    assert rendered.startswith("[CQ:image,file=https://example.com/a.png")
    assert rendered.endswith("]✨ 生成成功！")
    assert "\n✨ 生成成功！" not in rendered


def test_format_draw_quota_messages_show_current_count() -> None:
    assert format_draw_start_message(3, 5) == "收到，棉花糖开始生图任务啦！这是今天第 3/5 次生图。"
    assert format_draw_quota_exceeded_message(5, 5) == "今天的生图次数已经用完啦（5/5）。明天再来找棉花糖画图吧！"


def test_ai_context_includes_private_memory_only_in_private_chat(tmp_path: Path) -> None:
    memory_store = ChatMemoryStore(tmp_path)
    memory_store.append_message(
        group_id="private:10001",
        space_id="qq:private:10001",
        message_id=8,
        direction="incoming",
        user_id=10001,
        actor_id="qq:user:10001",
        sender_name="10001",
        text="我喜欢写小说。",
        timestamp=8,
        visibility="private",
    )

    context = build_ai_context(
        RuntimeSettings(data_root=tmp_path),
        FakePrivateEvent(user_id="10001", text="我喜欢什么？"),
        AiGroupContextStore(tmp_path),
    )

    joined = "\n".join(context)
    assert "当前对话场景：私聊" in joined
    assert "结构化记忆证据" in joined
    assert '"space_id": "qq:private:10001"' in joined
    assert "我喜欢写小说。" in joined


def test_ai_context_includes_same_user_public_group_memory_in_private_chat(tmp_path: Path) -> None:
    memory_store = ChatMemoryStore(tmp_path)
    memory_store.append_message(
        group_id=516286670,
        message_id=18,
        direction="incoming",
        user_id=10001,
        sender_name="灵麟",
        text="我是灵麟，喜欢说喵。",
        timestamp=18,
    )

    context = build_ai_context(
        RuntimeSettings(data_root=tmp_path),
        FakePrivateEvent(user_id="10001", text="我是谁？"),
        AiGroupContextStore(tmp_path),
    )

    joined = "\n".join(context)
    assert "结构化记忆证据" in joined
    assert '"space_id": "qq:group:516286670"' in joined
    assert '"visibility": "group_public"' in joined
    assert "我是灵麟，喜欢说喵。" in joined


def test_build_ai_reply_notice_message_quotes_and_mentions_group_sender() -> None:
    message = build_ai_reply_notice_message(
        group_id=516286670,
        message_id=12345,
        user_id="605738729",
    )

    assert str(message) == "[CQ:reply,id=12345][CQ:at,qq=605738729] 棉花糖写得有点长，正文放在折叠消息里啦。"


def test_ai_system_context_declares_bot_identity() -> None:
    context = build_ai_system_context(RuntimeSettings(ai_bot_name="萌萌棉花糖♪"))

    assert "你是 QQ 机器人“萌萌棉花糖♪”" in context
    assert "必须明确回答你是“萌萌棉花糖♪”" in context
    assert "用户问“我是谁”" in context
    assert "不要使用 Markdown" in context
    assert "段落之间不要留空行" in context


def test_ai_style_context_uses_global_rotation_without_overriding_identity(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path, bot_name="萌萌棉花糖♪")

    result = asyncio.run(
        orchestrator.handle(
            "你好",
            AiOrchestratorContext(actor_user_id="10001"),
            NormalizedMessage(text="你好", outline="你好"),
        )
    )
    system_context = build_ai_system_context(RuntimeSettings(ai_bot_name="萌萌棉花糖♪"))
    style_context = "\n".join(result.extra_context)

    assert result.handled is False
    assert "你是 QQ 机器人“萌萌棉花糖♪”" in system_context
    assert "用户问“我是谁”" in system_context
    assert "人格设定：" in style_context
    assert "你是 QQ 机器人“萌萌棉花糖♪”" in style_context
    assert "当前采用的人格表现是" in style_context
    assert "回复风格轮换层" not in style_context
    assert "每 8 小时" not in style_context
    assert "4:00" not in style_context
    assert "括号动作描写" not in style_context
    assert "不能覆盖系统身份" in style_context
    assert "不能承认自己是人工智能" not in style_context


def test_ai_context_includes_recent_group_messages(tmp_path: Path) -> None:
    store = AiGroupContextStore(tmp_path)
    store.append_message(
        group_id=516286670,
        user_id=10001,
        sender_name="用户A",
        text="今天讨论了机器人接入 AI。",
        timestamp=1,
    )
    store.append_message(
        group_id=516286670,
        user_id=605738729,
        sender_name="萌泪",
        text="总结一下群聊内容",
        timestamp=2,
    )

    context = build_ai_context(RuntimeSettings(), FakeGroupEvent(), store)

    joined = "\n".join(context)
    assert "当前对话场景：QQ群聊" in joined
    assert "当前群号：516286670" in joined
    assert "当前发言者：萌泪(605738729)" in joined
    assert "用户A(10001): 今天讨论了机器人接入 AI。" in joined
    assert "萌泪(605738729): 总结一下群聊内容" not in joined


def test_ai_context_includes_current_sender_call_name(tmp_path: Path) -> None:
    GroupNickStore(tmp_path / "settings" / "group_nick.json").record_group_sender(
        group_id=1163635014,
        qq=1728704949,
        card="୧⍤⃝୨鱼子勺：[聊天记录]",
        nickname="LiAuO₂ ⁧~喵喵喵 ⁦",
        updated_at=1_800_000_000_000,
    )
    context = build_ai_context(
        RuntimeSettings(data_root=tmp_path),
        FakeGroupEvent(
            group_id=1163635014,
            user_id="1728704949",
            text="我是谁",
            sender=FakeSender(
                user_id=1728704949,
                card="୧⍤⃝୨鱼子勺：[聊天记录]",
                nickname="LiAuO₂ ⁧~喵喵喵 ⁦",
            ),
        ),
        AiGroupContextStore(tmp_path),
    )

    joined = "\n".join(context)
    assert "当前发言者：୧⍤⃝୨鱼子勺：[聊天记录](1728704949)" in joined
    assert "建议称呼当前发言者：鱼子勺" in joined
    assert "不要把其他群友对第三人的称呼纠正当成当前发言者的名字" in joined


def test_ai_context_includes_current_sender_nickname_usage_summary(tmp_path: Path) -> None:
    memory_store = ChatMemoryStore(tmp_path)
    for index, sender_name in enumerate(
        [
            "୧⍤⃝୨鱼子勺：[聊天记录]",
            "୧⍤⃝୨鱼子勺：[聊天记录]",
            "୧⍤⃝୨勺子鱼",
        ],
        start=1,
    ):
        memory_store.append_message(
            group_id=1163635014,
            message_id=f"nickname-{index}",
            direction="incoming",
            user_id=1728704949,
            sender_name=sender_name,
            text=f"历史消息 {index}",
            timestamp=index,
        )

    context = build_ai_context(
        RuntimeSettings(data_root=tmp_path),
        FakeGroupEvent(
            group_id=1163635014,
            user_id="1728704949",
            text="我是谁",
            sender=FakeSender(
                user_id=1728704949,
                card="୧⍤⃝୨鱼子勺：[聊天记录]",
                nickname="LiAuO₂ ⁧~喵喵喵 ⁦",
            ),
        ),
        AiGroupContextStore(tmp_path),
    )

    joined = "\n".join(context)
    assert "当前发言者最近 3 条本人消息的昵称使用统计" in joined
    assert "鱼子勺 2/3 条，占 67%" in joined
    assert "勺子鱼 1/3 条，占 33%" in joined


def test_ai_context_includes_text_identity_query_nickname_candidate(tmp_path: Path) -> None:
    nick_store = GroupNickStore(tmp_path / "settings" / "group_nick.json")
    nick_store.record_group_sender(
        group_id=1163635014,
        qq=273548027,
        card="焰靛燦「YanDarkCollapser」",
        nickname="YanDarkCollapser",
        updated_at=1_800_000_000_000,
    )
    memory_store = ChatMemoryStore(tmp_path)
    for index, sender_name in enumerate(
        [
            "YDC",
            "YDC",
            "焰靛燦「YanDarkCollapser」",
        ],
        start=1,
    ):
        memory_store.append_message(
            group_id=1163635014,
            message_id=f"ydc-{index}",
            direction="incoming",
            user_id=273548027,
            sender_name=sender_name,
            text=f"YDC 历史消息 {index}",
            timestamp=index,
        )

    context = build_ai_context(
        RuntimeSettings(data_root=tmp_path),
        FakeGroupEvent(
            group_id=1163635014,
            user_id="605738729",
            text="你知道YDC是谁吗",
            sender=FakeSender(user_id=605738729, card="萌泪酱最可爱啦๑", nickname="萌泪"),
        ),
        AiGroupContextStore(tmp_path),
    )

    joined = "\n".join(context)
    assert "本次纯文本称呼身份查询证据" in joined
    assert "查询称呼：YDC" in joined
    assert "候选用户：焰靛燦「YanDarkCollapser」(273548027)" in joined
    assert "匹配称呼：YDC" in joined
    assert "最近 3 条本人消息的昵称使用统计：YDC 2/3 条，占 67%" in joined


def test_ai_context_includes_long_term_memory_search_results(tmp_path: Path) -> None:
    memory_store = ChatMemoryStore(tmp_path)
    memory_store.append_message(
        group_id=516286670,
        message_id=10,
        direction="incoming",
        user_id=10001,
        sender_name="可可",
        text="之前讨论过 shapez 数据库要按聊天记录打标签。",
        timestamp=1,
    )

    context = build_ai_context(
        RuntimeSettings(data_root=tmp_path),
        FakeGroupEvent(text="shapez 数据库怎么做"),
        AiGroupContextStore(tmp_path),
    )

    joined = "\n".join(context)
    assert "长期记忆检索结果" in joined
    assert "可可(10001): 之前讨论过 shapez 数据库要按聊天记录打标签。" in joined


def test_ai_context_omits_long_term_memory_when_no_result(tmp_path: Path) -> None:
    context = build_ai_context(
        RuntimeSettings(data_root=tmp_path),
        FakeGroupEvent(text="今天吃什么"),
        AiGroupContextStore(tmp_path),
    )

    assert "长期记忆检索结果" not in "\n".join(context)


def test_ai_context_separates_memory_facts_from_source_messages(tmp_path: Path) -> None:
    memory_store = ChatMemoryStore(tmp_path)
    memory_store.append_message(
        group_id=516286670,
        message_id=10,
        direction="incoming",
        user_id=10001,
        sender_name="可可",
        text="可可喜欢研究 shapez 数据库。",
        timestamp=1,
    )
    memory_store.extract_facts_from_recent_messages(516286670, limit=10)

    context = build_ai_context(
        RuntimeSettings(data_root=tmp_path),
        FakeGroupEvent(text="可可喜欢什么"),
        AiGroupContextStore(tmp_path),
    )

    joined = "\n".join(context)
    assert "长期事实记忆" in joined
    assert "相关历史原文" in joined
    assert joined.index("长期事实记忆") < joined.index("相关历史原文")
    assert "可可 喜欢 研究 shapez 数据库" in joined
    assert "可可(10001): 可可喜欢研究 shapez 数据库。" in joined


def test_ai_context_includes_fact_source_message_even_when_query_matches_only_fact(tmp_path: Path) -> None:
    memory_store = ChatMemoryStore(tmp_path)
    memory_store.append_message(
        group_id=516286670,
        message_id=11,
        direction="incoming",
        user_id=10001,
        sender_name="可可",
        text="可可叫糖糖。",
        timestamp=1,
    )

    context = build_ai_context(
        RuntimeSettings(data_root=tmp_path),
        FakeGroupEvent(text="糖糖是谁"),
        AiGroupContextStore(tmp_path),
    )

    joined = "\n".join(context)
    assert "可可 昵称 糖糖" in joined
    assert "可可(10001): 可可叫糖糖。" in joined


def test_ai_context_includes_current_sender_memory_across_groups(tmp_path: Path) -> None:
    memory_store = ChatMemoryStore(tmp_path)
    memory_store.append_message(
        group_id=10001,
        message_id=21,
        direction="incoming",
        user_id=10001,
        sender_name="可可",
        text="可可喜欢研究 shapez 存档。",
        timestamp=1,
    )
    memory_store.append_message(
        group_id=516286670,
        message_id=22,
        direction="incoming",
        user_id=10002,
        sender_name="路人",
        text="路人喜欢研究 shapez 存档。",
        timestamp=2,
    )
    memory_store.append_message(
        group_id=10003,
        message_id=23,
        direction="incoming",
        user_id=10001,
        sender_name="可可",
        text="以后规则是不要刷屏。",
        timestamp=3,
    )

    context = build_ai_context(
        RuntimeSettings(data_root=tmp_path),
        FakeGroupEvent(
            user_id="10001",
            text="我之前喜欢研究什么",
            sender=FakeSender(user_id=10001, card="可可"),
        ),
        AiGroupContextStore(tmp_path),
    )

    joined = "\n".join(context)
    assert "当前发言者跨群长期记忆" in joined
    sender_memory = joined.split("当前发言者跨群长期记忆", 1)[1]
    assert "可可 喜欢 研究 shapez 存档" in joined
    assert "可可(10001) 在群 10001 说： 可可喜欢研究 shapez 存档。" in joined
    assert "路人喜欢研究 shapez 存档" not in sender_memory
    assert "不要刷屏" not in sender_memory


def test_ai_scope_query_omits_current_group_short_history() -> None:
    event = FakeGroupEvent(text="我刚刚和你在另一个群说了什么？")
    normalized = normalize_onebot_message(FakeMessage("我刚刚和你在另一个群说了什么？"))

    assert should_omit_ai_history_for_scope_query(event, normalized) is True


def test_ai_context_warns_cross_group_query_cannot_use_current_group_history(
    tmp_path: Path,
) -> None:
    context = build_ai_context(
        RuntimeSettings(data_root=tmp_path),
        FakeGroupEvent(text="我刚刚和你在另一个群说了什么？"),
        AiGroupContextStore(tmp_path),
    )

    joined = "\n".join(context)
    assert "当前短期会话历史和本群最近聊天记录都不是其他群证据" in joined
    assert "只能依据明确标注为“当前发言者跨群长期记忆”的内容回答" in joined


def test_ai_cross_group_scope_query_includes_recent_sender_messages(
    tmp_path: Path,
) -> None:
    memory_store = ChatMemoryStore(tmp_path)
    memory_store.append_message(
        group_id=10001,
        message_id=31,
        direction="incoming",
        user_id=10001,
        sender_name="可可",
        text="喵喵喵",
        timestamp=31,
    )
    memory_store.append_message(
        group_id=10002,
        message_id=32,
        direction="incoming",
        user_id=10001,
        sender_name="可可",
        text="我刚刚在另一个群说什么了？",
        timestamp=32,
    )

    context = build_ai_context(
        RuntimeSettings(data_root=tmp_path),
        FakeGroupEvent(
            user_id="10001",
            text="我刚刚在另一个群说什么了？",
            sender=FakeSender(user_id=10001, card="可可"),
            group_id=10002,
        ),
        AiGroupContextStore(tmp_path),
    )

    joined = "\n".join(context)
    assert "当前发言者跨群长期记忆" in joined
    assert "可可(10001) 在群 10001 说： 喵喵喵" in joined
    assert "本群长期记忆" not in joined
    sender_memory = joined.rsplit("当前发言者跨群长期记忆", 1)[1]
    assert "我刚刚在另一个群说什么了？" not in sender_memory


def test_ai_context_refuses_private_memory_in_group(tmp_path: Path) -> None:
    context = build_ai_context(
        RuntimeSettings(data_root=tmp_path),
        FakeGroupEvent(text="我和你私聊里说了什么？"),
        AiGroupContextStore(tmp_path),
    )

    joined = "\n".join(context)
    assert "不要在群聊里查看、复述或暗示任何私聊历史" in joined


def test_ai_context_uses_private_profile_facts_without_private_messages_in_group(
    tmp_path: Path,
) -> None:
    memory_store = ChatMemoryStore(tmp_path)
    memory_store.append_message(
        group_id="private:10001",
        space_id="qq:private:10001",
        message_id=41,
        direction="incoming",
        user_id=10001,
        actor_id="qq:user:10001",
        sender_name="灵麟",
        text="灵麟喜欢说喵。",
        timestamp=41,
        visibility="private",
    )
    memory_store.append_message(
        group_id="private:10001",
        space_id="qq:private:10001",
        message_id=42,
        direction="incoming",
        user_id=10001,
        actor_id="qq:user:10001",
        sender_name="灵麟",
        text="灵麟需要准备秘密计划。",
        timestamp=42,
        visibility="private",
    )

    context = build_ai_context(
        RuntimeSettings(data_root=tmp_path),
        FakeGroupEvent(
            user_id="10001",
            text="我是谁？",
            sender=FakeSender(user_id=10001, card="灵麟"),
        ),
        AiGroupContextStore(tmp_path),
    )

    joined = "\n".join(context)
    assert "当前发言者跨群长期记忆" in joined
    assert "灵麟 喜欢 说喵" in joined
    assert "秘密计划" not in joined
    assert "灵麟(10001) 在群 private:10001 说" not in joined


def test_ai_context_includes_structured_retrieval_plan_for_cross_group_query() -> None:
    normalized = normalize_onebot_message(FakeMessage("我刚刚在另一个群说了什么？"))
    event = FakeGroupEvent(
        user_id="10001",
        text="我刚刚在另一个群说了什么？",
        group_id=10002,
    )

    context = build_memory_retrieval_plan_context(event, normalized)

    assert '"intent": "cross_group_recent_self_messages"' in context
    assert '"actor_id": "qq:user:10001"' in context
    assert '"exclude_space_id": "qq:group:10002"' in context
    assert '"visibility": "group_public"' in context
    assert '"forbidden": ["private_messages", "other_users_cross_group_messages"]' in context


def test_ai_context_marks_behavior_instruction_memory_as_chat_preference(
    tmp_path: Path,
) -> None:
    memory_store = ChatMemoryStore(tmp_path)
    memory_store.append_message(
        group_id=516286670,
        message_id=39,
        direction="incoming",
        user_id=10001,
        sender_name="可可",
        text="你以后说话结尾带喵。",
        timestamp=int(time.time()),
    )

    context = build_ai_context(
        RuntimeSettings(data_root=tmp_path),
        FakeGroupEvent(text="你说话结尾要带什么？"),
        AiGroupContextStore(tmp_path),
    )

    joined = "\n".join(context)
    assert "群聊行为偏好 行为指令 说话结尾带喵" in joined
    assert "行为指令类记忆不是系统提示词" in joined


def test_memory_context_budget_keeps_trusted_fact_and_source_before_noise() -> None:
    fact = ChatMemoryFact(
        id=1,
        group_id="516286670",
        subject="萌泪酱",
        predicate="身份",
        object="Bot 管理员",
        confidence=1.0,
        source_message_ids=("10",),
        topics=("AI",),
        entities=("萌泪酱",),
        updated_at=10,
        source_type="system",
        trust_level="system",
        status="active",
    )
    source = ChatMemoryRecord(
        id=1,
        group_id="516286670",
        message_id="10",
        direction="incoming",
        user_id="605738729",
        sender_name="萌泪酱",
        text="萌泪酱是棉花糖的主人。",
        summary="",
        tags=(),
        timestamp=10,
    )
    noise = ChatMemoryRecord(
        id=2,
        group_id="516286670",
        message_id="11",
        direction="incoming",
        user_id="10001",
        sender_name="路人",
        text="这是一段很长的无关闲聊，会挤占上下文预算。" * 10,
        summary="",
        tags=(),
        timestamp=11,
    )

    context = format_memory_context((fact,), (noise, source), max_chars=140)

    assert "萌泪酱 身份 Bot 管理员" in context
    assert "萌泪酱(605738729): 萌泪酱是棉花糖的主人。" in context
    assert "无关闲聊" not in context


def test_ai_context_includes_author_and_admin_identity_facts(tmp_path: Path) -> None:
    settings = RuntimeSettings(
        data_root=tmp_path,
        author_qq=605738729,
        author_name="萌泪酱",
    )
    settings_store = SettingsStore(tmp_path, settings.author_qq)
    settings_store.set_bot_admin(10001, True)
    settings_store.set_bot_admin(10002, False)
    nick_store = GroupNickStore(tmp_path / "settings" / "group_nick.json")
    nick_store.record_group_sender(
        group_id=516286670,
        qq=10001,
        card="棉花糖管理员",
        nickname="",
        updated_at=1,
    )

    context = build_ai_context(
        settings,
        FakeGroupEvent(user_id="605738729", sender=FakeSender(user_id=605738729, card="萌泪")),
        AiGroupContextStore(tmp_path),
        settings_store=settings_store,
    )

    joined = "\n".join(context)
    assert "Bot 作者/主人：萌泪酱(605738729)" in joined
    assert "Bot 管理员列表：萌泪酱(605738729)、棉花糖管理员(10001)" in joined
    assert "当前发言者身份：Bot 作者/主人" in joined
    assert "10002" not in joined
    assert "别人问“萌泪酱是你的什么人”" in joined


def test_ai_context_marks_current_sender_as_bot_admin(tmp_path: Path) -> None:
    settings = RuntimeSettings(
        data_root=tmp_path,
        author_qq=605738729,
        author_name="萌泪酱",
    )
    settings_store = SettingsStore(tmp_path, settings.author_qq)
    settings_store.set_bot_admin(10001, True)

    context = build_ai_context(
        settings,
        FakeGroupEvent(user_id="10001", sender=FakeSender(user_id=10001, card="管理员A")),
        AiGroupContextStore(tmp_path),
        settings_store=settings_store,
    )

    joined = "\n".join(context)
    assert "当前发言者身份：Bot 管理员" in joined


def test_ai_context_includes_quoted_reply_text(tmp_path: Path) -> None:
    store = AiGroupContextStore(tmp_path)
    reply = FakeReply(
        FakeMessage("这是一条被引用的消息"),
        FakeSender(user_id=10002, card="群友B"),
    )

    context = build_ai_context(
        RuntimeSettings(),
        FakeGroupEvent(text="看看这个是什么", reply=reply),
        store,
    )

    joined = "\n".join(context)
    assert "用户这次消息引用了下面这条消息" in joined
    assert "群友B(10002): 这是一条被引用的消息" in joined


def test_normalized_message_marks_images_in_outline() -> None:
    normalized = normalize_onebot_message(
        FakeMessage(segments=[FakeSegment("image", {"url": "https://example.invalid/a.png"})])
    )

    assert normalized.outline == "[图片]"
    assert normalized.image_urls == ("https://example.invalid/a.png",)


def test_ai_context_describes_current_message_structure(tmp_path: Path) -> None:
    store = AiGroupContextStore(tmp_path)
    message = FakeMessage(
        segments=[
            FakeSegment("at", {"qq": "10002"}),
            FakeSegment("text", {"text": " 看看这个"}),
            FakeSegment("image", {"url": "https://example.invalid/a.png"}),
            FakeSegment("record", {"url": "https://example.invalid/a.amr"}),
            FakeSegment("video", {"url": "https://example.invalid/a.mp4"}),
        ]
    )

    context = build_ai_context(
        RuntimeSettings(data_root=tmp_path),
        FakeGroupEvent(text="看看这个", message=message),
        store,
    )

    joined = "\n".join(context)
    assert "本次消息概要：[@10002] 看看这个 [图片] [语音] [视频]" in joined
    assert "本次消息 @ 了：10002" in joined
    assert "用户本次消息包含图片" in joined
    assert "用户本次消息包含语音" in joined
    assert "用户本次消息包含视频" in joined


def test_ai_context_includes_at_target_nickname_usage_summary(tmp_path: Path) -> None:
    nick_store = GroupNickStore(tmp_path / "settings" / "group_nick.json")
    nick_store.record_group_sender(
        group_id=1163635014,
        qq=1728704949,
        card="୧⍤⃝୨鱼子勺：[聊天记录]",
        nickname="LiAuO₂ ⁧~喵喵喵 ⁦",
        updated_at=1_800_000_000_000,
    )
    memory_store = ChatMemoryStore(tmp_path)
    for index, sender_name in enumerate(
        [
            "୧⍤⃝୨鱼子勺：[聊天记录]",
            "୧⍤⃝୨鱼子勺：[聊天记录]",
            "୧⍤⃝୨勺子鱼",
        ],
        start=1,
    ):
        memory_store.append_message(
            group_id=1163635014,
            message_id=f"at-target-{index}",
            direction="incoming",
            user_id=1728704949,
            sender_name=sender_name,
            text=f"目标历史消息 {index}",
            timestamp=index,
        )
    message = FakeMessage(
        segments=[
            FakeSegment("at", {"qq": "1443944862"}),
            FakeSegment("text", {"text": " 你知道"}),
            FakeSegment("at", {"qq": "1728704949"}),
            FakeSegment("text", {"text": " 是谁吗"}),
        ]
    )

    context = build_ai_context(
        RuntimeSettings(data_root=tmp_path),
        FakeGroupEvent(
            group_id=1163635014,
            user_id="605738729",
            text="你知道 是谁吗",
            message=message,
        ),
        AiGroupContextStore(tmp_path),
    )

    joined = "\n".join(context)
    assert "本次消息 @ 的目标用户身份证据" in joined
    assert "目标用户：鱼子勺(1728704949)" in joined
    assert "最近 3 条本人消息的昵称使用统计：鱼子勺 2/3 条，占 67%；勺子鱼 1/3 条，占 33%" in joined


def test_ai_context_limits_identity_query_to_current_at_target(tmp_path: Path) -> None:
    GroupNickStore(tmp_path / "settings" / "group_nick.json").record_group_sender(
        group_id=1163635014,
        qq=605738729,
        card="萌泪酱最可爱啦๑",
        nickname="萌泪酱最可爱啦๑",
        updated_at=1_800_000_000_000,
    )
    group_context_store = AiGroupContextStore(tmp_path)
    group_context_store.append_message(
        group_id=1163635014,
        user_id=1728704949,
        sender_name="୧⍤⃝୨勺子鱼的德军旗队长",
        text="我也在聊天记录里",
        timestamp=1,
    )
    message = FakeMessage(
        segments=[
            FakeSegment("at", {"qq": "1443944862"}),
            FakeSegment("text", {"text": " 你知道"}),
            FakeSegment("at", {"qq": "605738729"}),
            FakeSegment("text", {"text": " 是谁吗"}),
        ]
    )

    context = build_ai_context(
        RuntimeSettings(data_root=tmp_path),
        FakeGroupEvent(
            group_id=1163635014,
            user_id="2633301937",
            text="你知道 是谁吗",
            message=message,
            self_id=1443944862,
        ),
        group_context_store,
    )

    joined = "\n".join(context)
    assert "本轮是在询问被 @ 的目标用户身份；本轮身份查询目标只有：605738729。" in joined
    assert "不要把最近聊天记录里的其他 QQ 号当作本轮问题答案" in joined
    target_block = joined.split("本次消息 @ 的目标用户身份证据", 1)[1]
    assert "目标用户：萌泪酱最可爱啦๑(605738729)" in target_block
    assert "1728704949" not in target_block.split("回答“@某人是谁”时", 1)[0]
