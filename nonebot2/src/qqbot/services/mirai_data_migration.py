from __future__ import annotations

import json
from pathlib import Path
import shutil

from qqbot.services.group_nick_store import GroupNickStore


LOLICON_MODE_MAP = {
    "0": {"group_r18": False, "show_image": False},
    "1": {"group_r18": True, "show_image": False},
    "2": {"group_r18": False, "show_image": True},
    "3": {"group_r18": True, "show_image": True},
}


def load_java_properties_map(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def migrate_func_state(legacy_dir: Path, target_dir: Path) -> int:
    if not legacy_dir.exists():
        return 0
    migrated = 0
    for legacy_file in sorted(legacy_dir.glob("*.txt")):
        payload = {
            key: value.lower() == "true"
            for key, value in load_java_properties_map(legacy_file).items()
        }
        _write_json(target_dir / f"{legacy_file.stem}.json", payload)
        migrated += 1
    return migrated


def migrate_reread(legacy_file: Path, target_file: Path) -> None:
    payload = {
        key: float(value)
        for key, value in load_java_properties_map(legacy_file).items()
    }
    _write_json(target_file, payload)


def migrate_thunder(legacy_file: Path, target_file: Path) -> None:
    payload: dict[str, dict[str, float | int]] = {}
    for key, value in load_java_properties_map(legacy_file).items():
        chance_raw, min_seconds_raw, max_seconds_raw = value.split("-", 2)
        payload[key] = {
            "chance": float(chance_raw),
            "min_seconds": int(min_seconds_raw),
            "max_seconds": int(max_seconds_raw),
        }
    _write_json(target_file, payload)


def migrate_lolicon_config(legacy_file: Path, target_file: Path) -> None:
    payload = {
        key: dict(LOLICON_MODE_MAP.get(value, LOLICON_MODE_MAP["0"]))
        for key, value in load_java_properties_map(legacy_file).items()
    }
    _write_json(target_file, payload)


def migrate_group_nick(legacy_dir: Path, target_file: Path) -> int:
    if not legacy_dir.exists():
        return 0
    store = GroupNickStore(target_file)
    migrated = 0
    # 旧 groupNick 只作为当前昵称缓存的补充，不覆盖已经由新架构写入的较新记录。
    for legacy_file in sorted(legacy_dir.glob("*.txt")):
        group_id = int(legacy_file.stem)
        for qq, nickname in load_java_properties_map(legacy_file).items():
            if not qq.isdigit():
                continue
            store.merge_legacy_nickname(group_id, int(qq), nickname)
            migrated += 1
    return migrated


def copy_file(legacy_file: Path, target_file: Path) -> bool:
    if not legacy_file.exists():
        return False
    target_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(legacy_file, target_file)
    return True


def copy_tree(legacy_dir: Path, target_dir: Path) -> int:
    if not legacy_dir.exists():
        return 0
    source_files = {
        path.relative_to(legacy_dir).as_posix()
        for path in legacy_dir.rglob("*")
        if path.is_file()
    }
    file_count = len(source_files)
    if target_dir.exists():
        target_files = {
            path.relative_to(target_dir).as_posix()
            for path in target_dir.rglob("*")
            if path.is_file()
        }
        if target_files == source_files:
            return file_count
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(legacy_dir, target_dir, dirs_exist_ok=True)
    return file_count


def run_mirai_data_migration(legacy_run: Path, data_root: Path) -> dict[str, int]:
    settings_root = Path(data_root) / "settings"
    data_root = Path(data_root) / "data"
    shapez_root = Path(data_root).parent / "shapez"

    func_state_count = migrate_func_state(
        legacy_run / "settings" / "funcState",
        settings_root / "func_state",
    )
    group_nick_count = migrate_group_nick(
        legacy_run / "settings" / "groupNick",
        settings_root / "group_nick.json",
    )
    migrate_reread(legacy_run / "settings" / "reread.txt", settings_root / "reread.json")
    migrate_thunder(legacy_run / "settings" / "thunder.txt", settings_root / "thunder.json")
    migrate_lolicon_config(
        legacy_run / "settings" / "loliconImgConfig.txt",
        settings_root / "lolicon.json",
    )

    copied_zfb = int(copy_file(legacy_run / "data" / "zfb.jpg", data_root / "zfb.jpg"))
    copied_shapez_db = int(
        copy_file(
            legacy_run / "data" / "shapez" / "db_2c1r_1+3_new.csv",
            shapez_root / "db_2c1r_1+3_new.csv",
        )
    )
    copied_shapez_img = copy_tree(
        legacy_run / "data" / "shapez" / "img",
        shapez_root / "img",
    )
    copied_lolicon_img = copy_tree(
        legacy_run / "data" / "lolicon" / "img",
        data_root / "lolicon" / "img",
    )

    return {
        "func_state_files": func_state_count,
        "group_nick_entries": group_nick_count,
        "copied_zfb": copied_zfb,
        "copied_shapez_db": copied_shapez_db,
        "copied_shapez_img": copied_shapez_img,
        "copied_lolicon_img": copied_lolicon_img,
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
