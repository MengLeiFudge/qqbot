from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.arc_service import ArcService


def test_arc_service_recommends_chart_from_local_songlist(tmp_path: Path) -> None:
    assets_root = tmp_path / "Games" / "Arcaea"
    chart_root = assets_root / "官谱"
    chart_root.mkdir(parents=True, exist_ok=True)
    (chart_root / "sayonarahatsukoi").mkdir()
    (chart_root / "sayonarahatsukoi" / "base.jpg").write_bytes(b"jpg")
    (chart_root / "dl_someday").mkdir()
    (chart_root / "dl_someday" / "1080_base.jpg").write_bytes(b"jpg")
    (chart_root / "songlist").write_text(
        json.dumps(
            {
                "songs": [
                    {
                        "id": "sayonarahatsukoi",
                        "title_localized": {"en": "Sayonara Hatsukoi"},
                        "difficulties": [
                            {"ratingClass": 0, "rating": 3, "ratingPlus": False},
                            {"ratingClass": 2, "rating": 8, "ratingPlus": True},
                        ],
                    },
                    {
                        "id": "someday",
                        "title_localized": {"en": "Someday"},
                        "difficulties": [
                            {"ratingClass": 2, "rating": 9, "ratingPlus": True},
                        ],
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    service = ArcService(assets_root)
    chart = service.recommend_chart_by_ptt(
        10.5,
        constant_cache={
            "songs": {
                "sayonarahatsukoi": {"constants": {"2": 7.0}},
                "someday": {"constants": {"2": 9.9}},
            }
        },
        picker=lambda charts: charts[-1],
    )

    assert chart.song_id == "someday"
    assert chart.song_name == "Someday"
    assert chart.difficulty_label == "FTR"
    assert chart.constant_text == "9.9"
    assert chart.jacket_path is not None
    assert chart.jacket_path.as_posix().endswith("dl_someday/1080_base.jpg")


def test_arc_service_builds_recommendation_text(tmp_path: Path) -> None:
    assets_root = tmp_path / "Games" / "Arcaea"
    chart_root = assets_root / "官谱"
    chart_root.mkdir(parents=True, exist_ok=True)
    (chart_root / "test_song").mkdir()
    (chart_root / "test_song" / "base.jpg").write_bytes(b"jpg")
    (chart_root / "songlist").write_text(
        json.dumps(
            {
                "songs": [
                    {
                        "id": "test_song",
                        "title_localized": {"en": "Test Song"},
                        "artist": "Composer",
                        "bpm": "180",
                        "set": "testpack",
                        "version": "6.0",
                        "difficulties": [
                            {
                                "ratingClass": 2,
                                "rating": 10,
                                "ratingPlus": True,
                                "chartDesigner": "Chart Guy",
                                "jacketDesigner": "Jacket Gal",
                            },
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    service = ArcService(assets_root)
    chart = service.recommend_chart_by_ptt(
        10.5,
        constant_cache={"songs": {"test_song": {"constants": {"2": 10.5}}}},
        picker=lambda charts: charts[0],
    )

    text = service.build_recommendation_text(10.5, chart)

    assert "PTT 10.5" in text
    assert "Test Song" in text
    assert "Composer" in text
    assert "FTR" in text
    assert "10.5" in text
    assert "BPM：180" in text
    assert "谱师：Chart Guy" in text


def test_arc_service_uses_lower_recommendation_window(tmp_path: Path) -> None:
    service = ArcService(tmp_path)

    assert service._build_recommend_window(10.5) == (8.5, 10.0)
