import asyncio
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.message_normalizer import (
    normalize_onebot_event,
    normalize_onebot_event_with_fetcher,
    normalize_onebot_message,
)


class FakeSegment:
    def __init__(self, segment_type: str, data: dict[str, str] | None = None) -> None:
        self.type = segment_type
        self.data = data or {}


class FakeMessage:
    def __init__(self, segments: list[FakeSegment]) -> None:
        self.segments = segments

    def extract_plain_text(self) -> str:
        return "".join(
            segment.data.get("text", "")
            for segment in self.segments
            if segment.type == "text"
        )

    def __iter__(self):
        return iter(self.segments)


class FakeSender:
    def __init__(self, user_id: int = 10001, card: str = "", nickname: str = "群友") -> None:
        self.user_id = user_id
        self.card = card
        self.nickname = nickname


class FakeReply:
    def __init__(self, message: FakeMessage, sender: FakeSender | None = None, message_id: int = 114) -> None:
        self.message = message
        self.sender = sender or FakeSender()
        self.message_id = message_id


class FakeEvent:
    message_type = "group"
    group_id = 516286670
    message_id = 233
    time = 1_800_000_000

    def __init__(
        self,
        message: FakeMessage,
        reply: FakeReply | None = None,
        sender: FakeSender | None = None,
    ) -> None:
        self.message = message
        self.original_message = message
        self.reply = reply
        self.sender = sender or FakeSender(user_id=605738729, card="萌泪")

    def get_user_id(self) -> str:
        return str(self.sender.user_id)

    def get_plaintext(self) -> str:
        return self.message.extract_plain_text()


def test_normalize_onebot_message_collects_text_at_and_image() -> None:
    message = FakeMessage(
        [
            FakeSegment("at", {"qq": "114514"}),
            FakeSegment("text", {"text": " 看看这个"}),
            FakeSegment("image", {"url": "https://example.invalid/a.png"}),
        ]
    )

    normalized = normalize_onebot_message(message)

    assert normalized.text == "看看这个"
    assert normalized.outline == "[@114514] 看看这个 [图片]"
    assert normalized.image_urls == ("https://example.invalid/a.png",)
    assert normalized.at_user_ids == ("114514",)


def test_normalize_onebot_message_uses_file_name_in_outline() -> None:
    message = FakeMessage([FakeSegment("file", {"name": "报告.pdf"})])

    normalized = normalize_onebot_message(message)

    assert normalized.text == ""
    assert normalized.outline == "[文件：报告.pdf]"


def test_normalize_onebot_message_collects_audio_and_video_urls() -> None:
    message = FakeMessage(
        [
            FakeSegment("record", {"url": "https://example.invalid/a.amr"}),
            FakeSegment("video", {"url": "https://example.invalid/a.mp4"}),
        ]
    )

    normalized = normalize_onebot_message(message)

    assert normalized.outline == "[语音] [视频]"
    assert normalized.audio_urls == ("https://example.invalid/a.amr",)
    assert normalized.video_urls == ("https://example.invalid/a.mp4",)


def test_normalize_onebot_event_includes_reply_message() -> None:
    event = FakeEvent(
        FakeMessage([FakeSegment("text", {"text": "看看这个是什么"})]),
        reply=FakeReply(
            FakeMessage([FakeSegment("text", {"text": "被引用的文字"})]),
            sender=FakeSender(user_id=10002, card="群友B"),
        ),
    )

    normalized = normalize_onebot_event(event)

    assert normalized.text == "看看这个是什么"
    assert normalized.reply is not None
    assert normalized.reply.sender_name == "群友B"
    assert normalized.reply.user_id == "10002"
    assert normalized.reply.message_id == "114"
    assert normalized.reply.message.outline == "被引用的文字"


def test_normalize_onebot_event_expands_quoted_forward_message() -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    async def fetcher(api: str, **data: object) -> object:
        calls.append((api, data))
        if api == "get_msg":
            assert data == {"message_id": 114}
            return {
                "message_id": 114,
                "sender": {"user_id": 10002, "card": "群友B"},
                "message": [{"type": "forward", "data": {"id": "forward-1"}}],
            }
        if api == "get_forward_msg":
            assert data == {"id": "forward-1"}
            return {
                "messages": [
                    {
                        "sender": {"user_id": 10003, "nickname": "梦想天生"},
                        "message": [{"type": "text", "data": {"text": "llo：LoveLive Only展"}}],
                    },
                    {
                        "sender": {"user_id": 10004, "nickname": "柆雨"},
                        "message": [{"type": "text", "data": {"text": "你能理解这个聊天记录吗"}}],
                    },
                ]
            }
        raise AssertionError(api)

    event = FakeEvent(
        FakeMessage([FakeSegment("text", {"text": "看看这个是什么"})]),
        reply=FakeReply(
            FakeMessage([FakeSegment("text", {"text": "[聊天记录]"})]),
            sender=FakeSender(user_id=10002, card="群友B"),
        ),
    )

    normalized = asyncio.run(normalize_onebot_event_with_fetcher(event, fetcher))

    assert normalized.reply is not None
    assert normalized.reply.sender_name == "群友B"
    assert normalized.reply.message.outline == (
        "梦想天生(10003): llo：LoveLive Only展\n"
        "柆雨(10004): 你能理解这个聊天记录吗"
    )
    assert calls == [
        ("get_msg", {"message_id": 114}),
        ("get_forward_msg", {"id": "forward-1"}),
    ]


def test_normalize_onebot_event_expands_nested_forward_nodes() -> None:
    async def fetcher(api: str, **data: object) -> object:
        if api == "get_msg":
            return {
                "message_id": 114,
                "sender": {"user_id": 10002, "nickname": "群友B"},
                "message": [{"type": "forward", "data": {"id": "outer"}}],
            }
        if api == "get_forward_msg" and data == {"id": "outer"}:
            return {
                "messages": [
                    {
                        "sender": {"user_id": 10003, "nickname": "梦想天生"},
                        "message": [{"type": "forward", "data": {"id": "inner"}}],
                    }
                ]
            }
        if api == "get_forward_msg" and data == {"id": "inner"}:
            return {
                "messages": [
                    {
                        "sender": {"user_id": 10004, "nickname": "柆雨"},
                        "message": [{"type": "text", "data": {"text": "ota 是打 call 观众"}}],
                    }
                ]
            }
        raise AssertionError((api, data))

    event = FakeEvent(
        FakeMessage([FakeSegment("text", {"text": "能理解吗"})]),
        reply=FakeReply(FakeMessage([FakeSegment("text", {"text": "[聊天记录]"})])),
    )

    normalized = asyncio.run(normalize_onebot_event_with_fetcher(event, fetcher))

    assert normalized.reply is not None
    assert normalized.reply.message.outline == "梦想天生(10003): 柆雨(10004): ota 是打 call 观众"


def test_normalize_onebot_event_expands_onebot_node_segment_shape() -> None:
    async def fetcher(api: str, **data: object) -> object:
        if api == "get_msg":
            return {
                "message_id": 114,
                "sender": {"user_id": 10002, "nickname": "群友B"},
                "message": [{"type": "forward", "data": {"id": "forward-1"}}],
            }
        if api == "get_forward_msg":
            return {
                "messages": [
                    {
                        "type": "node",
                        "data": {
                            "name": "梦想天生",
                            "uin": "10003",
                            "content": [{"type": "text", "data": {"text": "ij 是北京 IJOY 漫展"}}],
                        },
                    }
                ]
            }
        raise AssertionError((api, data))

    event = FakeEvent(
        FakeMessage([FakeSegment("text", {"text": "能理解吗"})]),
        reply=FakeReply(FakeMessage([FakeSegment("text", {"text": "[聊天记录]"})])),
    )

    normalized = asyncio.run(normalize_onebot_event_with_fetcher(event, fetcher))

    assert normalized.reply is not None
    assert normalized.reply.message.outline == "梦想天生(10003): ij 是北京 IJOY 漫展"


def test_normalize_onebot_event_keeps_forward_placeholder_when_api_fails() -> None:
    async def fetcher(api: str, **data: object) -> object:
        if api == "get_msg":
            return {
                "message_id": 114,
                "sender": {"user_id": 10002, "nickname": "群友B"},
                "message": [{"type": "forward", "data": {"id": "forward-1"}}],
            }
        raise RuntimeError("forward api unavailable")

    event = FakeEvent(
        FakeMessage([FakeSegment("text", {"text": "能理解吗"})]),
        reply=FakeReply(FakeMessage([FakeSegment("text", {"text": "[聊天记录]"})])),
    )

    normalized = asyncio.run(normalize_onebot_event_with_fetcher(event, fetcher))

    assert normalized.reply is not None
    assert normalized.reply.message.outline == "[聊天记录]"


def test_normalize_onebot_event_keeps_reply_sender_when_get_msg_has_no_sender() -> None:
    async def fetcher(api: str, **data: object) -> object:
        if api == "get_msg":
            return {
                "message_id": 114,
                "message": [{"type": "text", "data": {"text": "被引用的文字"}}],
            }
        raise AssertionError((api, data))

    event = FakeEvent(
        FakeMessage([FakeSegment("text", {"text": "看看这个是什么"})]),
        reply=FakeReply(
            FakeMessage([FakeSegment("text", {"text": "旧内容"})]),
            sender=FakeSender(user_id=10002, card="群友B"),
        ),
    )

    normalized = asyncio.run(normalize_onebot_event_with_fetcher(event, fetcher))

    assert normalized.reply is not None
    assert normalized.reply.sender_name == "群友B"
    assert normalized.reply.user_id == "10002"
    assert normalized.reply.message.outline == "被引用的文字"
