from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.arc_event_service import ArcEventService


def test_arc_event_service_parses_active_events_and_enriches_rewards() -> None:
    page_map = {
        "World Mode Data Past Events": """
{{#ifeq:{{{1|0-LE DJMAX Collaboration / Tairitsu & El Fail Event}}}|0-LE DJMAX Collaboration / Tairitsu & El Fail Event|
|history =
* Playable from 2026-04-20 to 2026-04-25
<tr><td>Total</td><td>'''1080'''</td><td colspan=2><ul><li>'''2000 Fragments'''</li><li>'''Ether Drop &times; 4'''</li><li>'''[[Someday]]'''</li><li>'''[[Tairitsu & El Fail]]'''</li></ul></td></tr>
}}
}}{{#ifeq:{{{1|0-LE Old Event}}}|0-LE Old Event|
|history =
* Playable from 2026-03-01 to 2026-03-07
<tr><td>Total</td><td>'''1080'''</td><td colspan=2><ul><li>'''500 Fragments'''</li></ul></td></tr>
}}
""",
        "Someday": """
{{Song
|Mobile Pack = World Extend 3
|Version = Version 6.6.0 (2025-06-26)
}}
""",
        "Tairitsu & El Fail": """
{{PartnerInfobox
|version_added = 6.6.0 (2025-06-26)
}}
""",
    }
    service = ArcEventService(
        wiki_page_fetcher=lambda title: page_map[title],
        version_fetcher=lambda: "6.13.10c",
        timezone="Asia/Shanghai",
    )

    now = datetime(
        2026,
        4,
        23,
        12,
        0,
        tzinfo=timezone(timedelta(hours=8), name="Asia/Shanghai"),
    )
    events = service.fetch_active_events(now=now)
    messages = service.render_event_messages(events, now=now)

    assert len(events) == 1
    assert events[0].title == "DJMAX Collaboration"
    assert "Someday（曲目 / World Extend 3）" in messages[0]
    assert "Tairitsu & El Fail（搭档 / 复刻搭档）" in messages[0]
    assert "Ether Drop x4" in messages[0]
    assert "剩余时间：" in messages[0]


def test_arc_event_service_renders_no_event_message_when_empty() -> None:
    service = ArcEventService(
        wiki_page_fetcher=lambda _title: "",
        version_fetcher=lambda: "6.13.10c",
        timezone="Asia/Shanghai",
    )

    messages = service.render_event_messages([], now=datetime(2026, 4, 23, 12, 0))

    assert messages == ["当前没有活动梯子。"]
