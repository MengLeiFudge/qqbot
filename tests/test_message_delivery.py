import asyncio
from pathlib import Path

from qqbot.services.message_delivery import (
    FORWARD_NODE_TEXT_CHARS,
    MAX_TEXT_MESSAGE_CHARS,
    call_record_api,
    call_collapsible_text_api,
    call_split_text_api,
    finish_split_text,
    has_waited_group_message_interval,
    reset_group_message_interval_state,
    split_text_message,
    wait_for_group_message_interval,
)


class FakeMatcher:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.finished: list[str] = []

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def finish(self, message: str | None = None) -> None:
        if message is not None:
            self.finished.append(message)


class FakeBot:
    def __init__(self) -> None:
        self.self_id = 1443944862
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.interval_flags: list[bool] = []

    async def call_api(self, api: str, **data: object) -> None:
        self.interval_flags.append(has_waited_group_message_interval())
        self.calls.append((api, data))


class FailingForwardBot(FakeBot):
    async def call_api(self, api: str, **data: object) -> None:
        if api == "send_group_forward_msg":
            raise RuntimeError("forward disabled")
        await super().call_api(api, **data)


def test_split_text_message_keeps_short_text_unchanged() -> None:
    assert split_text_message("短消息") == ["短消息"]


def test_split_text_message_splits_long_text_with_part_markers() -> None:
    message = "long text " * 150

    chunks = split_text_message(message)

    assert len(chunks) == 2
    assert chunks[0].startswith("（1/2）\n")
    assert chunks[1].startswith("（2/2）\n")
    assert all(len(chunk) <= MAX_TEXT_MESSAGE_CHARS for chunk in chunks)


def test_finish_split_text_sends_prefix_chunks_before_finish() -> None:
    matcher = FakeMatcher()
    message = "0123456789" * 130

    asyncio.run(finish_split_text(matcher, message))

    assert len(matcher.sent) == 1
    assert len(matcher.finished) == 1
    assert matcher.sent[0].startswith("（1/2）\n")
    assert matcher.finished[0].startswith("（2/2）\n")


def test_finish_split_text_uses_group_forward_when_text_exceeds_200_chars() -> None:
    reset_group_message_interval_state()
    bot = FakeBot()
    matcher = FakeMatcher()
    message = "x" * 201

    asyncio.run(
        finish_split_text(
            matcher,
            message,
            group_id=10001,
            bot=bot,
            title="AI 回复",
        )
    )

    assert matcher.sent == []
    assert matcher.finished == []
    assert len(bot.calls) == 1
    api, data = bot.calls[0]
    assert api == "send_group_forward_msg"
    assert data["group_id"] == 10001
    assert data["messages"][0]["data"]["name"] == "AI 回复"
    assert data["messages"][0]["data"]["content"] == message


def test_finish_split_text_keeps_200_chars_as_normal_message() -> None:
    bot = FakeBot()
    matcher = FakeMatcher()
    message = "x" * 200

    asyncio.run(finish_split_text(matcher, message, group_id=10001, bot=bot))

    assert bot.calls == []
    assert matcher.finished == [message]


def test_call_split_text_api_sends_each_chunk() -> None:
    reset_group_message_interval_state()
    sleep_calls: list[float] = []
    bot = FakeBot()
    message = "long text " * 150

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    asyncio.run(
        call_split_text_api(
            bot,
            "send_group_msg",
            group_id=10001,
            message=message,
            group_interval_sleep=fake_sleep,
        )
    )

    assert len(bot.calls) == 2
    assert len(sleep_calls) == 1
    assert 0 < sleep_calls[0] <= 0.5
    assert {call[0] for call in bot.calls} == {"send_group_msg"}
    assert {call[1]["group_id"] for call in bot.calls} == {10001}
    assert bot.calls[0][1]["message"].startswith("（1/2）\n")
    assert bot.calls[1][1]["message"].startswith("（2/2）\n")
    assert bot.interval_flags == [True, True]


def test_call_collapsible_text_api_uses_group_forward_for_long_text() -> None:
    reset_group_message_interval_state()
    bot = FakeBot()
    message = "long text " * 500

    asyncio.run(
        call_collapsible_text_api(
            bot,
            "send_group_msg",
            group_id=10001,
            message=message,
            title="Codex 回报",
        )
    )

    assert len(bot.calls) == 1
    api, data = bot.calls[0]
    assert api == "send_group_forward_msg"
    assert data["group_id"] == 10001
    assert data["messages"][0]["type"] == "node"
    assert data["messages"][0]["data"]["name"] == "Codex 回报"
    assert "long text" in data["messages"][0]["data"]["content"]
    assert bot.interval_flags == [True]


def test_call_collapsible_text_api_splits_forward_nodes_without_part_markers() -> None:
    reset_group_message_interval_state()
    bot = FakeBot()
    message = "long text " * 500

    asyncio.run(
        call_collapsible_text_api(
            bot,
            "send_group_msg",
            group_id=10001,
            message=message,
        )
    )

    nodes = bot.calls[0][1]["messages"]
    assert len(nodes) > 1
    assert all(len(node["data"]["content"]) <= FORWARD_NODE_TEXT_CHARS for node in nodes)
    assert not nodes[0]["data"]["content"].startswith("（1/")
    assert not nodes[1]["data"]["content"].startswith("（2/")


def test_call_collapsible_text_api_uses_group_forward_above_200_chars() -> None:
    reset_group_message_interval_state()
    bot = FakeBot()
    message = "x" * 201

    asyncio.run(
        call_collapsible_text_api(
            bot,
            "send_group_msg",
            group_id=10001,
            message=message,
        )
    )

    assert bot.calls[0][0] == "send_group_forward_msg"


def test_call_collapsible_text_api_keeps_200_chars_as_normal_message() -> None:
    reset_group_message_interval_state()
    bot = FakeBot()
    message = "x" * 200

    asyncio.run(
        call_collapsible_text_api(
            bot,
            "send_group_msg",
            group_id=10001,
            message=message,
        )
    )

    assert bot.calls == [("send_group_msg", {"group_id": 10001, "message": message})]


def test_call_collapsible_text_api_falls_back_to_split_when_forward_fails() -> None:
    reset_group_message_interval_state()
    bot = FailingForwardBot()
    message = "long text " * 260

    asyncio.run(
        call_collapsible_text_api(
            bot,
            "send_group_msg",
            group_id=10001,
            message=message,
        )
    )

    assert len(bot.calls) >= 2
    assert {api for api, _data in bot.calls} == {"send_group_msg"}
    assert bot.calls[0][1]["message"].startswith("（1/")


def test_call_record_api_sends_group_record(tmp_path: Path, monkeypatch) -> None:
    reset_group_message_interval_state()
    bot = FakeBot()
    record_values: list[str] = []

    def fake_record(file_path: str) -> str:
        record_values.append(file_path)
        return f"[record:{file_path}]"

    monkeypatch.setattr("qqbot.services.message_delivery.MessageSegment.record", fake_record)

    asyncio.run(
        call_record_api(
            bot,
            tmp_path,
            audio_bytes=b"wav-bytes",
            group_id=10001,
        )
    )

    assert len(record_values) == 1
    assert record_values[0].startswith("file:///")
    audio_path = Path(record_values[0].removeprefix("file:///"))
    assert audio_path.exists()
    assert audio_path.read_bytes() == b"wav-bytes"
    assert bot.calls == [
        (
            "send_group_msg",
            {
                "group_id": 10001,
                "message": f"[record:{record_values[0]}]",
            },
        )
    ]


def test_call_record_api_sends_private_record(tmp_path: Path, monkeypatch) -> None:
    bot = FakeBot()
    record_values: list[str] = []

    def fake_record(file_path: str) -> str:
        record_values.append(file_path)
        return f"[record:{file_path}]"

    monkeypatch.setattr(
        "qqbot.services.message_delivery.MessageSegment.record",
        fake_record,
    )

    asyncio.run(
        call_record_api(
            bot,
            tmp_path,
            audio_bytes=b"wav-bytes",
            user_id="605738729",
        )
    )

    assert bot.calls[0][0] == "send_private_msg"
    assert bot.calls[0][1]["user_id"] == "605738729"
    assert str(bot.calls[0][1]["message"]).startswith("[record:")
    assert record_values[0].startswith("file:///")


def test_group_message_interval_waits_for_same_group_only() -> None:
    reset_group_message_interval_state()
    clock = {"value": 10.0}
    sleep_calls: list[float] = []

    def fake_now() -> float:
        return clock["value"]

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        clock["value"] += seconds

    async def run() -> None:
        await wait_for_group_message_interval(10001, now=fake_now, sleep=fake_sleep)
        await wait_for_group_message_interval(10002, now=fake_now, sleep=fake_sleep)
        await wait_for_group_message_interval(10001, now=fake_now, sleep=fake_sleep)

    asyncio.run(run())

    assert sleep_calls == [0.5]
