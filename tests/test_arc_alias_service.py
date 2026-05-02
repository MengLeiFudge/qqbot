from datetime import datetime
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.arc_alias_service import ArcAliasService


def _write_songlist(assets_root: Path) -> None:
    chart_root = assets_root / "官谱"
    chart_root.mkdir(parents=True, exist_ok=True)
    (chart_root / "songlist").write_text(
        json.dumps(
            {
                "songs": [
                    {
                        "id": "grievouslady",
                        "title_localized": {"en": "Grievous Lady"},
                        "difficulties": [{"ratingClass": 2, "rating": 110}],
                    },
                    {
                        "id": "testsong",
                        "title_localized": {
                            "en": "Test Song",
                            "ja": "テストソング",
                            "zh-Hans": "测试曲",
                        },
                        "difficulties": [{"ratingClass": 2, "rating": 95}],
                    },
                    {
                        "id": "fractureray",
                        "title_localized": {"en": "Fracture Ray"},
                        "difficulties": [{"ratingClass": 2, "rating": 110}],
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_arc_alias_service_builds_base_aliases_from_formal_title(tmp_path: Path) -> None:
    assets_root = tmp_path / "Games" / "Arcaea"
    _write_songlist(assets_root)
    service = ArcAliasService(
        assets_root=assets_root,
        cache_path=tmp_path / "run" / "data" / "arc" / "guess_aliases.json",
        wiki_redirect_fetcher=lambda _title: [],
    )

    payload = service.build_alias_cache(now=datetime(2026, 4, 23, 12, 0))

    grievous = payload["songs"]["grievouslady"]
    assert grievous["title"] == "Grievous Lady"
    assert grievous["aliases"] == ["Grievous Lady", "gl"]


def test_arc_alias_service_includes_all_localized_titles(tmp_path: Path) -> None:
    assets_root = tmp_path / "Games" / "Arcaea"
    _write_songlist(assets_root)
    service = ArcAliasService(
        assets_root=assets_root,
        cache_path=tmp_path / "run" / "data" / "arc" / "guess_aliases.json",
        wiki_redirect_fetcher=lambda _title: [],
    )

    payload = service.build_alias_cache(now=datetime(2026, 4, 23, 12, 0))

    assert payload["songs"]["testsong"]["aliases"] == [
        "Test Song",
        "ts",
        "テストソング",
        "测试曲",
    ]


def test_arc_alias_service_merges_manual_aliases(tmp_path: Path) -> None:
    assets_root = tmp_path / "Games" / "Arcaea"
    _write_songlist(assets_root)
    manual_alias_path = tmp_path / "run" / "data" / "arc" / "guess_manual_aliases.json"
    manual_alias_path.parent.mkdir(parents=True, exist_ok=True)
    manual_alias_path.write_text(
        json.dumps(
                {
                    "songs": {
                        "testsong": ["测歌", "Test Song"],
                        "fractureray": {"aliases": ["骨折光"]},
                    }
                },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    service = ArcAliasService(
        assets_root=assets_root,
        cache_path=tmp_path / "run" / "data" / "arc" / "guess_aliases.json",
        manual_alias_path=manual_alias_path,
        wiki_redirect_fetcher=lambda _title: [],
    )

    payload = service.build_alias_cache(now=datetime(2026, 4, 23, 12, 0))

    assert payload["songs"]["testsong"]["aliases"] == [
        "Test Song",
        "ts",
        "テストソング",
        "测试曲",
        "测歌",
    ]
    assert payload["songs"]["fractureray"]["aliases"] == [
        "Fracture Ray",
        "fr",
        "骨折光",
    ]


def test_arc_alias_service_merges_wiki_redirects(tmp_path: Path) -> None:
    assets_root = tmp_path / "Games" / "Arcaea"
    _write_songlist(assets_root)
    service = ArcAliasService(
        assets_root=assets_root,
        cache_path=tmp_path / "run" / "data" / "arc" / "guess_aliases.json",
        wiki_redirect_fetcher=lambda title: ["Grevious Lady", "骨折光"] if title == "Grievous Lady" else [],
    )

    payload = service.build_alias_cache(now=datetime(2026, 4, 23, 12, 0))

    assert payload["songs"]["grievouslady"]["aliases"] == [
        "Grievous Lady",
        "gl",
        "Grevious Lady",
        "骨折光",
    ]


def test_arc_alias_service_syncs_cache_even_when_wiki_fetch_fails(tmp_path: Path) -> None:
    assets_root = tmp_path / "Games" / "Arcaea"
    _write_songlist(assets_root)

    def broken_fetcher(_title: str) -> list[str]:
        raise RuntimeError("boom")

    service = ArcAliasService(
        assets_root=assets_root,
        cache_path=tmp_path / "run" / "data" / "arc" / "guess_aliases.json",
        wiki_redirect_fetcher=broken_fetcher,
    )

    service.sync_alias_cache(now=datetime(2026, 4, 23, 12, 0))
    payload = service.load_alias_cache()

    assert payload["updated_at"] == "2026-04-23T12:00:00"
    assert payload["songs"]["testsong"]["aliases"] == [
        "Test Song",
        "ts",
        "テストソング",
        "测试曲",
    ]
