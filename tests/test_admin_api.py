from pathlib import Path
import asyncio
import json

from fastapi import FastAPI

from qqbot.admin_api import register_admin_routes
from qqbot.config import RuntimeSettings
import qqbot.services.admin_service as admin_service_module
from qqbot.services.admin_service import AdminService
from qqbot.services.group_nick_store import GroupNickStore
from qqbot.services.settings_store import SettingsStore


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
    assert "重启 Bot" in body
    assert "全局插件" in body
    assert "AI 模型" in body


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


def test_group_feature_toggle_updates_state(tmp_path: Path) -> None:
    state_root = tmp_path / "run" / "settings" / "func_state"
    state_root.mkdir(parents=True)
    (state_root / "516286670.json").write_text('{"Arc狼人杀": true}', encoding="utf-8")
    app = build_app(tmp_path)

    status_code, body = asgi_request(
        app,
        "PUT",
        "/admin/api/groups/516286670/features/13",
        json_body={"enabled": False},
    )

    assert status_code == 200
    assert json.loads(body)["feature"]["enabled"] is False
    text = (state_root / "516286670.json").read_text(encoding="utf-8")
    assert '"Arc": false' in text
    assert "Arc狼人杀" not in text


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
