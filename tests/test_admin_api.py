from pathlib import Path
import asyncio
import json

from fastapi import FastAPI

from qqbot.admin_api import register_admin_routes
from qqbot.config import RuntimeSettings
import qqbot.services.admin_service as admin_service_module
from qqbot.services.admin_service import AdminService
from qqbot.services.group_message_log_store import GroupMessageLogStore
from qqbot.services.group_nick_store import GroupNickStore
from qqbot.services.kun_service import KunService
from qqbot.services.settings_store import SettingsStore


class FakeUploadBot:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def call_api(self, api: str, **data: object) -> dict[str, object]:
        self.calls.append((api, data))
        return {"status": "ok"}


def build_app(tmp_path: Path) -> FastAPI:
    profile_file = tmp_path / "config" / "ai_providers.toml"
    profile_file.parent.mkdir(parents=True)
    profile_file.write_text(
        """
model_provider = "xiaomi"

[model_providers.xiaomi]
provider = "xiaomi_mimo"
base_url = "https://example.invalid/v1"
model = "mimo-v2.5-pro"
api_key_env = "QQBOT_AI_KEY_XIAOMI"
enabled = true

[model_providers.hicode]
provider = "openai_compatible"
base_url = "https://example.invalid/v1"
model = "gpt-5.5"
api_key_env = "QQBOT_AI_KEY_HICODE"
enabled = true
""".strip(),
        encoding="utf-8",
    )
    settings = RuntimeSettings(data_root=tmp_path / "run", ai_profile_file=profile_file)
    service = AdminService(
        settings=settings,
        store=SettingsStore(settings.data_root, settings.author_qq),
        project_root=tmp_path,
    )
    app = FastAPI()
    async def resolve_group_names() -> dict[int, str]:
        return {516286670: "测试群"}

    register_admin_routes(
        app,
        settings,
        service_factory=lambda: service,
        group_name_resolver=resolve_group_names,
    )
    return app


def asgi_request(
    app: FastAPI,
    method: str,
    path: str,
    json_body: dict[str, object] | None = None,
) -> tuple[int, str]:
    body = b""
    headers = []
    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        headers.append((b"content-type", b"application/json"))

    async def run_request() -> tuple[int, str]:
        sent_request = False
        status_code = 0
        body_parts: list[bytes] = []

        async def receive() -> dict[str, object]:
            nonlocal sent_request
            if sent_request:
                return {"type": "http.disconnect"}
            sent_request = True
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message: dict[str, object]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            if message["type"] == "http.response.body":
                body_parts.append(message.get("body", b""))

        await app(
            {
                "type": "http",
                "http_version": "1.1",
                "method": method,
                "path": path,
                "raw_path": path.encode("ascii"),
                "query_string": b"",
                "headers": headers,
                "client": ("127.0.0.1", 12345),
                "server": ("127.0.0.1", 8080),
                "scheme": "http",
            },
            receive,
            send,
        )
        return status_code, b"".join(body_parts).decode("utf-8")

    return asyncio.run(run_request())


def test_admin_page_returns_html(tmp_path: Path) -> None:
    app = build_app(tmp_path)

    status_code, body = asgi_request(app, "GET", "/admin")

    assert status_code == 200
    assert "QQBot Admin" in body
    assert "/admin/api/groups" in body
    assert "/admin/api/restart" in body
    assert "/admin/api/plugins" in body
    assert "/admin/api/ai" in body
    assert "群功能" not in body
    assert "/features" not in body
    assert "adminShell" in body
    assert "tab-button" in body
    assert "data-tab=\"realtimePanel\"" in body
    assert "data-tab=\"kunPanel\"" in body
    assert "data-tab=\"groupControlPanel\"" in body
    assert "重启 Bot" in body
    assert "全局插件" in body
    assert "AI 模型" in body
    assert "Codex 群绑定项目" in body
    assert "/admin/api/codex/group-bindings" in body
    assert "renderCodexProjectOption" in body
    assert "实时信息" in body
    assert "主控面板" not in body
    assert "id=\"realtimePanel\"" in body
    assert "群管管理" in body
    assert "群管配置" in body
    assert "/admin/api/group-control" in body
    assert "随机复读概率" in body
    assert "养鲲管理" in body
    assert "养鲲数据" in body
    assert "用户选择" in body
    assert "/admin/api/kun/users" in body
    assert "群消息" in body
    assert "/admin/api/group-messages" in body
    assert "全部群" not in body
    assert "selectLatestMessageGroup" in body
    assert "isMessageListAtBottom" in body
    assert "captureSelectedMessageScroll" in body
    assert "restoreSelectedMessageScroll" in body
    assert "scrollState.scrollTop" in body
    assert "scrollSelectedMessageListToBottom" in body
    assert "message-row" in body
    assert ".message-row.incoming" in body
    assert ".message-row.bot" in body


def test_groups_api_returns_configured_groups(tmp_path: Path) -> None:
    state_root = tmp_path / "run" / "settings" / "func_state"
    state_root.mkdir(parents=True)
    (state_root / "516286670.json").write_text('{"Arc": true}', encoding="utf-8")
    app = build_app(tmp_path)

    status_code, body = asgi_request(app, "GET", "/admin/api/groups")

    assert status_code == 200
    payload = json.loads(body)[0]
    assert payload["group_id"] == 516286670
    assert payload["display_name"] == "测试群（516286670）"


def test_group_messages_api_returns_grouped_realtime_messages(tmp_path: Path) -> None:
    store = GroupMessageLogStore(tmp_path / "run")
    store.append_message(
        group_id=516286670,
        direction="incoming",
        user_id=10001,
        sender_name="群友",
        text="左侧消息",
        timestamp=1,
    )
    store.append_message(
        group_id=516286670,
        direction="bot",
        user_id=30001,
        sender_name="Bot",
        text="右侧消息",
        timestamp=2,
    )
    app = build_app(tmp_path)

    status_code, body = asgi_request(app, "GET", "/admin/api/group-messages")

    assert status_code == 200
    payload = json.loads(body)
    assert payload["groups"][0]["display_name"] == "测试群（516286670）"
    assert [message["direction"] for message in payload["groups"][0]["messages"]] == [
        "incoming",
        "bot",
    ]


def test_upload_local_artifact_api_uploads_repo_zip(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    package = repo / "AfterBuildEvent" / "bin" / "win" / "Debug" / "ModZips" / "FractionateEverything_2.3.0.zip"
    package.parent.mkdir(parents=True)
    package.write_bytes(b"zip")
    bot = FakeUploadBot()
    monkeypatch.setattr("qqbot.admin_api.nonebot.get_bots", lambda: {"114514": bot})
    monkeypatch.setattr(
        "qqbot.admin_api.get_codex_project_by_id",
        lambda project_id: type(
            "Project",
            (),
            {
                "project_id": project_id,
                "display_name": "MLJ_DSPmods",
                "repo_path": str(repo),
            },
        )(),
        raising=False,
    )
    app = build_app(tmp_path)

    status_code, body = asgi_request(
        app,
        "POST",
        "/admin/api/artifacts/upload-local",
        json_body={
            "project_id": "mlj_dspmods",
            "group_id": 319567534,
            "files": [str(package)],
        },
    )

    assert status_code == 200
    assert json.loads(body) == {
        "ok": True,
        "uploaded": [
            {
                "file": str(package),
                "name": "FractionateEverything_2.3.0.zip",
            }
        ],
    }
    assert bot.calls == [
        (
            "upload_group_file",
            {
                "group_id": 319567534,
                "file": str(package),
                "name": "FractionateEverything_2.3.0.zip",
            },
        )
    ]


def test_upload_local_artifact_api_rejects_zip_outside_repo(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    package = tmp_path / "outside.zip"
    package.write_bytes(b"zip")
    bot = FakeUploadBot()
    monkeypatch.setattr("qqbot.admin_api.nonebot.get_bots", lambda: {"114514": bot})
    monkeypatch.setattr(
        "qqbot.admin_api.get_codex_project_by_id",
        lambda project_id: type(
            "Project",
            (),
            {
                "project_id": project_id,
                "display_name": "MLJ_DSPmods",
                "repo_path": str(repo),
            },
        )(),
        raising=False,
    )
    app = build_app(tmp_path)

    status_code, body = asgi_request(
        app,
        "POST",
        "/admin/api/artifacts/upload-local",
        json_body={
            "project_id": "mlj_dspmods",
            "group_id": 319567534,
            "files": [str(package)],
        },
    )

    assert status_code == 400
    assert "Artifact must be inside project repository" in body
    assert bot.calls == []


def test_plugins_api_lists_and_updates_global_state(tmp_path: Path) -> None:
    app = build_app(tmp_path)

    list_status, list_body = asgi_request(app, "GET", "/admin/api/plugins")
    update_status, update_body = asgi_request(
        app,
        "PUT",
        "/admin/api/plugins/arc",
        json_body={"enabled": False},
    )

    assert list_status == 200
    arc_plugin = next(plugin for plugin in json.loads(list_body)["plugins"] if plugin["id"] == "arc")
    assert arc_plugin["global_enabled"] is True
    assert update_status == 200
    assert json.loads(update_body)["plugin"]["global_enabled"] is False


def test_group_control_api_lists_and_updates_config(tmp_path: Path) -> None:
    app = build_app(tmp_path)

    list_status, list_body = asgi_request(
        app,
        "GET",
        "/admin/api/group-control",
    )
    update_status, update_body = asgi_request(
        app,
        "PUT",
        "/admin/api/group-control",
        json_body={
            "reread_probability_percent": 12.5,
            "thunder_probability_percent": 2.5,
            "min_seconds": 20,
            "max_seconds": 5,
        },
    )

    assert list_status == 200
    assert json.loads(list_body) == {
        "reread_chance": 0.05,
        "reread_probability_percent": 5.0,
        "thunder_chance": 0.05,
        "thunder_probability_percent": 5.0,
        "thunder_min_seconds": 5,
        "thunder_max_seconds": 20,
    }
    assert update_status == 200
    assert json.loads(update_body) == {
        "reread_chance": 0.125,
        "reread_probability_percent": 12.5,
        "thunder_chance": 0.025,
        "thunder_probability_percent": 2.5,
        "thunder_min_seconds": 5,
        "thunder_max_seconds": 20,
    }


def test_kun_api_gets_and_updates_user(tmp_path: Path) -> None:
    KunService(tmp_path / "run" / "data" / "kun" / "users.json").ensure_user(605738729)
    app = build_app(tmp_path)

    list_status, list_body = asgi_request(
        app,
        "GET",
        "/admin/api/kun/users/605738729",
    )
    update_status, update_body = asgi_request(
        app,
        "PUT",
        "/admin/api/kun/users/605738729",
        json_body={"updates": {"level": 3210, "money": 4567}},
    )

    assert list_status == 200
    assert json.loads(list_body)["user"]["qq"] == 605738729
    assert update_status == 200
    updated = json.loads(update_body)
    assert updated["user"]["level"] == 3210
    assert updated["user"]["money"] == 4567


def test_kun_api_lists_users_for_selection(tmp_path: Path) -> None:
    kun_service = KunService(tmp_path / "run" / "data" / "kun" / "users.json")
    first = kun_service.ensure_user(10001)
    first.name = "甲鲲"
    first.level = 2000
    second = kun_service.ensure_user(10002)
    second.name = "乙鲲"
    second.level = 3000
    kun_service._save()
    app = build_app(tmp_path)

    status_code, body = asgi_request(app, "GET", "/admin/api/kun/users")

    assert status_code == 200
    payload = json.loads(body)
    assert [item["qq"] for item in payload["users"]] == [10002, 10001]
    assert payload["users"][0]["name"] == "乙鲲"


def test_ai_api_lists_and_updates_current_provider(tmp_path: Path) -> None:
    app = build_app(tmp_path)

    list_status, list_body = asgi_request(app, "GET", "/admin/api/ai")
    update_status, update_body = asgi_request(
        app,
        "PUT",
        "/admin/api/ai/provider",
        json_body={"profile": "hicode"},
    )

    assert list_status == 200
    payload = json.loads(list_body)
    assert payload["current_profile"] == "xiaomi"
    assert [profile["name"] for profile in payload["profiles"]] == ["xiaomi", "hicode"]
    assert "supports_vision" not in payload["profiles"][0]
    assert update_status == 200
    assert json.loads(update_body)["current_profile"] == "hicode"


def test_ai_api_rejects_unknown_provider(tmp_path: Path) -> None:
    app = build_app(tmp_path)

    status_code, body = asgi_request(
        app,
        "PUT",
        "/admin/api/ai/provider",
        json_body={"profile": "missing"},
    )

    assert status_code == 404
    assert "Unknown AI profile" in body


def test_codex_group_bindings_api_lists_and_updates_runtime_binding(tmp_path: Path) -> None:
    app = build_app(tmp_path)

    list_status, list_body = asgi_request(app, "GET", "/admin/api/codex/group-bindings")
    update_status, update_body = asgi_request(
        app,
        "PUT",
        "/admin/api/codex/group-bindings/516286670",
        json_body={"project_id": "qqbot"},
    )

    assert list_status == 200
    list_payload = json.loads(list_body)
    default_group = next(group for group in list_payload["groups"] if group["group_id"] == 319567534)
    assert default_group["effective_project_id"] == "mlj_dspmods"
    assert default_group["source"] == "default"
    assert update_status == 200
    update_payload = json.loads(update_body)
    updated_group = next(group for group in update_payload["groups"] if group["group_id"] == 516286670)
    assert updated_group["project_id"] == "qqbot"
    assert updated_group["effective_project_id"] == "qqbot"
    assert updated_group["source"] == "runtime"


def test_codex_group_bindings_api_rejects_unknown_project(tmp_path: Path) -> None:
    app = build_app(tmp_path)

    status_code, body = asgi_request(
        app,
        "PUT",
        "/admin/api/codex/group-bindings/516286670",
        json_body={"project_id": "missing"},
    )

    assert status_code == 404
    assert "Unknown Codex project" in body


def test_admin_endpoints_update_admin_state(tmp_path: Path) -> None:
    nick_store = GroupNickStore(tmp_path / "run" / "settings" / "group_nick.json")
    nick_store.record_group_sender(
        group_id=516286670,
        qq=10001,
        card="测试管理员",
        nickname="",
        updated_at=1,
    )
    app = build_app(tmp_path)

    add_status, add_body = asgi_request(
        app,
        "POST",
        "/admin/api/admins",
        json_body={"qq": 10001},
    )
    delete_status, delete_body = asgi_request(app, "DELETE", "/admin/api/admins/10001")

    assert add_status == 200
    add_payload = json.loads(add_body)
    assert add_payload["admins"] == [10001]
    assert add_payload["admin_items"] == [
        {"qq": 10001, "name": "测试管理员", "display_name": "测试管理员（10001）"}
    ]
    assert delete_status == 200
    assert json.loads(delete_body)["admins"] == []


def test_restart_endpoint_schedules_restart(tmp_path: Path, monkeypatch) -> None:
    script = tmp_path / "scripts" / "start_all.bat"
    script.parent.mkdir(parents=True)
    script.write_text("@echo off\n", encoding="utf-8")
    calls: list[dict[str, object]] = []

    def fake_popen(*args: object, **kwargs: object) -> object:
        calls.append({"args": args, "kwargs": kwargs})
        return object()

    monkeypatch.setattr(admin_service_module.subprocess, "Popen", fake_popen)
    app = build_app(tmp_path)

    status_code, body = asgi_request(app, "POST", "/admin/api/restart")

    assert status_code == 200
    assert json.loads(body)["scheduled"] is True
    assert len(calls) == 1


def test_log_endpoint_returns_tail_content(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs" / "start_all" / "20260425-123456"
    log_dir.mkdir(parents=True)
    (log_dir / "launcher.log").write_text("started\nconnected\n", encoding="utf-8")
    app = build_app(tmp_path)

    status_code, body = asgi_request(
        app,
        "GET",
        "/admin/api/logs/20260425-123456/launcher.log",
    )

    assert status_code == 200
    assert json.loads(body)["content"] == "started\nconnected"
