from pathlib import Path
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fastapi import FastAPI

from qqbot.admin_api import get_connected_group_names, register_admin_routes
from qqbot.config import RuntimeSettings
import qqbot.services.admin_service as admin_service_module
from qqbot.services.admin_service import AdminService
from qqbot.services.ai_diagnostics import (
    AiAttemptDiagnostics,
    AiDiagnosticsStore,
    build_ai_diagnostics_record,
)
from qqbot.services.chat_memory_store import ChatMemoryStore
from qqbot.services.group_message_log_store import GroupMessageLogStore
from qqbot.services.group_nick_store import GroupNickStore
from qqbot.services.kun_service import KunService
from qqbot.services.settings_store import SettingsStore


class FakeUploadBot:
    self_id = "114514"

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.group_files: list[dict[str, object]] = []

    async def call_api(self, api: str, **data: object) -> dict[str, object]:
        self.calls.append((api, data))
        if api == "get_group_root_files":
            return {"files": list(self.group_files)}
        if api == "upload_group_file":
            return {"message_id": 24680}
        return {"status": "ok"}


class FakeSlowGroupListBot:
    async def call_api(self, api: str, **data: object) -> list[dict[str, object]]:
        await asyncio.sleep(1)
        return [{"group_id": 516286670, "group_name": "测试群"}]


def build_app(
    tmp_path: Path,
    group_name_resolver=None,
) -> FastAPI:
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
        group_name_resolver=group_name_resolver or resolve_group_names,
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

    assert status_code == 200, body
    assert "QQBot Admin" in body
    assert "/admin/api/groups" in body
    assert "/admin/api/restart" in body
    assert "/admin/api/plugins" in body
    assert "/admin/api/ai" in body
    assert "/admin/api/ai/diagnostics" in body
    assert "/admin/api/ai/output-modes" in body
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
    assert "/admin/api/ai/profile-priority" in body
    assert "AI 回复模式" in body
    assert "AI 诊断" in body
    assert "AI 主动介入" not in body
    assert "/admin/api/ai/proactive-modes" not in body
    assert "Codex 群绑定项目" in body
    assert "/admin/api/codex/group-bindings" in body
    assert "renderCodexProjectOption" in body
    assert "实时信息" in body
    assert "主控面板" not in body
    assert "id=\"realtimePanel\"" in body
    assert "群管管理" in body
    assert "群管配置" in body
    assert "/admin/api/group-control" in body
    assert "随机复读概率" not in body
    assert "随机禁言概率" not in body
    assert "已移除自动随机禁言" in body
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
    assert "loadAiDiagnostics" in body
    assert "loadAiOutputModes" in body
    assert "saveAllAiOutputModes" in body
    assert "saveGroupAiProactiveMode" not in body
    assert "message-row" in body
    assert ".message-row.incoming" in body
    assert ".message-row.bot" in body
    assert "长期记忆" in body
    assert "/admin/api/memory/debug" in body
    assert "/admin/api/memory/facts/rebuild" in body
    assert "/admin/api/memory/facts" in body


def test_groups_api_returns_configured_groups(tmp_path: Path) -> None:
    state_root = tmp_path / "run" / "settings" / "func_state"
    state_root.mkdir(parents=True)
    (state_root / "516286670.json").write_text('{"Arc": true}', encoding="utf-8")
    app = build_app(tmp_path)

    status_code, body = asgi_request(app, "GET", "/admin/api/groups")

    assert status_code == 200, body
    payload = json.loads(body)[0]
    assert payload["group_id"] == 516286670
    assert payload["display_name"] == "测试群（516286670）"


def test_ai_proactive_mode_api_is_removed(tmp_path: Path) -> None:
    app = build_app(tmp_path)

    status_code, body = asgi_request(
        app,
        "PUT",
        "/admin/api/ai/proactive-modes/516286670",
        {"enabled": True},
    )

    assert status_code == 404, body


def test_get_connected_group_names_skips_slow_onebot_api(monkeypatch) -> None:
    monkeypatch.setattr(
        "qqbot.admin_api.nonebot.get_bots",
        lambda: {"114514": FakeSlowGroupListBot()},
    )

    names = asyncio.run(get_connected_group_names(timeout_seconds=0.01))

    assert names == {}


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


def test_memory_admin_api_debugs_rebuilds_and_updates_facts(tmp_path: Path) -> None:
    memory_store = ChatMemoryStore(tmp_path / "run")
    memory_store.append_message(
        group_id=516286670,
        message_id=221,
        direction="incoming",
        user_id=10001,
        sender_name="可可",
        text="可可喜欢研究数据库。",
        timestamp=100,
    )
    chat_fact = memory_store.search_facts(516286670, "可可喜欢什么", limit=5)[0]
    app = build_app(tmp_path)

    debug_status, debug_body = asgi_request(
        app,
        "POST",
        "/admin/api/memory/debug",
        json_body={"group_id": 516286670, "query": "可可喜欢什么", "limit": 5},
    )
    upsert_status, upsert_body = asgi_request(
        app,
        "POST",
        "/admin/api/memory/facts",
        json_body={
            "group_id": 516286670,
            "subject": "萌泪酱",
            "predicate": "身份",
            "object": "Bot 管理员",
            "confidence": 1.0,
            "source_type": "system",
            "trust_level": "system",
            "topics": ["AI"],
            "entities": ["萌泪酱"],
        },
    )
    disable_status, disable_body = asgi_request(
        app,
        "PUT",
        f"/admin/api/memory/facts/{chat_fact.id}",
        json_body={"status": "disabled"},
    )
    rebuild_status, rebuild_body = asgi_request(
        app,
        "POST",
        "/admin/api/memory/facts/rebuild",
        json_body={"group_id": 516286670},
    )

    assert debug_status == 200
    assert json.loads(debug_body)["facts"][0]["subject"] == "可可"
    assert rebuild_status == 200
    assert json.loads(rebuild_body)["messages_scanned"] == 1
    assert json.loads(rebuild_body)["disabled_facts_restored"] == 1
    assert upsert_status == 200
    assert json.loads(upsert_body)["fact"]["object"] == "Bot 管理员"
    assert disable_status == 200
    assert json.loads(disable_body) == {"fact_id": chat_fact.id, "status": "disabled", "updated": True}


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

    assert status_code == 200, body
    assert json.loads(body) == {
        "ok": True,
        "uploaded": [
            {
                "file": str(package),
                "name": "FractionateEverything_2.3.0.zip",
            }
        ],
        "deleted": [],
        "skipped": False,
        "reason": "",
    }
    assert bot.calls == [
        (
            "get_group_root_files",
            {
                "group_id": 319567534,
            },
        ),
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
    package = tmp_path / "FractionateEverything_2.3.0.zip"
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


def test_publish_fe_artifact_deletes_old_fe_zips_and_uploads_only_fe(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    modzips = repo / "AfterBuildEvent" / "bin" / "win" / "Debug" / "ModZips"
    fe_package = modzips / "FractionateEverything_2.3.0.zip"
    get_data_package = modzips / "GetDspData_1.0.0.zip"
    modzips.mkdir(parents=True)
    fe_package.write_bytes(b"fe")
    get_data_package.write_bytes(b"get-data")
    bot = FakeUploadBot()
    bot.group_files = [
        {
            "file_id": "old-fe-1",
            "busid": 1,
            "file_name": "FractionateEverything_2.2.9.zip",
            "uploader": 114514,
        },
        {
            "file_id": "old-fe-2",
            "busid": 2,
            "file_name": "FractionateEverything_2.3.0.zip",
            "uploader": 114514,
        },
        {
            "file_id": "keep-get-data",
            "busid": 3,
            "file_name": "GetDspData_1.0.0.zip",
            "uploader": 114514,
        },
        {
            "file_id": "keep-user-fe",
            "busid": 4,
            "file_name": "FractionateEverything_2.0.0.zip",
            "uploader": 10001,
        },
    ]
    monkeypatch.setattr("qqbot.admin_api.nonebot.get_bots", lambda: {"114514": bot})
    monkeypatch.setattr(
        "qqbot.services.fe_artifact_publish_service.read_latest_commit_summary",
        lambda repo_path: type(
            "Commit",
            (),
            {
                "short_hash": "c251753",
                "title": "修复：避免分馏处理器静态初始化崩溃",
                "body": "",
            },
        )(),
    )
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
            "files": [str(fe_package)],
            "message": "原因：用户反馈启动崩溃\n修复：避免 ProcessManager 静态初始化读取未就绪字段",
        },
    )

    assert status_code == 200, body
    assert json.loads(body) == {
        "ok": True,
        "uploaded": [
            {
                "file": str(fe_package),
                "name": "FractionateEverything_2.3.0.zip",
            }
        ],
        "deleted": [
            "FractionateEverything_2.2.9.zip",
            "FractionateEverything_2.3.0.zip",
        ],
        "skipped": False,
        "reason": "",
    }
    assert bot.calls == [
        (
            "get_group_root_files",
            {
                "group_id": 319567534,
            },
        ),
        (
            "delete_group_file",
            {
                "group_id": 319567534,
                "file_id": "old-fe-1",
                "busid": 1,
            },
        ),
        (
            "delete_group_file",
            {
                "group_id": 319567534,
                "file_id": "old-fe-2",
                "busid": 2,
            },
        ),
        (
            "upload_group_file",
            {
                "group_id": 319567534,
                "file": str(fe_package),
                "name": "FractionateEverything_2.3.0.zip",
            },
        ),
        (
            "send_group_msg",
            {
                "group_id": 319567534,
                "message": (
                    "[CQ:reply,id=24680]c251753 修复：避免分馏处理器静态初始化崩溃\n\n"
                    "根本原因：\n"
                    "用户反馈启动崩溃\n\n"
                    "修复方式：\n"
                    "避免 ProcessManager 静态初始化读取未就绪字段"
                ),
            },
        ),
    ]


def test_publish_fe_artifact_skips_unchanged_fe_zip(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    modzips = repo / "AfterBuildEvent" / "bin" / "win" / "Debug" / "ModZips"
    fe_package = modzips / "FractionateEverything_2.3.0.zip"
    modzips.mkdir(parents=True)
    fe_package.write_bytes(b"same-fe-content")
    sha256 = __import__("hashlib").sha256(fe_package.read_bytes()).hexdigest()
    state_path = tmp_path / "run" / "fe_artifacts" / "319567534.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps({"sha256": sha256}), encoding="utf-8")
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
            "files": [str(fe_package)],
            "message": "原因：这次 FE 包没变",
        },
    )

    assert status_code == 200, body
    assert json.loads(body) == {
        "ok": True,
        "uploaded": [],
        "deleted": [],
        "skipped": True,
        "reason": "FE package sha256 unchanged.",
    }
    assert bot.calls == []


def test_publish_local_artifacts_uploads_declared_files_to_multiple_groups(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    modzips = repo / "AfterBuildEvent" / "bin" / "Debug" / "ModZips"
    package = modzips / "MyNewMod_1.0.0.zip"
    modzips.mkdir(parents=True)
    package.write_bytes(b"new-mod")
    package_sha = __import__("hashlib").sha256(package.read_bytes()).hexdigest()
    bot = FakeUploadBot()
    bot.group_files = [
        {
            "file_id": "old-same-name",
            "busid": 1,
            "file_name": "MyNewMod_1.0.0.zip",
            "uploader": 114514,
        },
        {
            "file_id": "keep-other-name",
            "busid": 2,
            "file_name": "OtherMod_1.0.0.zip",
            "uploader": 114514,
        },
        {
            "file_id": "keep-user-upload",
            "busid": 3,
            "file_name": "MyNewMod_1.0.0.zip",
            "uploader": 10001,
        },
    ]
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
    monkeypatch.setattr(
        "qqbot.admin_api._read_git_output",
        lambda repo_path, *args: "master-224"
        if args == ("branch", "--show-current")
        else "abcdef1234567890",
    )
    app = build_app(tmp_path)

    status_code, body = asgi_request(
        app,
        "POST",
        "/admin/api/artifacts/publish-local",
        json_body={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "project_id": "mlj_dspmods",
            "branch": "master-224",
            "commit_hash": "abcdef1234567890",
            "commit_subject": "功能：发布新模组",
            "commit_detail": "原因：新增测试包\n新增：MyNewMod 发布\n验证：AfterBuildEvent 1 成功",
            "files": [
                {
                    "path": str(package),
                    "sha256": package_sha,
                    "targets": [319567534, 516286670],
                }
            ],
        },
    )

    assert status_code == 200, body
    assert json.loads(body) == {
        "ok": True,
        "uploaded": [
            {
                "group_id": 319567534,
                "file": str(package),
                "name": "MyNewMod_1.0.0.zip",
                "sha256": package_sha,
            },
            {
                "group_id": 516286670,
                "file": str(package),
                "name": "MyNewMod_1.0.0.zip",
                "sha256": package_sha,
            },
        ],
        "deleted": [
            {"group_id": 319567534, "name": "MyNewMod_1.0.0.zip"},
            {"group_id": 516286670, "name": "MyNewMod_1.0.0.zip"},
        ],
    }
    assert bot.calls == [
        (
            "get_group_root_files",
            {
                "group_id": 319567534,
            },
        ),
        (
            "delete_group_file",
            {
                "group_id": 319567534,
                "file_id": "old-same-name",
                "busid": 1,
            },
        ),
        (
            "upload_group_file",
            {
                "group_id": 319567534,
                "file": str(package),
                "name": "MyNewMod_1.0.0.zip",
            },
        ),
        (
            "send_group_msg",
            {
                "group_id": 319567534,
                "message": (
                    "[CQ:reply,id=24680]abcdef1 功能：发布新模组\n\n"
                    "分支：master-224\n\n"
                    "背景原因：\n"
                    "新增测试包\n\n"
                    "新增能力：\n"
                    "MyNewMod 发布\n\n"
                    "验证：\n"
                    "AfterBuildEvent 1 成功"
                ),
            },
        ),
        (
            "get_group_root_files",
            {
                "group_id": 516286670,
            },
        ),
        (
            "delete_group_file",
            {
                "group_id": 516286670,
                "file_id": "old-same-name",
                "busid": 1,
            },
        ),
        (
            "upload_group_file",
            {
                "group_id": 516286670,
                "file": str(package),
                "name": "MyNewMod_1.0.0.zip",
            },
        ),
        (
            "send_group_msg",
            {
                "group_id": 516286670,
                "message": (
                    "[CQ:reply,id=24680]abcdef1 功能：发布新模组\n\n"
                    "分支：master-224\n\n"
                    "背景原因：\n"
                    "新增测试包\n\n"
                    "新增能力：\n"
                    "MyNewMod 发布\n\n"
                    "验证：\n"
                    "AfterBuildEvent 1 成功"
                ),
            },
        ),
    ]


def test_publish_local_artifacts_rejects_stale_request(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    package = repo / "ModZips" / "MyNewMod_1.0.0.zip"
    package.parent.mkdir(parents=True)
    package.write_bytes(b"new-mod")
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
    monkeypatch.setattr(
        "qqbot.admin_api._read_git_output",
        lambda repo_path, *args: "master"
        if args == ("branch", "--show-current")
        else "abcdef1234567890",
    )
    app = build_app(tmp_path)

    status_code, body = asgi_request(
        app,
        "POST",
        "/admin/api/artifacts/publish-local",
        json_body={
            "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
            "project_id": "mlj_dspmods",
            "files": [{"path": str(package), "targets": [319567534]}],
        },
    )

    assert status_code == 400
    assert "Publish request timestamp is stale" in body
    assert bot.calls == []


def test_publish_local_artifacts_rejects_wrong_branch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    package = repo / "ModZips" / "MyNewMod_1.0.0.zip"
    package.parent.mkdir(parents=True)
    package.write_bytes(b"new-mod")
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
    monkeypatch.setattr(
        "qqbot.admin_api._read_git_output",
        lambda repo_path, *args: "master"
        if args == ("branch", "--show-current")
        else "abcdef1234567890",
    )
    app = build_app(tmp_path)

    status_code, body = asgi_request(
        app,
        "POST",
        "/admin/api/artifacts/publish-local",
        json_body={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "project_id": "mlj_dspmods",
            "branch": "master-224",
            "commit_hash": "abcdef1234567890",
            "commit_detail": "验证：不会发送",
            "files": [{"path": str(package), "targets": [319567534]}],
        },
    )

    assert status_code == 400
    assert "Publish branch does not match project checkout" in body
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


def test_group_control_api_lists_policy(tmp_path: Path) -> None:
    app = build_app(tmp_path)

    list_status, list_body = asgi_request(
        app,
        "GET",
        "/admin/api/group-control",
    )
    update_status, _update_body = asgi_request(app, "PUT", "/admin/api/group-control")

    assert list_status == 200
    assert json.loads(list_body) == {
        "reread_policy": "consecutive_duplicate_once",
        "reread_description": "同一群连续两条相同消息时复读一次，后续相同消息不再复读，直到出现不同消息。",
        "random_thunder_enabled": False,
        "manual_controls": ["禁言", "解禁", "群禁言", "群解禁", "踢出"],
    }
    assert update_status == 405


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
    assert payload["fallback_order"] == ["hicode", "xiaomi"]
    assert "supports_vision" not in payload["profiles"][0]
    assert update_status == 200
    assert json.loads(update_body)["current_profile"] == "hicode"
    assert json.loads(update_body)["fallback_order"][0] == "hicode"


def test_ai_api_updates_profile_priority(tmp_path: Path) -> None:
    app = build_app(tmp_path)

    status_code, body = asgi_request(
        app,
        "PUT",
        "/admin/api/ai/profile-priority",
        json_body={"profiles": ["xiaomi", "hicode"]},
    )

    assert status_code == 200
    payload = json.loads(body)
    assert payload["current_profile"] == "xiaomi"
    assert payload["fallback_order"] == ["xiaomi", "hicode"]


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


def test_ai_output_mode_api_lists_and_updates_group_modes(tmp_path: Path) -> None:
    app = build_app(tmp_path)

    list_status, list_body = asgi_request(app, "GET", "/admin/api/ai/output-modes")
    update_status, update_body = asgi_request(
        app,
        "PUT",
        "/admin/api/ai/output-modes/516286670",
        json_body={"mode": "voice"},
    )
    bulk_status, bulk_body = asgi_request(
        app,
        "PUT",
        "/admin/api/ai/output-modes/all",
        json_body={"mode": "text"},
    )

    assert list_status == 200
    list_payload = json.loads(list_body)
    assert list_payload["groups"] == []
    assert update_status == 200
    updated_group = json.loads(update_body)["groups"][0]
    assert updated_group["display_name"] == "516286670"
    assert updated_group["mode"] == "voice"
    assert updated_group["source"] == "group"
    assert bulk_status == 200
    assert json.loads(bulk_body)["groups"][0]["mode"] == "text"


def test_ai_output_mode_api_rejects_invalid_mode(tmp_path: Path) -> None:
    app = build_app(tmp_path)

    status_code, body = asgi_request(
        app,
        "PUT",
        "/admin/api/ai/output-modes/516286670",
        json_body={"mode": "bad"},
    )

    assert status_code == 400
    assert "AI output mode must be text or voice" in body


def test_ai_output_mode_update_api_does_not_wait_for_group_names(tmp_path: Path) -> None:
    async def slow_group_names() -> dict[int, str]:
        await asyncio.sleep(0.1)
        raise AssertionError("update routes must not refresh connected group names")

    app = build_app(tmp_path, group_name_resolver=slow_group_names)

    group_status, group_body = asgi_request(
        app,
        "PUT",
        "/admin/api/ai/output-modes/516286670",
        json_body={"mode": "voice"},
    )
    bulk_status, bulk_body = asgi_request(
        app,
        "PUT",
        "/admin/api/ai/output-modes/all",
        json_body={"mode": "text"},
    )

    assert group_status == 200, group_body
    assert json.loads(group_body)["groups"][0]["display_name"] == "516286670"
    assert bulk_status == 200, bulk_body
    assert json.loads(bulk_body)["groups"][0]["mode"] == "text"


def test_ai_diagnostics_api_returns_summary(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    store = AiDiagnosticsStore(tmp_path / "run")
    store.append(
        build_ai_diagnostics_record(
            profile="xiaomi",
            provider="xiaomi_mimo",
            model="mimo-v2.5-pro",
            scope="private",
            group_id="",
            user_id="605738729",
            fallback=False,
            fallback_reason="",
            prompt_chars=12,
            context_chars=34,
            history_messages=2,
            image_count=0,
            local_prepare_seconds=0.25,
            total_seconds=1.25,
            queue_wait_seconds=0.5,
            prepare_stages={"context": 0.2},
            attempts=(
                AiAttemptDiagnostics(
                    attempt=1,
                    timeout_seconds=12.0,
                    result="success",
                    total_seconds=1.0,
                    first_token_seconds=0.35,
                    completion_tokens=5,
                    output_chars=20,
                ),
            ),
            now=1777777777,
        )
    )

    status_code, body = asgi_request(app, "GET", "/admin/api/ai/diagnostics")

    assert status_code == 200
    payload = json.loads(body)
    assert payload["count"] == 1
    assert payload["success_count"] == 1
    assert payload["avg_queue_wait_seconds"] == 0.5
    assert payload["avg_prepare_stages"] == {"context": 0.2}
    assert payload["avg_first_token_seconds"] == 0.35
    assert payload["records"][0]["profile"] == "xiaomi"
    assert payload["records"][0]["queue_wait_seconds"] == 0.5
    assert payload["records"][0]["prepare_stages"] == {"context": 0.2}
    assert payload["records"][0]["prompt_chars"] == 12


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
