from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
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


def test_group_nick_store_builds_alias_terms_for_group_member(tmp_path: Path) -> None:
    store = GroupNickStore(tmp_path / "run" / "settings" / "group_nick.json")
    store.record_group_sender(
        group_id=10001,
        qq=605738729,
        card="萌泪酱",
        nickname="MLJ",
        updated_at=1,
    )

    assert store.build_alias_terms(10001, "萌泪酱是谁") == ("605738729", "萌泪酱", "MLJ")
    assert store.build_alias_terms(10001, "605738729") == ("605738729", "萌泪酱", "MLJ")


def test_group_nick_store_treats_empty_json_as_empty_records(tmp_path: Path) -> None:
    path = tmp_path / "run" / "settings" / "group_nick.json"
    path.parent.mkdir(parents=True)
    path.write_text("", encoding="utf-8")

    store = GroupNickStore(path)

    assert store.records == {}


def test_group_nick_store_writes_atomically_without_tmp_file_left(tmp_path: Path) -> None:
    path = tmp_path / "run" / "settings" / "group_nick.json"
    store = GroupNickStore(path)

    store.record_group_sender(
        group_id=10001,
        qq=605738729,
        card="萌泪酱",
        nickname="MLJ",
        updated_at=1,
    )

    assert GroupNickStore(path).resolve_display_name(10001, 605738729) == "萌泪酱"
    assert not list(path.parent.glob(".group_nick.json.*.tmp"))


def test_group_nick_store_retries_permission_denied_replace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "run" / "settings" / "group_nick.json"
    original_replace = Path.replace
    calls = 0

    def flaky_replace(self: Path, target: Path) -> Path:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PermissionError("[WinError 5] 拒绝访问")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", flaky_replace)

    GroupNickStore(path).record_group_sender(
        group_id=10001,
        qq=605738729,
        card="萌泪酱",
        nickname="MLJ",
        updated_at=1,
    )

    assert calls == 2
    assert json.loads(path.read_text(encoding="utf-8"))["10001"]["605738729"]["card"] == "萌泪酱"
    assert not list(path.parent.glob(".group_nick.json.*.tmp"))


def test_group_nick_store_parallel_writes_do_not_share_tmp_file(tmp_path: Path) -> None:
    path = tmp_path / "run" / "settings" / "group_nick.json"

    def write_record(index: int) -> None:
        store = GroupNickStore(path)
        store.record_group_sender(
            group_id=10001 + index,
            qq=605738729 + index,
            card=f"群名片{index}",
            nickname=f"昵称{index}",
            updated_at=index,
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(write_record, range(40)))

    assert path.exists()
    assert not list(path.parent.glob(".group_nick.json.*.tmp"))


def test_resolve_call_name_strips_shapez_decorations(tmp_path: Path) -> None:
    store = GroupNickStore(tmp_path / "run" / "settings" / "group_nick.json")
    store.record_group_sender(
        group_id=1163635014,
        qq=1728704949,
        card="୧⍤⃝୨鱼子勺：[聊天记录]",
        nickname="LiAuO₂ ⁧~喵喵喵 ⁦",
        updated_at=1_800_000_000_000,
    )

    assert store.resolve_call_name(1163635014, 1728704949) == "鱼子勺"


def test_resolve_call_name_keeps_plain_shapez_name(tmp_path: Path) -> None:
    store = GroupNickStore(tmp_path / "run" / "settings" / "group_nick.json")
    store.record_group_sender(
        group_id=1163635014,
        qq=3120618805,
        card="",
        nickname="୧⍤⃝୨勺子鱼",
        updated_at=1_800_000_000_000,
    )

    assert store.resolve_call_name(1163635014, 3120618805) == "勺子鱼"
