from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.group_nick_store import GroupNickStore


def test_resolve_display_name_prefers_current_group_card(tmp_path: Path) -> None:
    store = GroupNickStore(tmp_path / "run" / "settings" / "group_nick.json")

    store.record_group_sender(
        group_id=10001,
        qq=605738729,
        card="本群名片",
        nickname="本群昵称",
        updated_at=1_800_000_000_000,
    )

    assert store.resolve_display_name(10001, 605738729) == "本群名片"


def test_resolve_display_name_falls_back_to_latest_other_group_name(tmp_path: Path) -> None:
    store = GroupNickStore(tmp_path / "run" / "settings" / "group_nick.json")

    store.record_group_sender(
        group_id=10002,
        qq=605738729,
        card="",
        nickname="旧昵称",
        updated_at=1_700_000_000_000,
    )
    store.record_group_sender(
        group_id=10003,
        qq=605738729,
        card="新群名片",
        nickname="新昵称",
        updated_at=1_800_000_000_000,
    )

    assert store.resolve_display_name(99999, 605738729) == "新群名片"


def test_resolve_display_name_falls_back_to_qq_number(tmp_path: Path) -> None:
    store = GroupNickStore(tmp_path / "run" / "settings" / "group_nick.json")

    assert store.resolve_display_name(10001, 605738729) == "605738729"


def test_group_nick_store_removes_group_records(tmp_path: Path) -> None:
    path = tmp_path / "run" / "settings" / "group_nick.json"
    store = GroupNickStore(path)
    store.record_group_sender(
        group_id=10001,
        qq=605738729,
        card="旧群名片",
        nickname="",
        updated_at=1,
    )

    assert store.remove_group(10001) is True
    assert GroupNickStore(path).records == {}
    assert store.remove_group(10001) is False
