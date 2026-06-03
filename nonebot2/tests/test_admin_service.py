from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.config import RuntimeSettings
from qqbot.services.admin_service import AdminService
import qqbot.services.admin_service as admin_service_module
from qqbot.services.chat_memory_store import ChatMemoryStore
from qqbot.services.group_message_log_store import GroupMessageLogStore
from qqbot.services.group_nick_store import GroupNickStore
from qqbot.services.kun_service import KunService
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
    (state_root / "10002.json").write_text('{"group_assistant": true}', encoding="utf-8")
    (state_root / "10001.json").write_text('{"arc": true}', encoding="utf-8")

    groups = service.list_groups({10001: "测试群 A", 10002: "测试群 B"})

    assert [group["group_id"] for group in groups] == [10001, 10002]
    assert groups[0]["display_name"] == "测试群 A（10001）"
    assert groups[1]["display_name"] == "测试群 B（10002）"
    assert "features" not in groups[0]


def test_list_groups_includes_connected_group_names_without_feature_files(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    groups = service.list_groups({123: "在线群"})

    assert groups == [
        {
            "group_id": 123,
            "group_name": "在线群",
            "display_name": "在线群（123）",
        }
    ]


def test_list_groups_does_not_use_group_nick_cache_as_known_group_source(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    nick_store = GroupNickStore(tmp_path / "run" / "settings" / "group_nick.json")
    nick_store.record_group_sender(
        group_id=10001,
        qq=605738729,
        card="旧群名片",
        nickname="",
        updated_at=1,
    )

    assert service.list_groups() == []


def test_list_plugins_returns_global_states(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    payload = service.list_plugins()
    arc_plugin = next(plugin for plugin in payload["plugins"] if plugin["id"] == "arc")

    assert arc_plugin["name"] == "Arc"
    assert "feature_index" not in arc_plugin
    assert arc_plugin["global_enabled"] is True
    assert arc_plugin["ai_capabilities"] == ["explain"]


def test_set_plugin_enabled_updates_global_state(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    payload = service.set_plugin_enabled("arc", False)

    assert payload["plugin"]["id"] == "arc"
    assert payload["plugin"]["global_enabled"] is False


def test_set_plugin_enabled_rejects_unknown_plugin(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    with pytest.raises(ValueError):
        service.set_plugin_enabled("missing", False)


def test_ai_profile_priority_lists_openrouter_icu_then_rightcodes(tmp_path: Path) -> None:
    profile_file = tmp_path / "config" / "qqbot.toml"
    profile_file.parent.mkdir(parents=True)
    profile_file.write_text(
        """
[ai]
default_profile = "rightcodes"

[ai.providers.rightcodes]
provider = "openai_compatible"
base_url = "https://right.codes/codex/v1"
model = "gpt-5.5"
api_key_env = "QQBOT_AI_KEY_RIGHTCODES"

[ai.providers.openrouter-icu]
provider = "openai_compatible"
base_url = "https://rehdasu.cn/v1"
model = "gpt-5.5"
api_key_env = "QQBOT_AI_KEY_OPENROUTER_ICU"
""".strip(),
        encoding="utf-8",
    )
    settings = RuntimeSettings(data_root=tmp_path / "run", ai_profile_file=profile_file, ai_default_profile="rightcodes")
    service = AdminService(settings=settings, store=SettingsStore(settings.data_root, settings.author_qq), project_root=tmp_path)

    payload = service.list_ai()
    updated = service.set_ai_profile_priority(["rightcodes", "openrouter-icu"])

    assert payload["fallback_order"] == ["openrouter-icu", "rightcodes"]
    assert updated["fallback_order"] == ["openrouter-icu", "rightcodes"]
    assert updated["current_profile"] == "rightcodes"
    with pytest.raises(ValueError):
        service.set_ai_profile_priority(["missing"])


def test_ai_output_mode_management_lists_and_updates_groups(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    GroupMessageLogStore(tmp_path / "run").append_message(
        group_id=10001,
        direction="incoming",
        user_id=605738729,
        sender_name="群友",
        text="你好",
        timestamp=1,
    )
    service.store.set_group_ai_output_mode(10002, "voice")

    initial = service.list_ai_output_modes({10001: "甲群", 10002: "乙群"})
    updated = service.set_group_ai_output_mode(10001, "voice", {10001: "甲群", 10002: "乙群"})
    bulk = service.set_all_group_ai_output_modes("text", {10001: "甲群", 10002: "乙群"})

    assert initial["default_mode"] == "text"
    assert initial["modes"] == ["text", "voice"]
    assert initial["groups"] == [
        {
            "group_id": 10001,
            "group_name": "甲群",
            "display_name": "甲群（10001）",
            "mode": "text",
            "source": "default",
        },
        {
            "group_id": 10002,
            "group_name": "乙群",
            "display_name": "乙群（10002）",
            "mode": "voice",
            "source": "group",
        },
    ]
    assert all(group["mode"] == "voice" for group in updated["groups"])
    assert all(group["mode"] == "text" for group in bulk["groups"])
    assert service.store.get_ai_output_mode(group_id=10001, user_id="605738729") == "text"
    assert service.store.get_ai_output_mode(group_id=10002, user_id="605738729") == "text"


def test_ai_output_mode_management_rejects_invalid_mode_and_group(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    with pytest.raises(ValueError):
        service.set_group_ai_output_mode(10001, "bad")
    with pytest.raises(ValueError):
        service.set_group_ai_output_mode(0, "voice")
    with pytest.raises(ValueError):
        service.set_all_group_ai_output_modes("bad")


def test_group_control_config_describes_current_policy(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    payload = service.get_group_control_config()

    assert payload == {
        "reread_policy": "consecutive_duplicate_once",
        "reread_description": "同一群连续两条相同消息时复读一次，后续相同消息不再复读，直到出现不同消息。",
        "random_thunder_enabled": False,
        "manual_controls": ["禁言", "解禁", "群禁言", "群解禁", "踢出"],
    }


def test_kun_admin_service_gets_and_updates_user(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    kun_service = KunService(tmp_path / "run" / "data" / "kun" / "users.json")
    kun_service.ensure_user(605738729)

    initial = service.get_kun_user(605738729)
    updated = service.update_kun_user(605738729, {"level": 3210, "money": 4567})

    assert initial["user"]["qq"] == 605738729
    assert updated["user"]["level"] == 3210
    assert updated["user"]["money"] == 4567


def test_kun_admin_service_lists_users_for_selection(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    kun_service = KunService(tmp_path / "run" / "data" / "kun" / "users.json")
    first = kun_service.ensure_user(10001)
    first.name = "甲鲲"
    first.level = 2000
    first.money = 300
    second = kun_service.ensure_user(10002)
    second.name = "乙鲲"
    second.level = 3000
    second.money = 200
    kun_service._save()
    nick_store = GroupNickStore(tmp_path / "run" / "settings" / "group_nick.json")
    nick_store.record_group_sender(
        group_id=516286670,
        qq=10002,
        card="本群乙",
        nickname="",
        updated_at=1,
    )

    payload = service.list_kun_users()

    assert payload["users"] == [
        {
            "qq": 10002,
            "name": "乙鲲",
            "level": 3000,
            "money": 200,
            "display_name": "本群乙（10002）",
        },
        {
            "qq": 10001,
            "name": "甲鲲",
            "level": 2000,
            "money": 300,
            "display_name": "10001",
        },
    ]


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


def test_list_group_messages_returns_recent_messages_with_group_names(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    log_store = GroupMessageLogStore(tmp_path / "run")
    log_store.append_message(
        group_id=516286670,
        direction="incoming",
        user_id=10001,
        sender_name="群友",
        text="左侧消息",
        timestamp=1,
    )
    log_store.append_message(
        group_id=516286670,
        direction="bot",
        user_id=30001,
        sender_name="Bot",
        text="右侧消息",
        timestamp=2,
    )

    payload = service.list_group_messages({516286670: "测试群"})

    assert payload["groups"][0]["display_name"] == "测试群（516286670）"
    assert [message["direction"] for message in payload["groups"][0]["messages"]] == [
        "incoming",
        "bot",
    ]


def test_memory_admin_service_rebuilds_debugs_and_updates_facts(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    memory_store = ChatMemoryStore(tmp_path / "run")
    memory_store.append_message(
        group_id=10001,
        message_id=201,
        direction="incoming",
        user_id=20001,
        sender_name="可可",
        text="可可喜欢研究数据库。",
        timestamp=100,
    )
    chat_fact = memory_store.search_facts(10001, "可可喜欢什么", limit=5)[0]

    debugged = service.debug_memory_search(10001, "可可喜欢什么")
    trusted = service.upsert_memory_fact(
        {
            "group_id": 10001,
            "subject": "萌泪酱",
            "predicate": "身份",
            "object": "Bot 管理员",
            "confidence": 1.0,
            "source_type": "system",
            "trust_level": "system",
            "topics": ["AI"],
            "entities": ["萌泪酱"],
        }
    )
    disabled = service.set_memory_fact_status(chat_fact.id, "disabled")
    rebuilt = service.rebuild_memory_facts(10001)

    assert rebuilt["messages_scanned"] == 1
    assert rebuilt["disabled_facts_restored"] == 1
    assert debugged["facts"][0]["subject"] == "可可"
    assert trusted["fact"]["object"] == "Bot 管理员"
    assert disabled["updated"] is True
    assert disabled["fact_id"] == chat_fact.id


def test_domain_knowledge_admin_service_seeds_and_updates_candidates(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    seeded = service.seed_domain_knowledge_candidates()
    listed = service.list_domain_knowledge(domain="shapez")
    target_id = listed["records"][0]["id"]
    updated = service.set_domain_knowledge_status(target_id, "trusted")

    assert len(seeded["records"]) >= 3
    assert {record["domain"] for record in seeded["records"]} >= {"shapez", "fractionate_everything"}
    assert any("萌新必看" in record["summary"] for record in listed["records"])
    assert updated == {"id": target_id, "status": "trusted", "updated": True}


def test_ai_pending_tasks_admin_service_lists_records(tmp_path: Path) -> None:
    from qqbot.services.ai_command import AiChatTriggerKind
    from qqbot.services.ai_message_decision import decide_ai_message
    from qqbot.services.ai_pending_task_store import AiPendingTaskStore
    from qqbot.services.message_normalizer import NormalizedMessage

    service = build_service(tmp_path)
    decision = decide_ai_message(
        trigger_kind=AiChatTriggerKind.PROACTIVE,
        normalized_message=NormalizedMessage(text="分馏塔卡死了 修一下", outline="分馏塔卡死了 修一下"),
        group_id=319567534,
    )
    AiPendingTaskStore(tmp_path / "run").create_ack_task(
        group_id=319567534,
        user_id=605738729,
        message_id=12345,
        prompt="分馏塔卡死了 修一下",
        decision=decision,
        now=100,
    )

    payload = service.list_ai_pending_tasks(status="ack_sent")

    assert payload["tasks"][0]["status"] == "ack_sent"
    assert payload["tasks"][0]["decision"]["fe_feedback_kind"] == "bug"


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
