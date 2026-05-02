from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.message_normalizer import normalize_onebot_event, normalize_onebot_message


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
    def __init__(self, message: FakeMessage, sender: FakeSender | None = None) -> None:
        self.message = message
        self.sender = sender or FakeSender()


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
    assert normalized.reply.message.outline == "被引用的文字"
