from pathlib import Path

import pytest

from qqbot.config import RuntimeSettings
from qqbot.services.admin_service import AdminService
import qqbot.services.admin_service as admin_service_module
from qqbot.services.group_nick_store import GroupNickStore
from qqbot.services.settings_store import SettingsStore


def build_service(tmp_path: Path) -> AdminService:
    settings = RuntimeSettings(data_root=tmp_path / "run")
    return AdminService(
        settings=settings,
        store=SettingsStore(settings.data_root, settings.author_qq),
        project_root=tmp_path,
    )


def test_list_groups_reads_existing_feature_files(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    state_root = tmp_path / "run" / "settings" / "func_state"
    state_root.mkdir(parents=True)
    (state_root / "10002.json").write_text('{"随机复读": true}', encoding="utf-8")
    (state_root / "10001.json").write_text('{"随机禁言": true}', encoding="utf-8")

    groups = service.list_groups({10001: "测试群 A", 10002: "测试群 B"})

    assert [group["group_id"] for group in groups] == [10001, 10002]
    assert groups[0]["display_name"] == "测试群 A（10001）"
    assert groups[1]["display_name"] == "测试群 B（10002）"
    first_features = groups[0]["features"]
    assert first_features[0]["name"] == "随机复读"


def test_arc_legacy_keys_render_as_current_arc_feature(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    state_root = tmp_path / "run" / "settings" / "func_state"
    state_root.mkdir(parents=True)
    (state_root / "123.json").write_text('{"Arc狼人杀": true}', encoding="utf-8")

    payload = service.get_group_features(123)
    arc_feature = next(feature for feature in payload["features"] if feature["name"] == "Arc")

    assert arc_feature["enabled"] is True


def test_list_plugins_returns_global_states(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    payload = service.list_plugins()
    arc_plugin = next(plugin for plugin in payload["plugins"] if plugin["id"] == "arc")

    assert arc_plugin["name"] == "Arc"
    assert arc_plugin["feature_index"] == 13
    assert arc_plugin["global_enabled"] is True
    assert arc_plugin["ai_capabilities"] == ["explain"]


def test_set_plugin_enabled_affects_group_feature_effective_state(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    service.set_group_feature(123, 13, True)

    payload = service.set_plugin_enabled("arc", False)
    group_payload = service.get_group_features(123)
    arc_feature = next(feature for feature in group_payload["features"] if feature["name"] == "Arc")

    assert payload["plugin"]["id"] == "arc"
    assert payload["plugin"]["global_enabled"] is False
    assert arc_feature["enabled"] is False


def test_set_plugin_enabled_rejects_unknown_plugin(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    with pytest.raises(ValueError):
        service.set_plugin_enabled("missing", False)


def test_set_group_feature_uses_current_name_and_removes_legacy_keys(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    state_path = tmp_path / "run" / "settings" / "func_state" / "123.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text('{"Arc查询": true, "Arc狼人杀": true}', encoding="utf-8")

    payload = service.set_group_feature(123, 13, False)

    assert payload["feature"]["name"] == "Arc"
    assert payload["feature"]["enabled"] is False
    text = state_path.read_text(encoding="utf-8")
    assert '"Arc": false' in text
    assert "Arc查询" not in text
    assert "Arc狼人杀" not in text


def test_admin_list_and_update_use_bot_admin_json(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    nick_store = GroupNickStore(tmp_path / "run" / "settings" / "group_nick.json")
    nick_store.record_group_sender(
        group_id=100,
        qq=10001,
        card="测试管理员",
        nickname="",
        updated_at=1,
    )

    service.set_admin(10001, True)
    service.set_admin(10002, False)
    payload = service.list_admins()

    assert payload["author_qq"] == 0
    assert payload["admins"] == [10001]
    assert payload["author"] == {"qq": 0, "name": "", "display_name": "0"}
    assert payload["admin_items"] == [
        {"qq": 10001, "name": "测试管理员", "display_name": "测试管理员（10001）"}
    ]
    assert service.store.is_bot_admin(10001) is True
    assert service.store.is_bot_admin(10002) is False


def test_admin_author_display_can_use_configured_name(tmp_path: Path) -> None:
    settings = RuntimeSettings(
        data_root=tmp_path / "run",
        author_qq=605738729,
        author_name="萌泪酱",
    )
    service = AdminService(
        settings=settings,
        store=SettingsStore(settings.data_root, settings.author_qq),
        project_root=tmp_path,
    )

    payload = service.list_admins()

    assert payload["author"] == {
        "qq": 605738729,
        "name": "萌泪酱",
        "display_name": "萌泪酱（605738729）",
    }


def test_log_reading_rejects_unsafe_file_names_and_unknown_runs(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    log_dir = tmp_path / "logs" / "start_all" / "20260425-123456"
    log_dir.mkdir(parents=True)
    (log_dir / "launcher.log").write_text("line1\nline2\n", encoding="utf-8")

    payload = service.read_startup_log("20260425-123456", "launcher.log", tail_lines=1)
    assert payload["content"] == "line2"

    with pytest.raises(ValueError):
        service.read_startup_log("../bad", "launcher.log")
    with pytest.raises(ValueError):
        service.read_startup_log("20260425-123456", "../secret.txt")
    with pytest.raises(FileNotFoundError):
        service.read_startup_log("20260425-000000", "launcher.log")


def test_schedule_restart_launches_start_all(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = build_service(tmp_path)
    script = tmp_path / "scripts" / "start_all.bat"
    script.parent.mkdir(parents=True)
    script.write_text("@echo off\n", encoding="utf-8")
    calls: list[dict[str, object]] = []

    def fake_popen(*args: object, **kwargs: object) -> object:
        calls.append({"args": args, "kwargs": kwargs})
        return object()

    monkeypatch.setattr(admin_service_module.subprocess, "Popen", fake_popen)

    payload = service.schedule_restart()

    assert payload["scheduled"] is True
    assert len(calls) == 1
    command_text = " ".join(str(part) for part in calls[0]["args"])
    assert "start_all.bat" in command_text
    assert "-SkipInstall" in command_text
    assert "-RestartBot" in command_text


def test_windows_restart_command_uses_windows_terminal(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    script = tmp_path / "scripts" / "start_all.bat"

    command = service._build_windows_restart_command(script)

    assert command == [
        "wt.exe",
        "-w",
        "-1",
        "new-tab",
        "--title",
        "QQBot-Restart",
        "-d",
        str(tmp_path),
        str(script),
        "-SkipInstall",
        "-RestartBot",
    ]
