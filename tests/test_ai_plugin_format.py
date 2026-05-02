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
    format_ai_response,
)
from qqbot.services.ai_gateway import AiMetrics, AiResponse
from qqbot.services.ai_group_context_store import AiGroupContextStore
from qqbot.services.message_normalizer import normalize_onebot_message


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
