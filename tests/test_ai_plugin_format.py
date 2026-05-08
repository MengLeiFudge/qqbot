from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.config import RuntimeSettings
from qqbot.plugins.ai_test import (
    build_ai_context,
    build_ai_system_context,
    build_ai_reply_message,
    build_ai_reply_notice_message,
    format_ai_response,
    format_memory_context,
)
from qqbot.services.ai_gateway import AiMetrics, AiResponse
from qqbot.services.ai_group_context_store import AiGroupContextStore
from qqbot.services.chat_memory_store import ChatMemoryFact, ChatMemoryRecord, ChatMemoryStore
from qqbot.services.group_nick_store import GroupNickStore
from qqbot.services.message_normalizer import normalize_onebot_message
from qqbot.services.settings_store import SettingsStore


class FakeGroupEvent:
    message_type = "group"
    group_id = 516286670

    def __init__(
        self,
        user_id: str = "605738729",
        text: str = "总结一下群聊内容",
        reply=None,
        sender=None,
        message=None,
    ) -> None:
        self.user_id = user_id
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
    assert "不要使用 Markdown" in context
    assert "段落之间不要留空行" in context


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
