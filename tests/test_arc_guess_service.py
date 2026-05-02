from datetime import datetime, timedelta
from pathlib import Path
import json
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.arc_guess_service import ArcGuessService


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
                        "title_localized": {"en": "Test Song"},
                        "difficulties": [{"ratingClass": 2, "rating": 95}],
                    },
                    {
                        "id": "axeofyggdrasil",
                        "title_localized": {"en": "Axe of Yggdrasil"},
                        "difficulties": [{"ratingClass": 2, "rating": 105}],
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_jackets(assets_root: Path) -> None:
    chart_root = assets_root / "官谱"
    for song_id, color in {
        "grievouslady": (255, 0, 0),
        "testsong": (0, 255, 0),
        "axeofyggdrasil": (0, 0, 255),
    }.items():
        song_dir = chart_root / song_id
        song_dir.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (500, 500), color).save(song_dir / "base.jpg")


def _write_alias_cache(cache_path: Path) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {
                "updated_at": "2026-04-23T12:00:00",
                "songs": {
                    "grievouslady": {
                        "title": "Grievous Lady",
                        "aliases": ["Grievous Lady", "gl"],
                    },
                    "testsong": {
                        "title": "Test Song",
                        "aliases": ["Test Song", "ts"],
                    },
                    "axeofyggdrasil": {
                        "title": "Axe of Yggdrasil",
                        "aliases": ["Axe of Yggdrasil", "aoy"],
                    },
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_constants_cache(cache_path: Path) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {
                "updated_at": "2026-04-24T12:00:00",
                "songs": {
                    "grievouslady": {
                        "title": "Grievous Lady",
                        "constants": {"2": 11.0},
                    },
                    "testsong": {
                        "title": "Test Song",
                        "constants": {"2": 9.5},
                    },
                    "axeofyggdrasil": {
                        "title": "Axe of Yggdrasil",
                        "constants": {"2": 10.5},
                    },
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _service(tmp_path: Path) -> ArcGuessService:
    assets_root = tmp_path / "Games" / "Arcaea"
    _write_songlist(assets_root)
    _write_jackets(assets_root)
    alias_cache_path = tmp_path / "run" / "data" / "arc" / "guess_aliases.json"
    _write_alias_cache(alias_cache_path)
    _write_constants_cache(alias_cache_path.with_name("constants.json"))
    return ArcGuessService(
        assets_root=assets_root,
        alias_cache_path=alias_cache_path,
        state_path=tmp_path / "run" / "data" / "arc" / "guess_sessions.json",
        timeout=timedelta(minutes=5),
    )


def test_arc_guess_service_starts_multi_song_session(tmp_path: Path) -> None:
    service = _service(tmp_path)

    text = service.start_game(
        room_id=516286670,
        question_count=2,
        picker=lambda entries, count: entries[:count],
        now=datetime(2026, 4, 23, 12, 0),
    )

    assert "已开始 Arc 猜歌" in text
    assert "1. ******** ****" in text
    assert "2. **** ****" in text
    assert "已开字符：无" in text


def test_arc_guess_service_rejects_restart_when_session_is_active(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.start_game(
        room_id=516286670,
        question_count=2,
        picker=lambda entries, count: entries[:count],
        now=datetime(2026, 4, 23, 12, 0),
    )

    text = service.start_game(
        room_id=516286670,
        question_count=2,
        picker=lambda entries, count: entries[:count],
        now=datetime(2026, 4, 23, 12, 1),
    )

    assert "当前已经有一局 Arc 猜歌" in text
    assert "ar" in text


def test_arc_guess_service_opens_shared_letter_across_unsolved_questions(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.start_game(
        room_id=516286670,
        question_count=2,
        picker=lambda entries, count: entries[:count],
        now=datetime(2026, 4, 23, 12, 0),
    )

    text = service.open_letter(
        room_id=516286670,
        letter="g",
        now=datetime(2026, 4, 23, 12, 1),
    )

    assert "已开字符：g" in text.text
    assert "1. G******* ****" in text.text
    assert "2. **** ***g" in text.text


def test_arc_guess_service_masks_and_opens_any_non_space_character(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.start_game(
        room_id=516286670,
        question_count=1,
        picker=lambda entries, count: entries[2:3],
        now=datetime(2026, 4, 23, 12, 0),
    )

    panel = service.get_session(516286670)
    assert panel is not None
    assert service._mask_answer("A+B-1 *", []) == "***** *"

    star_text = service.open_letter(
        room_id=516286670,
        letter="*",
        now=datetime(2026, 4, 23, 12, 1),
    )
    plus_text = service.open_letter(
        room_id=516286670,
        letter="+",
        now=datetime(2026, 4, 23, 12, 2),
    )
    bracket_text = service.open_letter(
        room_id=516286670,
        letter="[",
        now=datetime(2026, 4, 23, 12, 3),
    )

    assert "已开字符：*" in star_text.text
    assert service._mask_answer("A+B-1 *", ["*"]) == "***** *"
    assert "已开字符：+" in plus_text.text
    assert service._mask_answer("A+B-1 *", ["*", "+"]) == "*+*** *"
    assert "已开字符：[" in bracket_text.text


def test_arc_guess_service_keeps_opened_non_latin_character_display(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.start_game(
        room_id=516286670,
        question_count=1,
        picker=lambda entries, count: entries[:count],
        now=datetime(2026, 4, 23, 12, 0),
    )

    text = service.open_letter(
        room_id=516286670,
        letter="β",
        now=datetime(2026, 4, 23, 12, 1),
    )

    assert "已开字符：β" in text.text
    assert "已开字符：β" in text.text.splitlines()[-1]
    assert "Β" not in text.text


def test_arc_guess_service_checks_answer_by_index_and_alias(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.start_game(
        room_id=516286670,
        question_count=2,
        picker=lambda entries, count: entries[:count],
        now=datetime(2026, 4, 23, 12, 0),
    )

    wrong = service.guess(
        room_id=516286670,
        question_index=2,
        answer="gl",
        player_name="玩家A",
        now=datetime(2026, 4, 23, 12, 2),
    )
    right = service.guess(
        room_id=516286670,
        question_index=1,
        answer="gl",
        player_name="玩家A",
        now=datetime(2026, 4, 23, 12, 3),
    )

    assert "不对" in wrong.text
    assert "答对了第 1 首：Grievous Lady" in right.text
    assert right.image_path is not None
    assert right.image_path.name == "base.jpg"
    session = service.get_session(516286670)
    assert session is not None
    assert session.questions[0].is_solved is True
    assert session.questions[0].solved_by == "玩家A"


def test_arc_guess_service_builds_answer_image_when_letter_game_finishes(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.start_game(
        room_id=516286670,
        question_count=2,
        picker=lambda entries, count: entries[:count],
        now=datetime(2026, 4, 23, 12, 0),
    )

    first = service.guess(
        room_id=516286670,
        question_index=1,
        answer="gl",
        player_name="玩家A",
        now=datetime(2026, 4, 23, 12, 1),
    )
    final = service.guess(
        room_id=516286670,
        question_index=2,
        answer="ts",
        player_name="玩家B",
        now=datetime(2026, 4, 23, 12, 2),
    )

    assert first.image_path is not None
    assert first.image_path.name == "base.jpg"
    assert final.text == "游戏结束，答案如下："
    assert final.image_path is not None
    assert final.image_path.name == "answers.png"
    assert final.image_path.exists()
    with Image.open(final.image_path) as image:
        assert image.width >= 900
        assert image.height >= 280
        assert image.getpixel((32, 32)) == (254, 0, 0)
        assert image.getpixel((32, 172)) == (0, 255, 1)
    assert service.get_session(516286670) is None


def test_arc_guess_service_accepts_half_covered_partial_answer(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.start_game(
        room_id=516286670,
        question_count=1,
        picker=lambda entries, count: entries[2:3],
        now=datetime(2026, 4, 23, 12, 0),
    )

    short = service.guess(
        room_id=516286670,
        question_index=1,
        answer="ax",
        player_name="玩家A",
        now=datetime(2026, 4, 23, 12, 1),
    )
    too_short = service.guess(
        room_id=516286670,
        question_index=1,
        answer="ygg",
        player_name="玩家A",
        now=datetime(2026, 4, 23, 12, 2),
    )
    right = service.guess(
        room_id=516286670,
        question_index=1,
        answer="yggdrasil",
        player_name="玩家A",
        now=datetime(2026, 4, 23, 12, 3),
    )

    assert "不对" in short.text
    assert "不对" in too_short.text
    assert right.text == "游戏结束，答案如下："
    assert right.image_path is not None
    assert right.image_path.name == "answers.png"


def test_arc_guess_service_open_character_auto_solves_full_title(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.start_game(
        room_id=516286670,
        question_count=1,
        picker=lambda entries, count: entries[1:2],
        now=datetime(2026, 4, 23, 12, 0),
    )

    first = service.open_letter(
        room_id=516286670,
        letter="t",
        now=datetime(2026, 4, 23, 12, 1),
    )
    for offset, letter in enumerate("essong", start=2):
        second = service.open_letter(
            room_id=516286670,
            letter=letter,
            now=datetime(2026, 4, 23, 12, offset),
    )

    assert "已开字符：t" in first.text
    assert second.text == "游戏结束，答案如下："
    assert second.image_path is not None
    assert second.image_path.name == "answers.png"


def test_arc_guess_service_reveals_answers_and_clears_timeout_session(tmp_path: Path) -> None:
    service = _service(tmp_path)

    empty = service.reveal_answers(516286670)
    service.start_game(
        room_id=516286670,
        question_count=2,
        picker=lambda entries, count: entries[:count],
        now=datetime(2026, 4, 23, 12, 0),
    )
    timeout = service.open_letter(
        room_id=516286670,
        letter="a",
        now=datetime(2026, 4, 23, 12, 6),
    )
    service.start_game(
        room_id=516286670,
        question_count=2,
        picker=lambda entries, count: entries[:count],
        now=datetime(2026, 4, 23, 12, 12),
    )
    reveal = service.reveal_answers(516286670)

    assert "当前没有进行中的 Arc 猜歌" in empty
    assert "已经超时" in timeout.text
    assert "答案如下：" in timeout.text
    assert "1. Grievous Lady" not in timeout.text
    assert "2. Test Song" not in timeout.text
    assert timeout.image_path is not None
    assert timeout.image_path.name == "answers.png"
    assert reveal.text == "游戏结束，答案如下："
    assert "1. Grievous Lady" not in reveal.text
    assert reveal.image_path is not None
    assert reveal.image_path.name == "answers.png"
    assert service.get_session(516286670) is None


def test_arc_guess_service_refreshes_timeout_after_related_letter_messages(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.start_game(
        room_id=516286670,
        question_count=1,
        picker=lambda entries, count: entries[:count],
        now=datetime(2026, 4, 23, 12, 0),
    )

    wrong = service.guess(
        room_id=516286670,
        question_index=1,
        answer="not grievous lady",
        player_name="玩家A",
        now=datetime(2026, 4, 23, 12, 4),
    )
    still_alive = service.open_letter(
        room_id=516286670,
        letter="g",
        now=datetime(2026, 4, 23, 12, 8),
    )
    expired = service.open_letter(
        room_id=516286670,
        letter="r",
        now=datetime(2026, 4, 23, 12, 14),
    )

    assert "不对" in wrong.text
    assert "已开字符：g" in still_alive.text
    assert "已经超时" in expired.text
    assert "1. Grievous Lady" not in expired.text
    assert expired.image_path is not None
    assert expired.image_path.name == "answers.png"


def test_arc_guess_service_does_not_refresh_timeout_for_missing_question_index(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.start_game(
        room_id=516286670,
        question_count=1,
        picker=lambda entries, count: entries[:count],
        now=datetime(2026, 4, 23, 12, 0),
    )

    missing = service.guess(
        room_id=516286670,
        question_index=814,
        answer="是房租吗",
        player_name="玩家A",
        now=datetime(2026, 4, 23, 12, 4),
    )
    expired = service.open_letter(
        room_id=516286670,
        letter="g",
        now=datetime(2026, 4, 23, 12, 6),
    )

    assert "没有第 814 首题" in missing.text
    assert "已经超时" in expired.text
    assert "1. Grievous Lady" not in expired.text
    assert expired.image_path is not None
    assert expired.image_path.name == "answers.png"


def test_arc_guess_service_publishes_expired_answers_before_new_letter_game(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.start_game(
        room_id=516286670,
        question_count=1,
        picker=lambda entries, count: entries[:count],
        now=datetime(2026, 4, 23, 12, 0),
    )

    text = service.start_game(
        room_id=516286670,
        question_count=1,
        picker=lambda entries, count: entries[1:2],
        now=datetime(2026, 4, 23, 12, 6),
    )

    assert "这一局 Arc 猜歌已经超时，答案如下：" in text
    assert "1. Grievous Lady" not in text
    assert "已开始 Arc 猜歌：" in text
    assert "1. **** ****" in text


def test_arc_guess_service_collects_expired_sessions_for_background_publish(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.start_game(
        room_id=516286670,
        question_count=1,
        picker=lambda entries, count: entries[:count],
        now=datetime(2026, 4, 23, 12, 0),
    )

    fresh = service.collect_expired_sessions(now=datetime(2026, 4, 23, 12, 4))
    expired = service.collect_expired_sessions(now=datetime(2026, 4, 23, 12, 6))

    assert fresh == []
    assert len(expired) == 1
    assert expired[0][0] == 516286670
    assert "这一局 Arc 猜歌已经超时，答案如下：" in expired[0][1].text
    assert "1. Grievous Lady" not in expired[0][1].text
    assert expired[0][1].image_path is not None
    assert expired[0][1].image_path.name == "answers.png"
    assert service.get_session(516286670) is None


def test_arc_guess_service_starts_art_session_with_one_grid_tile(tmp_path: Path) -> None:
    service = _service(tmp_path)

    result = service.start_art_game(
        room_id=516286670,
        picker=lambda entries: entries[0],
        tile_picker=lambda choices: choices[12],
        now=datetime(2026, 4, 24, 12, 0),
    )

    assert result.image_path is not None
    assert result.image_path.exists()
    assert "已开始 Arc 曲绘猜歌" in result.text
    assert "已开放格子：1/25" in result.text
    assert result.image_path.name == "panel.png"
    with Image.open(result.image_path) as image:
        assert image.size == (500, 500)
        assert image.getpixel((250, 250)) == (254, 0, 0)
        assert image.getpixel((50, 50)) == (88, 88, 88)
    session = service.get_session(516286670)
    assert session is not None
    assert session.mode == "art"


def test_arc_guess_service_uses_custom_art_grid_size(tmp_path: Path) -> None:
    service = _service(tmp_path)

    result = service.start_or_open_art_tile(
        room_id=516286670,
        grid_size=5,
        picker=lambda entries: entries[0],
        tile_picker=lambda choices: choices[24],
        now=datetime(2026, 4, 24, 12, 0),
    )

    assert result.image_path is not None
    assert result.image_path.name == "panel.png"
    assert "已开放格子：1/25" in result.text
    with Image.open(result.image_path) as image:
        assert image.size == (500, 500)
        assert image.getpixel((450, 450)) == (254, 0, 0)
        assert image.getpixel((50, 50)) == (88, 88, 88)
        assert image.getpixel((400, 450)) == (254, 0, 0)


def test_arc_guess_service_allows_large_art_grid_size(tmp_path: Path) -> None:
    service = _service(tmp_path)

    result = service.start_or_open_art_tile(
        room_id=516286670,
        grid_size=30,
        picker=lambda entries: entries[0],
        tile_picker=lambda choices: choices[0],
        now=datetime(2026, 4, 24, 12, 0),
    )

    session = service.get_session(516286670)
    assert session is not None
    assert session.art_grid_size == 30
    assert "已开放格子：1/900" in result.text


def test_arc_guess_service_qhmax_uses_jacket_max_supported_grid(tmp_path: Path) -> None:
    service = _service(tmp_path)

    result = service.start_or_open_art_tile(
        room_id=516286670,
        grid_size="max",
        picker=lambda entries: entries[0],
        tile_picker=lambda choices: choices[0],
        now=datetime(2026, 4, 24, 12, 0),
    )

    session = service.get_session(516286670)
    assert session is not None
    assert session.art_grid_size == 500
    assert "已开放格子：1/250000" in result.text


def test_arc_guess_service_one_grid_reveals_whole_jacket(tmp_path: Path) -> None:
    service = _service(tmp_path)

    result = service.start_art_game(
        room_id=516286670,
        grid_size=1,
        picker=lambda entries: entries[0],
        tile_picker=lambda choices: choices[0],
        now=datetime(2026, 4, 24, 12, 0),
    )

    assert result.image_path is not None
    assert "已开放格子：1/1" in result.text
    with Image.open(result.image_path) as image:
        assert image.size == (500, 500)
        assert image.getpixel((50, 50)) == (254, 0, 0)
        assert image.getpixel((250, 250)) == (254, 0, 0)
        assert image.getpixel((450, 450)) == (254, 0, 0)



def test_arc_guess_service_arcqh_opens_next_tile_when_art_session_exists(tmp_path: Path) -> None:
    service = _service(tmp_path)

    first = service.start_or_open_art_tile(
        room_id=516286670,
        picker=lambda entries: entries[0],
        tile_picker=lambda choices: choices[0],
        now=datetime(2026, 4, 24, 12, 0),
    )
    second = service.start_or_open_art_tile(
        room_id=516286670,
        picker=lambda entries: entries[0],
        tile_picker=lambda choices: choices[0],
        now=datetime(2026, 4, 24, 12, 1),
    )

    assert "已开始 Arc 曲绘猜歌" in first.text
    assert "补充了一块曲绘" in second.text
    assert "已开放格子：2/25" in second.text


def test_arc_guess_service_qh_number_opens_multiple_tiles_when_art_session_exists(tmp_path: Path) -> None:
    service = _service(tmp_path)

    service.start_or_open_art_tile(
        room_id=516286670,
        picker=lambda entries: entries[0],
        tile_picker=lambda choices: choices[0],
        now=datetime(2026, 4, 24, 12, 0),
    )
    result = service.start_or_open_art_tile(
        room_id=516286670,
        grid_size=3,
        picker=lambda entries: entries[0],
        tile_picker=lambda choices: choices[0],
        now=datetime(2026, 4, 24, 12, 1),
    )

    session = service.get_session(516286670)
    assert session is not None
    assert session.opened_tiles == [1, 2, 3, 4]
    assert "补充了 3 块曲绘" in result.text
    assert "已开放格子：4/25" in result.text


def test_arc_guess_service_adds_only_one_new_art_tile_until_all_open(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.start_art_game(
        room_id=516286670,
        picker=lambda entries: entries[0],
        tile_picker=lambda choices: choices[0],
        now=datetime(2026, 4, 24, 12, 0),
    )

    second = service.open_art_tile(
        room_id=516286670,
        tile_picker=lambda choices: choices[0],
        now=datetime(2026, 4, 24, 12, 1),
    )
    for _ in range(23):
        service.open_art_tile(
            room_id=516286670,
            tile_picker=lambda choices: choices[0],
            now=datetime(2026, 4, 24, 12, 2),
        )
    exhausted = service.open_art_tile(
        room_id=516286670,
        tile_picker=lambda choices: choices[0],
        now=datetime(2026, 4, 24, 12, 3),
    )

    assert second.image_path is not None
    assert "已开放格子：2/25" in second.text
    assert exhausted.image_path is None
    assert "25 个格子已经全部开完" in exhausted.text


def test_arc_guess_service_checks_art_answer_without_index_by_alias(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.start_art_game(
        room_id=516286670,
        picker=lambda entries: entries[0],
        tile_picker=lambda choices: choices[0],
        now=datetime(2026, 4, 24, 12, 0),
    )

    wrong = service.guess_art(
        room_id=516286670,
        answer="aoy",
        player_name="玩家A",
        now=datetime(2026, 4, 24, 12, 1),
    )
    right = service.guess_art(
        room_id=516286670,
        answer="gl",
        player_name="玩家A",
        now=datetime(2026, 4, 24, 12, 2),
    )

    assert "不对" in wrong.text
    assert wrong.image_path is None
    assert "答对了：Grievous Lady" in right.text
    assert right.image_path is not None
    assert service.get_session(516286670) is None


def test_arc_guess_service_identifies_plausible_art_answers(tmp_path: Path) -> None:
    service = _service(tmp_path)

    assert service.is_plausible_answer("gl", ["Grievous Lady", "gl"]) is True
    assert service.is_plausible_answer("grievous", ["Grievous Lady", "gl"]) is True
    assert service.is_plausible_answer("dancing on a cat's paw", ["Dancin' on a Cat's Paw", "doacsp"]) is True
    assert service.is_plausible_answer("fellis", ["Felis"]) is True
    assert service.is_plausible_answer("felix", ["Felis"]) is False
    assert service.is_plausible_answer("随便聊天", ["Grievous Lady", "gl"]) is False
    assert service.is_plausible_answer("今天吃什么", ["Grievous Lady", "gl"]) is False


def test_arc_guess_service_reveal_art_answer_includes_jacket(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.start_art_game(
        room_id=516286670,
        picker=lambda entries: entries[0],
        tile_picker=lambda choices: choices[0],
        now=datetime(2026, 4, 24, 12, 0),
    )

    reveal = service.reveal_answers(516286670)

    assert reveal.image_path is not None
    assert "游戏结束，答案是：Grievous Lady" in reveal.text
    assert service.get_session(516286670) is None


def test_arc_guess_service_rejects_cross_mode_restart_until_reveal(tmp_path: Path) -> None:
    service = _service(tmp_path)

    service.start_game(
        room_id=516286670,
        question_count=1,
        picker=lambda entries, count: entries[:count],
        now=datetime(2026, 4, 24, 12, 0),
    )
    art_rejected = service.start_art_game(
        room_id=516286670,
        picker=lambda entries: entries[0],
        tile_picker=lambda choices: choices[0],
        now=datetime(2026, 4, 24, 12, 1),
    )
    service.reveal_answers(516286670)
    service.start_art_game(
        room_id=516286670,
        picker=lambda entries: entries[0],
        tile_picker=lambda choices: choices[0],
        now=datetime(2026, 4, 24, 12, 2),
    )
    letter_rejected = service.start_game(
        room_id=516286670,
        question_count=1,
        picker=lambda entries, count: entries[:count],
        now=datetime(2026, 4, 24, 12, 3),
    )

    assert "当前已经有一局 Arc 猜歌" in art_rejected.text
    assert "ar" in art_rejected.text
    assert "当前已经有一局 Arc 猜歌" in letter_rejected
    assert "ar" in letter_rejected
