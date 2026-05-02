from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.arc_background_service import ArcBackgroundService
from qqbot.services.feature_catalog import get_feature_by_index
from qqbot.services.message_delivery import reset_group_message_interval_state
from qqbot.services.settings_store import SettingsStore


class FakeBot:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def call_api(self, api: str, **data: object) -> None:
        self.calls.append((api, data))


class FakeEventService:
    def __init__(self, messages: list[str] | None = None, should_raise: bool = False) -> None:
        self.messages = messages or []
        self.should_raise = should_raise

    def fetch_active_events(self, now=None):
        if self.should_raise:
            raise RuntimeError("boom")
        if not self.messages:
            return []
        return ["event"]

    def render_event_messages(self, events, now=None):
        if self.should_raise:
            raise RuntimeError("boom")
        if not events:
            return ["当前没有活动梯子。"]
        return list(self.messages)


class FakeAliasService:
    def __init__(self, should_raise: bool = False) -> None:
        self.should_raise = should_raise
        self.calls: list[datetime | None] = []

    def sync_alias_cache(self, now=None):
        self.calls.append(now)
        if self.should_raise:
            raise RuntimeError("boom")
        return {"updated_at": str(now)}


class FakeConstantService:
    def __init__(self, should_raise: bool = False) -> None:
        self.should_raise = should_raise
        self.calls: list[tuple[list[dict[str, str]], datetime | None]] = []

    def sync_missing_constants(self, songs, now=None):
        self.calls.append((songs, now))
        if self.should_raise:
            raise RuntimeError("boom")
        return {"updated_at": str(now), "songs": {}}


class FakeGuessService:
    def __init__(self, expired=None) -> None:
        self.expired = expired or []
        self.calls: list[datetime | None] = []

    def collect_expired_sessions(self, now=None):
        self.calls.append(now)
        return list(self.expired)


def _service(
    tmp_path: Path,
    version_fetcher,
    event_service,
    alias_service=None,
    guess_service=None,
    constant_service=None,
    constant_song_loader=None,
    sleep=None,
) -> ArcBackgroundService:
    store = SettingsStore(tmp_path / "run", author_qq=605738729)
    return ArcBackgroundService(
        state_path=tmp_path / "run" / "data" / "arc" / "background_state.json",
        settings_store=store,
        arc_feature=get_feature_by_index(13),
        author_qq=605738729,
        version_fetcher=version_fetcher,
        event_service=event_service,
        alias_service=alias_service or FakeAliasService(),
        guess_service=guess_service,
        constant_service=constant_service,
        constant_song_loader=constant_song_loader,
        timezone_name="Asia/Shanghai",
        sleep_func=sleep,
    )


def test_arc_background_service_checks_version_on_schedule_without_private_message(tmp_path: Path) -> None:
    versions = iter(["6.13.10c", "6.14.0c", "6.14.0c"])
    service = _service(
        tmp_path,
        version_fetcher=lambda: next(versions),
        event_service=FakeEventService(),
    )
    bot = FakeBot()

    first = datetime(2026, 4, 23, 8, 0, tzinfo=timezone(timedelta(hours=8)))
    second = datetime(2026, 4, 23, 20, 0, tzinfo=timezone(timedelta(hours=8)))
    third = datetime(2026, 4, 24, 8, 0, tzinfo=timezone(timedelta(hours=8)))

    assert service.should_run_version_check(first) is True

    import asyncio

    asyncio.run(service.check_version_and_notify(bot, now=first))
    asyncio.run(service.check_version_and_notify(bot, now=second))
    asyncio.run(service.check_version_and_notify(bot, now=third))

    assert bot.calls == []
    assert service.state.version_last_seen == "6.14.0c"


def test_arc_background_service_syncs_alias_cache_on_first_run_and_after_24h_gap(tmp_path: Path) -> None:
    alias_service = FakeAliasService()
    constant_service = FakeConstantService()
    service = _service(
        tmp_path,
        version_fetcher=lambda: "6.13.10c",
        event_service=FakeEventService(),
        alias_service=alias_service,
        constant_service=constant_service,
        constant_song_loader=lambda: [{"id": "eden", "title": "eden"}],
    )
    bot = FakeBot()
    import asyncio

    first = datetime(2026, 4, 23, 8, 0, tzinfo=timezone(timedelta(hours=8)))
    second = datetime(2026, 4, 23, 20, 0, tzinfo=timezone(timedelta(hours=8)))
    third = datetime(2026, 4, 24, 9, 0, tzinfo=timezone(timedelta(hours=8)))

    asyncio.run(service.run_once(bot, now=first))
    asyncio.run(service.run_once(bot, now=second))
    asyncio.run(service.run_once(bot, now=third))

    assert alias_service.calls == [first, third]
    assert constant_service.calls == [([{"id": "eden", "title": "eden"}], first), ([{"id": "eden", "title": "eden"}], third)]


def test_arc_background_service_immediately_catches_up_after_24h_gap(tmp_path: Path) -> None:
    service = _service(
        tmp_path,
        version_fetcher=lambda: "6.13.10c",
        event_service=FakeEventService(),
    )
    service.state.version_last_checked_at = "2026-04-22T06:00:00+08:00"

    now = datetime(2026, 4, 23, 7, 0, tzinfo=timezone(timedelta(hours=8)))

    assert service.should_run_version_check(now) is True


def test_arc_background_service_sends_group_reminders_once_per_day_with_delay(tmp_path: Path) -> None:
    reset_group_message_interval_state()
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    service = _service(
        tmp_path,
        version_fetcher=lambda: "6.13.10c",
        event_service=FakeEventService(messages=["活动1", "活动2"]),
        sleep=fake_sleep,
    )
    bot = FakeBot()
    feature = get_feature_by_index(13)
    assert feature is not None
    service.settings_store.set_group_feature_state(123456789, feature, True)

    import asyncio

    now = datetime(2026, 4, 23, 9, 0, tzinfo=timezone(timedelta(hours=8)))
    asyncio.run(service.send_activity_reminders(bot, now=now))
    asyncio.run(service.send_activity_reminders(bot, now=now + timedelta(hours=1)))

    assert [api for api, _ in bot.calls] == ["send_group_msg", "send_group_msg"]
    assert len(sleep_calls) == 1
    assert 0 < sleep_calls[0] <= 0.5


def test_arc_background_service_skips_empty_or_failed_activity_fetch(tmp_path: Path) -> None:
    empty_service = _service(
        tmp_path / "empty",
        version_fetcher=lambda: "6.13.10c",
        event_service=FakeEventService(messages=[]),
    )
    failed_service = _service(
        tmp_path / "failed",
        version_fetcher=lambda: "6.13.10c",
        event_service=FakeEventService(should_raise=True),
    )
    bot = FakeBot()
    feature = get_feature_by_index(13)
    assert feature is not None
    empty_service.settings_store.set_group_feature_state(123456789, feature, True)
    failed_service.settings_store.set_group_feature_state(123456789, feature, True)

    import asyncio

    now = datetime(2026, 4, 23, 9, 0, tzinfo=timezone(timedelta(hours=8)))
    asyncio.run(empty_service.send_activity_reminders(bot, now=now))
    asyncio.run(failed_service.send_activity_reminders(bot, now=now))

    assert bot.calls == []


def test_arc_background_service_publishes_expired_arc_guess_sessions(tmp_path: Path) -> None:
    from qqbot.services.arc_guess_service import ArcGuessMessage
    import asyncio

    reset_group_message_interval_state()
    now = datetime(2026, 4, 23, 9, 0, tzinfo=timezone(timedelta(hours=8)))
    guess_service = FakeGuessService(
        expired=[(516286670, ArcGuessMessage("这一局 Arc 猜歌已经超时，答案如下：\n1. Felis"))]
    )
    service = _service(
        tmp_path,
        version_fetcher=lambda: "6.13.10c",
        event_service=FakeEventService(),
        guess_service=guess_service,
    )
    bot = FakeBot()

    asyncio.run(service.expire_arc_guess_sessions(bot, now=now))

    assert guess_service.calls == [now]
    assert bot.calls == [
        (
            "send_group_msg",
            {
                "group_id": 516286670,
                "message": "这一局 Arc 猜歌已经超时，答案如下：\n1. Felis",
            },
        )
    ]


def test_arc_background_service_ignores_alias_sync_failure(tmp_path: Path) -> None:
    alias_service = FakeAliasService(should_raise=True)
    service = _service(
        tmp_path,
        version_fetcher=lambda: "6.14.0c",
        event_service=FakeEventService(messages=["活动1"]),
        alias_service=alias_service,
    )
    bot = FakeBot()
    feature = get_feature_by_index(13)
    assert feature is not None
    service.settings_store.set_group_feature_state(123456789, feature, True)
    service.state.version_last_seen = "6.13.10c"

    import asyncio

    now = datetime(2026, 4, 23, 8, 0, tzinfo=timezone(timedelta(hours=8)))
    asyncio.run(service.run_once(bot, now=now))

    assert [api for api, _ in bot.calls] == ["send_group_msg"]
