from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services import rightcodes_draw_quota_store as quota_module
from qqbot.services.rightcodes_draw_quota_store import (
    RIGHTCODES_DRAW_DAILY_LIMIT,
    RightCodesDrawQuotaStore,
    current_draw_quota_date_key,
)


def test_rightcodes_draw_quota_counts_per_user_per_day(tmp_path: Path) -> None:
    store = RightCodesDrawQuotaStore(tmp_path, daily_limit=2)

    first = store.reserve("10001", date_key="2026-05-09")
    second = store.reserve("10001", date_key="2026-05-09")
    third = store.reserve("10001", date_key="2026-05-09")

    assert first.allowed is True
    assert first.used == 1
    assert first.limit == 2
    assert second.allowed is True
    assert second.used == 2
    assert third.allowed is False
    assert third.used == 2
    assert third.limit == 2
    assert third.remaining == 0


def test_rightcodes_draw_default_daily_limit_is_ten(tmp_path: Path) -> None:
    store = RightCodesDrawQuotaStore(tmp_path)

    reservations = [store.reserve("10001", date_key="2026-05-09") for _ in range(11)]

    assert RIGHTCODES_DRAW_DAILY_LIMIT == 10
    assert all(result.allowed for result in reservations[:10])
    assert reservations[9].used == 10
    assert reservations[9].limit == 10
    assert reservations[10].allowed is False
    assert reservations[10].used == 10
    assert reservations[10].limit == 10


def test_rightcodes_draw_quota_refunds_failed_generation(tmp_path: Path) -> None:
    store = RightCodesDrawQuotaStore(tmp_path, daily_limit=2)

    reserved = store.reserve("10001", date_key="2026-05-09")
    store.refund("10001", date_key="2026-05-09")
    next_reserved = store.reserve("10001", date_key="2026-05-09")

    assert reserved.used == 1
    assert next_reserved.allowed is True
    assert next_reserved.used == 1


def test_rightcodes_draw_quota_resets_by_date(tmp_path: Path) -> None:
    store = RightCodesDrawQuotaStore(tmp_path, daily_limit=1)

    assert store.reserve("10001", date_key="2026-05-09").allowed is True
    assert store.reserve("10001", date_key="2026-05-09").allowed is False
    next_day = store.reserve("10001", date_key="2026-05-10")

    assert next_day.allowed is True
    assert next_day.used == 1


def test_current_draw_quota_date_key_falls_back_without_tzdata(monkeypatch) -> None:
    class BrokenZoneInfo:
        def __init__(self, timezone_name: str) -> None:
            raise quota_module.ZoneInfoNotFoundError(timezone_name)

    monkeypatch.setattr(quota_module, "ZoneInfo", BrokenZoneInfo)

    assert current_draw_quota_date_key()
