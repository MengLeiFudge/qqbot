from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.mirai_data_migration import (
    copy_file,
    copy_tree,
    migrate_bot_admin,
    migrate_func_state,
    migrate_group_nick,
    migrate_lolicon_config,
    migrate_reread,
    migrate_thunder,
)


def test_migrate_bot_admin_writes_json(tmp_path: Path) -> None:
    legacy_file = tmp_path / "legacy" / "run" / "settings" / "botAdmin.txt"
    target_file = tmp_path / "run" / "settings" / "bot_admin.json"
    legacy_file.parent.mkdir(parents=True, exist_ok=True)
    legacy_file.write_text("#comment\n1397381851=true\n605738729=false\n", encoding="utf-8")

    migrate_bot_admin(legacy_file, target_file)

    assert json.loads(target_file.read_text(encoding="utf-8")) == {
        "1397381851": True,
        "605738729": False,
    }


def test_migrate_func_state_writes_json_files(tmp_path: Path) -> None:
    legacy_dir = tmp_path / "legacy" / "run" / "settings" / "funcState"
    target_dir = tmp_path / "run" / "settings" / "func_state"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    (legacy_dir / "516286670.txt").write_text(
        "#comment\nLolicon美图=true\n异形工厂=true\n",
        encoding="utf-8",
    )

    migrated = migrate_func_state(legacy_dir, target_dir)

    assert migrated == 1
    assert json.loads((target_dir / "516286670.json").read_text(encoding="utf-8")) == {
        "Lolicon美图": True,
        "异形工厂": True,
    }


def test_migrate_reread_thunder_and_lolicon_configs(tmp_path: Path) -> None:
    legacy_settings = tmp_path / "legacy" / "run" / "settings"
    target_settings = tmp_path / "run" / "settings"
    legacy_settings.mkdir(parents=True, exist_ok=True)

    reread_legacy = legacy_settings / "reread.txt"
    thunder_legacy = legacy_settings / "thunder.txt"
    lolicon_legacy = legacy_settings / "loliconImgConfig.txt"
    reread_target = target_settings / "reread.json"
    thunder_target = target_settings / "thunder.json"
    lolicon_target = target_settings / "lolicon.json"

    reread_legacy.write_text("#comment\n516286670=0.01\n", encoding="utf-8")
    thunder_legacy.write_text("#comment\n319567534=0.025-3-10\n", encoding="utf-8")
    lolicon_legacy.write_text("#comment\n516286670=2\n", encoding="utf-8")

    migrate_reread(reread_legacy, reread_target)
    migrate_thunder(thunder_legacy, thunder_target)
    migrate_lolicon_config(lolicon_legacy, lolicon_target)

    assert json.loads(reread_target.read_text(encoding="utf-8")) == {"516286670": 0.01}
    assert json.loads(thunder_target.read_text(encoding="utf-8")) == {
        "319567534": {
            "chance": 0.025,
            "min_seconds": 3,
            "max_seconds": 10,
        }
    }
    assert json.loads(lolicon_target.read_text(encoding="utf-8")) == {
        "516286670": {
            "group_r18": False,
            "show_image": True,
        }
    }


def test_migrate_group_nick_builds_current_json_shape(tmp_path: Path) -> None:
    legacy_dir = tmp_path / "legacy" / "run" / "settings" / "groupNick"
    target_file = tmp_path / "run" / "settings" / "group_nick.json"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    (legacy_dir / "516286670.txt").write_text(
        "#comment\n605738729=萌泪酱\n2629227874=萌泪3号\n",
        encoding="utf-8",
    )

    migrated = migrate_group_nick(legacy_dir, target_file)

    payload = json.loads(target_file.read_text(encoding="utf-8"))
    assert migrated == 2
    assert payload["516286670"]["605738729"] == {
        "card": "",
        "nickname": "萌泪酱",
        "updated_at": 0,
    }
    assert payload["516286670"]["2629227874"] == {
        "card": "",
        "nickname": "萌泪3号",
        "updated_at": 0,
    }


def test_migrate_group_nick_keeps_current_records(tmp_path: Path) -> None:
    legacy_dir = tmp_path / "legacy" / "run" / "settings" / "groupNick"
    target_file = tmp_path / "run" / "settings" / "group_nick.json"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(
        json.dumps(
            {
                "516286670": {
                    "605738729": {
                        "card": "当前名片",
                        "nickname": "当前昵称",
                        "updated_at": 1_800_000_000_000,
                    }
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (legacy_dir / "516286670.txt").write_text("#comment\n605738729=旧昵称\n", encoding="utf-8")

    migrated = migrate_group_nick(legacy_dir, target_file)

    payload = json.loads(target_file.read_text(encoding="utf-8"))
    assert migrated == 1
    assert payload["516286670"]["605738729"] == {
        "card": "当前名片",
        "nickname": "当前昵称",
        "updated_at": 1_800_000_000_000,
    }


def test_copy_file_copies_binary_content(tmp_path: Path) -> None:
    legacy_file = tmp_path / "legacy" / "run" / "data" / "zfb.jpg"
    target_file = tmp_path / "run" / "data" / "zfb.jpg"
    legacy_file.parent.mkdir(parents=True, exist_ok=True)
    legacy_file.write_bytes(b"legacy-zfb")

    copied = copy_file(legacy_file, target_file)

    assert copied is True
    assert target_file.read_bytes() == b"legacy-zfb"


def test_copy_tree_copies_nested_files(tmp_path: Path) -> None:
    legacy_shape = tmp_path / "legacy" / "run" / "data" / "shapez" / "img" / "shape"
    legacy_lolicon = tmp_path / "legacy" / "run" / "data" / "lolicon" / "img"
    target_shape = tmp_path / "run" / "shapez" / "img"
    target_lolicon = tmp_path / "run" / "data" / "lolicon" / "img"
    legacy_shape.mkdir(parents=True, exist_ok=True)
    legacy_lolicon.mkdir(parents=True, exist_ok=True)
    (legacy_shape / "a.png").write_bytes(b"shape")
    (legacy_lolicon / "1001.jpg").write_bytes(b"lolicon")

    copied_shape = copy_tree(legacy_shape.parent, target_shape)
    copied_lolicon = copy_tree(legacy_lolicon.parent, target_lolicon.parent)

    assert copied_shape == 1
    assert copied_lolicon == 1
    assert (target_shape / "shape" / "a.png").read_bytes() == b"shape"
    assert (target_lolicon / "1001.jpg").read_bytes() == b"lolicon"
