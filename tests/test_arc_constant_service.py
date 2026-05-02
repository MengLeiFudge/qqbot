from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.arc_constant_service import ArcConstantService


def test_arc_constant_service_parses_wiki_cc_fields(tmp_path: Path) -> None:
    service = ArcConstantService(
        cache_path=tmp_path / "run" / "data" / "arc" / "constants.json",
        wiki_text_fetcher=lambda _title: """
{{Song
|Past CC = 4.5
|Present CC = 8.2
|Future CC = 10.5
|Beyond CC = 11.2
|Eternal CC = 9.8
}}
""",
    )

    payload = service.sync_constant_cache(
        songs=[{"id": "edenwacca", "title": "eden"}],
        now=datetime(2026, 4, 24, 12, 0),
    )

    assert payload["songs"]["edenwacca"]["constants"] == {
        "0": 4.5,
        "1": 8.2,
        "2": 10.5,
        "3": 11.2,
        "4": 9.8,
    }


def test_arc_constant_service_loads_existing_cache(tmp_path: Path) -> None:
    cache_path = tmp_path / "run" / "data" / "arc" / "constants.json"
    service = ArcConstantService(cache_path=cache_path, wiki_text_fetcher=lambda _title: "")
    service.sync_constant_cache(
        songs=[{"id": "test", "title": "Test"}],
        now=datetime(2026, 4, 24, 12, 0),
    )

    loaded = service.load_constant_cache()

    assert loaded["songs"]["test"]["title"] == "Test"


def test_arc_constant_service_incrementally_fills_missing_entries(tmp_path: Path) -> None:
    fetched: list[str] = []

    def fake_fetch(title: str) -> str:
        fetched.append(title)
        return "|Future CC = 9.8"

    service = ArcConstantService(
        cache_path=tmp_path / "run" / "data" / "arc" / "constants.json",
        wiki_text_fetcher=fake_fetch,
    )
    service.sync_constant_cache(
        songs=[{"id": "done", "title": "Done"}],
        now=datetime(2026, 4, 24, 12, 0),
    )

    payload = service.sync_missing_constants(
        songs=[
            {"id": "done", "title": "Done"},
            {"id": "a", "title": "A"},
            {"id": "b", "title": "B"},
        ],
        now=datetime(2026, 4, 24, 13, 0),
        limit=1,
    )

    assert fetched == ["Done", "A"]
    assert payload["songs"]["done"]["constants"] == {"2": 9.8}
    assert payload["songs"]["a"]["constants"] == {"2": 9.8}
    assert "b" not in payload["songs"]
