import asyncio

from qqbot.services.message_delivery import (
    MAX_TEXT_MESSAGE_CHARS,
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

    async def finish(self, message: str) -> None:
        self.finished.append(message)


class FakeBot:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.interval_flags: list[bool] = []

    async def call_api(self, api: str, **data: object) -> None:
        self.interval_flags.append(has_waited_group_message_interval())
        self.calls.append((api, data))


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
