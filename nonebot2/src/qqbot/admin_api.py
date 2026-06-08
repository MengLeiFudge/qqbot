from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
import subprocess

import nonebot
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from qqbot.config import RuntimeSettings
from qqbot.services.admin_service import AdminService
from qqbot.features.artifacts.publish_service import (
    LocalArtifactPublishContext,
    LocalArtifactPublishFile,
    publish_local_artifacts,
)
from qqbot.services.group_file_cleanup_service import (
    SHAPEZ_GROUP_ID,
    GroupFileInfo,
    ShapezGroupFileCleanupService,
    ShapezGroupFileCleanupStore,
)

LOCAL_CLIENT_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}
ONEBOT_GROUP_LIST_TIMEOUT_SECONDS = 2.0
LOCAL_ARTIFACT_PUBLISH_MAX_AGE_SECONDS = 5 * 60


class FeatureToggleRequest(BaseModel):
    enabled: bool


class AiProviderUpdateRequest(BaseModel):
    profile: str


class AiProfilePriorityUpdateRequest(BaseModel):
    profiles: list[str]


class ShapezFileCleanupUnmuteRequest(BaseModel):
    user_id: int


class LocalArtifactPublishFileRequest(BaseModel):
    path: str
    name: str = ""
    sha256: str = ""
    targets: list[int]
    message: str = ""


class LocalArtifactPublishRequest(BaseModel):
    timestamp: str
    project_id: str
    branch: str = ""
    commit_hash: str = ""
    commit_subject: str = ""
    commit_detail: str = ""
    files: list[LocalArtifactPublishFileRequest]


class KunUserUpdateRequest(BaseModel):
    updates: dict[str, object]


class MemoryDebugRequest(BaseModel):
    group_id: int
    query: str
    limit: int = 6


class MemoryRebuildRequest(BaseModel):
    group_id: int


class MemoryFactUpsertRequest(BaseModel):
    group_id: int
    subject: str
    predicate: str
    object: str
    confidence: float = 1.0
    source_type: str = "system"
    trust_level: str = "system"
    topics: list[str] = []
    entities: list[str] = []


class MemoryFactStatusRequest(BaseModel):
    status: str


class KnowledgeStatusRequest(BaseModel):
    status: str


def register_admin_routes(
    app: FastAPI,
    settings: RuntimeSettings,
    service_factory: Callable[[], AdminService] | None = None,
    group_name_resolver: Callable[[], Awaitable[dict[int, str]]] | None = None,
) -> None:
    factory = service_factory or (lambda: AdminService.from_settings(settings))
    resolve_group_names = group_name_resolver or get_connected_group_names

    async def require_local_request(request: Request) -> None:
        host = request.client.host if request.client else ""
        if host not in LOCAL_CLIENT_HOSTS:
            raise HTTPException(status_code=403, detail="Admin console is local-only.")

    def service() -> AdminService:
        return factory()

    @app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
    async def admin_page(_: None = Depends(require_local_request)) -> HTMLResponse:
        return HTMLResponse(build_admin_html(settings))

    @app.get("/admin/api/status")
    async def admin_status(
        _: None = Depends(require_local_request),
        admin_service: AdminService = Depends(service),
    ) -> dict[str, object]:
        return admin_service.get_status(connected_bot_count=len(nonebot.get_bots()))

    @app.post("/admin/api/restart")
    async def admin_restart(
        _: None = Depends(require_local_request),
        admin_service: AdminService = Depends(service),
    ) -> dict[str, object]:
        try:
            return admin_service.schedule_restart()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/admin/api/groups")
    async def admin_groups(
        _: None = Depends(require_local_request),
        admin_service: AdminService = Depends(service),
    ) -> list[dict[str, object]]:
        return admin_service.list_groups(await resolve_group_names())

    @app.get("/admin/api/group-messages")
    async def admin_group_messages(
        _: None = Depends(require_local_request),
        admin_service: AdminService = Depends(service),
    ) -> dict[str, object]:
        return admin_service.list_group_messages(await resolve_group_names())

    @app.post("/admin/api/memory/debug")
    async def admin_memory_debug(
        payload: MemoryDebugRequest,
        _: None = Depends(require_local_request),
        admin_service: AdminService = Depends(service),
    ) -> dict[str, object]:
        return admin_service.debug_memory_search(payload.group_id, payload.query, payload.limit)

    @app.post("/admin/api/memory/facts/rebuild")
    async def admin_memory_rebuild_facts(
        payload: MemoryRebuildRequest,
        _: None = Depends(require_local_request),
        admin_service: AdminService = Depends(service),
    ) -> dict[str, int]:
        return admin_service.rebuild_memory_facts(payload.group_id)

    @app.post("/admin/api/memory/facts")
    async def admin_memory_upsert_fact(
        payload: MemoryFactUpsertRequest,
        _: None = Depends(require_local_request),
        admin_service: AdminService = Depends(service),
    ) -> dict[str, object]:
        try:
            return admin_service.upsert_memory_fact(payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.put("/admin/api/memory/facts/{fact_id}")
    async def admin_memory_update_fact_status(
        fact_id: int,
        payload: MemoryFactStatusRequest,
        _: None = Depends(require_local_request),
        admin_service: AdminService = Depends(service),
    ) -> dict[str, object]:
        try:
            return admin_service.set_memory_fact_status(fact_id, payload.status)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/admin/api/knowledge")
    async def admin_domain_knowledge(
        status: str = "",
        domain: str = "",
        limit: int = 100,
        _: None = Depends(require_local_request),
        admin_service: AdminService = Depends(service),
    ) -> dict[str, object]:
        return admin_service.list_domain_knowledge(status=status, domain=domain, limit=limit)

    @app.post("/admin/api/knowledge/scan")
    async def admin_domain_knowledge_scan(
        _: None = Depends(require_local_request),
        admin_service: AdminService = Depends(service),
    ) -> dict[str, object]:
        return admin_service.seed_domain_knowledge_candidates()

    @app.put("/admin/api/knowledge/{record_id}")
    async def admin_domain_knowledge_update(
        record_id: str,
        payload: KnowledgeStatusRequest,
        _: None = Depends(require_local_request),
        admin_service: AdminService = Depends(service),
    ) -> dict[str, object]:
        try:
            return admin_service.set_domain_knowledge_status(record_id, payload.status)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/admin/api/ai/pending-tasks")
    async def admin_ai_pending_tasks(
        status: str = "",
        limit: int = 100,
        _: None = Depends(require_local_request),
        admin_service: AdminService = Depends(service),
    ) -> dict[str, object]:
        return admin_service.list_ai_pending_tasks(status=status, limit=limit)

    @app.get("/admin/api/plugins")
    async def admin_plugins(
        _: None = Depends(require_local_request),
        admin_service: AdminService = Depends(service),
    ) -> dict[str, object]:
        return admin_service.list_plugins()

    @app.put("/admin/api/plugins/{plugin_id}")
    async def admin_update_plugin(
        plugin_id: str,
        payload: FeatureToggleRequest,
        _: None = Depends(require_local_request),
        admin_service: AdminService = Depends(service),
    ) -> dict[str, object]:
        try:
            return admin_service.set_plugin_enabled(plugin_id, payload.enabled)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/admin/api/group-control")
    async def admin_group_control(
        _: None = Depends(require_local_request),
        admin_service: AdminService = Depends(service),
    ) -> dict[str, object]:
        return admin_service.get_group_control_config()

    @app.get("/admin/api/shapez-file-cleanup/preview")
    async def admin_shapez_file_cleanup_preview(
        _: None = Depends(require_local_request),
    ) -> dict[str, object]:
        bots = nonebot.get_bots()
        if not bots:
            raise HTTPException(status_code=503, detail="No connected OneBot bot.")
        bot = next(iter(bots.values()))
        service = ShapezGroupFileCleanupService(
            store=ShapezGroupFileCleanupStore(settings.data_root / "data" / "shapez_file_cleanup_state.json"),
            timezone_name=settings.timezone,
        )
        current = datetime.now(service.zone)
        snapshot = await service.fetch_snapshot(bot)
        violations = service.find_violations(snapshot, now=current)
        violating_files = tuple(file_info for files in violations.values() for file_info in files)
        root_upload_times = tuple(file_info.uploaded_at for file_info in snapshot.root_files if file_info.uploaded_at > 0)
        cutoff = int((current - timedelta(days=service.old_file_grace_days)).timestamp())
        return {
            "group_id": int(SHAPEZ_GROUP_ID),
            "preview_only": True,
            "root_file_count": len(snapshot.root_files),
            "folder_count": len(snapshot.folders),
            "inner_file_count": len(snapshot.inner_files),
            "root_old_file_count": sum(1 for file_info in snapshot.root_files if 0 < file_info.uploaded_at <= cutoff),
            "root_new_file_count": sum(1 for file_info in snapshot.root_files if file_info.uploaded_at > cutoff),
            "root_upload_time_min": min(root_upload_times, default=0),
            "root_upload_time_max": max(root_upload_times, default=0),
            "violating_user_count": len(violations),
            "violating_file_count": len(violating_files),
            "violating_total_size": sum(file_info.size for file_info in violating_files),
            "users": [
                {
                    "user_id": user_id,
                    "file_count": len(files),
                    "total_size": sum(file_info.size for file_info in files),
                    "files": [_preview_group_file(file_info) for file_info in sorted(files, key=lambda item: (-item.size, item.name))],
                }
                for user_id, files in sorted(violations.items(), key=lambda item: (-sum(file_info.size for file_info in item[1]), item[0]))
            ],
        }

    @app.post("/admin/api/shapez-file-cleanup/unmute")
    async def admin_shapez_file_cleanup_unmute(
        payload: ShapezFileCleanupUnmuteRequest,
        _: None = Depends(require_local_request),
    ) -> dict[str, object]:
        bots = nonebot.get_bots()
        if not bots:
            raise HTTPException(status_code=503, detail="No connected OneBot bot.")
        bot = next(iter(bots.values()))
        await bot.call_api(
            "set_group_ban",
            group_id=int(SHAPEZ_GROUP_ID),
            user_id=int(payload.user_id),
            duration=0,
        )
        return {"ok": True, "group_id": int(SHAPEZ_GROUP_ID), "user_id": int(payload.user_id), "duration": 0}

    @app.get("/admin/api/kun/users")
    async def admin_kun_users(
        _: None = Depends(require_local_request),
        admin_service: AdminService = Depends(service),
    ) -> dict[str, object]:
        return admin_service.list_kun_users()

    @app.get("/admin/api/kun/users/{qq}")
    async def admin_kun_user(
        qq: int,
        _: None = Depends(require_local_request),
        admin_service: AdminService = Depends(service),
    ) -> dict[str, object]:
        try:
            return admin_service.get_kun_user(qq)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.put("/admin/api/kun/users/{qq}")
    async def admin_update_kun_user(
        qq: int,
        payload: KunUserUpdateRequest,
        _: None = Depends(require_local_request),
        admin_service: AdminService = Depends(service),
    ) -> dict[str, object]:
        try:
            return admin_service.update_kun_user(qq, payload.updates)
        except ValueError as exc:
            detail = str(exc)
            status_code = 404 if "not found" in detail else 400
            raise HTTPException(status_code=status_code, detail=detail) from exc

    @app.get("/admin/api/ai")
    async def admin_ai(
        _: None = Depends(require_local_request),
        admin_service: AdminService = Depends(service),
    ) -> dict[str, object]:
        return admin_service.list_ai()

    @app.put("/admin/api/ai/provider")
    async def admin_update_ai_provider(
        payload: AiProviderUpdateRequest,
        _: None = Depends(require_local_request),
        admin_service: AdminService = Depends(service),
    ) -> dict[str, object]:
        try:
            return admin_service.set_ai_provider(payload.profile)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.put("/admin/api/ai/profile-priority")
    async def admin_update_ai_profile_priority(
        payload: AiProfilePriorityUpdateRequest,
        _: None = Depends(require_local_request),
        admin_service: AdminService = Depends(service),
    ) -> dict[str, object]:
        try:
            return admin_service.set_ai_profile_priority(payload.profiles)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/admin/api/ai/diagnostics")
    async def admin_ai_diagnostics(
        _: None = Depends(require_local_request),
        admin_service: AdminService = Depends(service),
    ) -> dict[str, object]:
        return admin_service.list_ai_diagnostics()

    @app.post("/admin/api/artifacts/publish-local")
    async def admin_publish_local_artifacts(
        payload: LocalArtifactPublishRequest,
        _: None = Depends(require_local_request),
    ) -> dict[str, object]:
        if not payload.files:
            raise HTTPException(status_code=400, detail="No artifact files to publish.")
        _validate_publish_timestamp(payload.timestamp)
        _validate_publish_metadata(payload)

        bots = nonebot.get_bots()
        if not bots:
            raise HTTPException(status_code=503, detail="No connected OneBot bot.")

        repo_path = _infer_publish_repo_path(payload.files)
        _validate_publish_git_context(payload, repo_path)

        files = [
            _build_local_artifact_publish_file(file_payload, repo_path)
            for file_payload in payload.files
        ]
        context = LocalArtifactPublishContext(
            project_id=payload.project_id,
            branch=payload.branch.strip(),
            commit_hash=payload.commit_hash.strip(),
            commit_subject=payload.commit_subject.strip(),
            commit_detail=payload.commit_detail.strip(),
        )
        bot = next(iter(bots.values()))
        try:
            result = await publish_local_artifacts(bot, files, context)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "ok": True,
            "uploaded": result.uploaded,
            "deleted": result.deleted,
            "skipped": result.skipped,
        }

    @app.get("/admin/api/author")
    async def admin_author(
        _: None = Depends(require_local_request),
        admin_service: AdminService = Depends(service),
    ) -> dict[str, object]:
        return admin_service.get_author()

    @app.get("/admin/api/logs")
    async def admin_list_logs(
        _: None = Depends(require_local_request),
        admin_service: AdminService = Depends(service),
    ) -> list[dict[str, object]]:
        return admin_service.list_startup_logs()

    @app.get("/admin/api/logs/{run_id}/{file_name}")
    async def admin_read_log(
        run_id: str,
        file_name: str,
        _: None = Depends(require_local_request),
        admin_service: AdminService = Depends(service),
    ) -> dict[str, object]:
        try:
            return admin_service.read_startup_log(run_id, file_name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


def build_admin_html(settings: RuntimeSettings) -> str:
    title = "QQBot Admin"
    admin_url = f"http://{settings.host}:{settings.port}/admin"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
      background: #f6f7f9;
      color: #1f2937;
    }}
    body {{ margin: 0; min-height: 100vh; }}
    header {{
      background: #1e293b;
      color: #f8fafc;
      padding: 14px 22px;
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: center;
    }}
    h1 {{ margin: 0; font-size: 22px; }}
    h2 {{ margin: 0 0 14px; font-size: 18px; }}
    h3 {{ margin: 0 0 10px; font-size: 15px; }}
    .admin-shell {{
      min-height: calc(100vh - 58px);
      display: grid;
      grid-template-columns: 220px minmax(0, 1fr);
    }}
    .sidebar {{
      background: #e8edf3;
      border-right: 1px solid #cbd5e1;
      padding: 16px 12px;
    }}
    .tab-button {{
      width: 100%;
      min-height: 42px;
      margin-bottom: 8px;
      text-align: left;
      border-color: transparent;
      background: transparent;
      color: #334155;
      font-weight: 600;
    }}
    .tab-button.active {{
      background: #ffffff;
      border-color: #cbd5e1;
      color: #0f172a;
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
    }}
    .content {{ min-width: 0; padding: 22px; }}
    .tab-panel {{ display: none; max-width: 1180px; }}
    .tab-panel.active {{ display: block; }}
    .panel-block {{
      background: #ffffff;
      border: 1px solid #d9dee7;
      border-radius: 8px;
      margin-bottom: 18px;
      padding: 18px;
    }}
    button, select, input {{
      font: inherit;
      min-height: 36px;
      border: 1px solid #c7ced8;
      border-radius: 6px;
      background: #ffffff;
      color: #111827;
      padding: 6px 10px;
    }}
    button {{ cursor: pointer; }}
    button.enabled {{ background: #0f766e; border-color: #0f766e; color: #ffffff; }}
    button.disabled {{ background: #f3f4f6; }}
    button.danger {{ background: #b91c1c; border-color: #991b1b; color: #ffffff; }}
    button:disabled {{ cursor: not-allowed; opacity: 0.62; }}
    .row {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; }}
    .muted {{ color: #64748b; }}
    .control-panel {{ display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }}
    .status {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; }}
    .status div {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px; }}
    .form-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 10px; margin-top: 12px; }}
    .field {{ display: flex; flex-direction: column; gap: 5px; }}
    .field label {{ color: #475569; font-size: 13px; }}
    .binding-list {{ display: grid; gap: 10px; margin-top: 12px; }}
    .binding-row {{
      display: grid;
      grid-template-columns: minmax(180px, 1fr) minmax(180px, 260px) auto;
      gap: 10px;
      align-items: center;
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 10px;
    }}
    .binding-row select {{ width: 100%; }}
    .binding-title {{ font-weight: 700; }}
    .binding-meta {{ color: #64748b; font-size: 12px; margin-top: 4px; }}
    .diagnostic-list {{ display: grid; gap: 10px; margin-top: 12px; }}
    .diagnostic-row {{
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 10px;
    }}
    .diagnostic-title {{ font-weight: 700; }}
    .diagnostic-meta {{ color: #64748b; font-size: 12px; margin-top: 5px; line-height: 1.5; }}
    .message-groups {{ display: grid; gap: 14px; margin-top: 12px; }}
    .message-group {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px; }}
    .message-list {{ display: flex; flex-direction: column; gap: 8px; margin-top: 10px; max-height: 360px; overflow: auto; }}
    .message-row {{ display: flex; }}
    .message-row.incoming {{ justify-content: flex-start; }}
    .message-row.bot {{ justify-content: flex-end; }}
    .message-bubble {{
      max-width: min(70%, 720px);
      border: 1px solid #d7dde6;
      border-radius: 8px;
      padding: 8px 10px;
      background: #ffffff;
      box-shadow: 0 1px 1px rgba(15, 23, 42, 0.04);
    }}
    .message-row.bot .message-bubble {{ background: #ecfdf5; border-color: #a7f3d0; }}
    .message-meta {{ color: #64748b; font-size: 12px; margin-bottom: 4px; }}
    .message-text {{ white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.45; }}
    pre {{ white-space: pre-wrap; background: #111827; color: #e5e7eb; padding: 12px; border-radius: 6px; max-height: 420px; overflow: auto; }}
    ul {{ padding-left: 18px; }}
    @media (max-width: 760px) {{
      header {{ align-items: flex-start; flex-direction: column; }}
      .admin-shell {{ grid-template-columns: 1fr; }}
      .sidebar {{ display: flex; gap: 8px; overflow-x: auto; border-right: 0; border-bottom: 1px solid #cbd5e1; }}
      .tab-button {{ width: auto; min-width: 112px; margin-bottom: 0; text-align: center; }}
      .content {{ padding: 16px; }}
      .binding-row {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{escape(title)}</h1>
    <div>{escape(admin_url)}</div>
  </header>
  <div id="adminShell" class="admin-shell">
    <nav class="sidebar" aria-label="管理模块">
      <button class="tab-button active" data-tab="realtimePanel" onclick="showTab('realtimePanel')">实时信息</button>
      <button class="tab-button" data-tab="groupControlPanel" onclick="showTab('groupControlPanel')">群管管理</button>
      <button class="tab-button" data-tab="kunPanel" onclick="showTab('kunPanel')">养鲲管理</button>
      <button class="tab-button" data-tab="memoryPanel" onclick="showTab('memoryPanel')">长期记忆</button>
      <button class="tab-button" data-tab="systemPanel" onclick="showTab('systemPanel')">系统设置</button>
    </nav>
    <main class="content">
      <section id="realtimePanel" class="tab-panel active">
        <div class="panel-block">
          <h2>实时信息</h2>
          <div id="status" class="status"></div>
        </div>
        <div class="panel-block">
          <h3>群消息</h3>
          <div class="row">
            <select id="messageGroupSelect" onchange="renderGroupMessages()"></select>
            <button onclick="loadGroupMessages()">刷新</button>
            <span id="groupMessageStatus" class="muted"></span>
          </div>
          <div id="groupMessages" class="message-groups"></div>
        </div>
        <div class="panel-block">
          <h3>运行日志</h3>
          <div class="row">
            <select id="logRunSelect"></select>
            <select id="logFileSelect"></select>
            <button onclick="loadLogContent()">查看</button>
          </div>
          <pre id="logContent">请选择日志。</pre>
        </div>
      </section>
      <section id="groupControlPanel" class="tab-panel">
        <div class="panel-block">
          <h2>群管助手</h2>
          <h3>群文件清理</h3>
          <div class="row">
            <button onclick="loadGroupControlConfig()">读取</button>
            <span id="groupControlStatus" class="muted"></span>
          </div>
          <div class="status">
            <div>
              <strong>外层旧群文件</strong>
              <p id="groupFileCleanupText" class="muted">待读取。</p>
            </div>
          </div>
        </div>
      </section>
      <section id="kunPanel" class="tab-panel">
        <div class="panel-block">
          <h2>养鲲管理</h2>
          <h3>养鲲数据</h3>
          <div class="row">
            <label for="kunUserSelect">用户选择</label>
            <select id="kunUserSelect"></select>
            <button onclick="loadKunUserFromSelect()">选择</button>
            <input id="kunQqInput" inputmode="numeric" placeholder="QQ 号">
            <button onclick="loadKunUser()">查询</button>
            <button onclick="saveKunUser()">保存</button>
            <span id="kunStatus" class="muted"></span>
          </div>
          <div id="kunReadonly" class="status"></div>
          <div id="kunFields" class="form-grid"></div>
        </div>
      </section>
      <section id="memoryPanel" class="tab-panel">
        <div class="panel-block">
          <h2>长期记忆</h2>
          <h3>记忆检索调试</h3>
          <div class="form-grid">
            <div class="field"><label for="memoryGroupInput">群号</label><input id="memoryGroupInput" inputmode="numeric" placeholder="群号"></div>
            <div class="field"><label for="memoryQueryInput">问题</label><input id="memoryQueryInput" placeholder="输入要调试的问题"></div>
            <div class="field"><label for="memoryLimitInput">数量</label><input id="memoryLimitInput" type="number" min="1" max="20" step="1" value="6"></div>
          </div>
          <div class="row">
            <button onclick="debugMemorySearch()">检索调试</button>
            <button onclick="rebuildMemoryFacts()">重建事实</button>
            <button onclick="scanDomainKnowledge()">扫描知识候选</button>
            <button onclick="loadPendingAiTasks()">查看待处理 AI 任务</button>
            <span id="memoryStatus" class="muted"></span>
          </div>
          <pre id="memoryDebugOutput">请输入群号和问题。</pre>
        </div>
        <div class="panel-block">
          <h3>可信事实管理</h3>
          <div class="form-grid">
            <div class="field"><label for="memoryFactSubject">主体</label><input id="memoryFactSubject"></div>
            <div class="field"><label for="memoryFactPredicate">关系</label><input id="memoryFactPredicate"></div>
            <div class="field"><label for="memoryFactObject">内容</label><input id="memoryFactObject"></div>
            <div class="field"><label for="memoryFactConfidence">置信度</label><input id="memoryFactConfidence" type="number" min="0" max="1" step="0.05" value="1"></div>
            <div class="field"><label for="memoryFactSourceType">来源类型</label><select id="memoryFactSourceType"><option value="system">system</option><option value="admin">admin</option></select></div>
            <div class="field"><label for="memoryFactTrustLevel">信任层级</label><select id="memoryFactTrustLevel"><option value="system">system</option><option value="admin">admin</option></select></div>
          </div>
          <div class="row">
            <button onclick="upsertMemoryFact()">保存可信事实</button>
            <input id="memoryFactIdInput" inputmode="numeric" placeholder="事实 ID">
            <select id="memoryFactStatusInput"><option value="disabled">disabled</option><option value="active">active</option><option value="superseded">superseded</option></select>
            <button onclick="updateMemoryFactStatus()">更新状态</button>
          </div>
        </div>
      </section>
      <section id="systemPanel" class="tab-panel">
        <div class="panel-block">
          <h2>系统设置</h2>
          <h3>运行控制</h3>
          <div class="control-panel">
            <button id="restartButton" class="danger" onclick="restartBot()">重启 Bot</button>
            <span id="restartStatus" class="muted">重启会断开几秒钟，NapCat 会自动重连。</span>
          </div>
        </div>
        <div class="panel-block">
          <h3>全局插件</h3>
          <div id="pluginGrid" class="grid"></div>
        </div>
        <div class="panel-block">
          <h3>AI 模型</h3>
          <div class="row">
            <select id="aiProviderSelect"></select>
            <span id="aiProviderStatus" class="muted"></span>
          </div>
          <div id="aiProfilePriorityList" class="binding-list"></div>
        </div>
        <div class="panel-block">
          <h3>AI 诊断</h3>
          <div class="row">
            <button onclick="loadAiDiagnostics()">刷新</button>
            <span id="aiDiagnosticsStatus" class="muted"></span>
          </div>
          <div id="aiDiagnosticsSummary" class="status"></div>
          <div id="aiDiagnosticsList" class="diagnostic-list"></div>
        </div>
        <div class="panel-block">
          <h3>作者权限</h3>
          <ul id="adminList"></ul>
        </div>
      </section>
    </main>
  </div>
  <script>
    const api = (path, options = {{}}) => fetch(path, {{
      headers: {{ "Content-Type": "application/json" }},
      ...options,
    }}).then(async response => {{
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    }});

    function showTab(tabId) {{
      document.querySelectorAll(".tab-panel").forEach(panel => {{
        panel.classList.toggle("active", panel.id === tabId);
      }});
      document.querySelectorAll(".tab-button").forEach(button => {{
        button.classList.toggle("active", button.dataset.tab === tabId);
      }});
    }}

    async function loadStatus() {{
      const status = await api("/admin/api/status");
      document.getElementById("status").innerHTML = [
        ["OneBot", status.onebot_connected ? "已连接" : "未连接"],
        ["连接数", String(status.connected_bot_count)],
        ["WebSocket", status.onebot_ws_url],
        ["数据目录", status.data_root],
      ].map(([label, value]) => `<div><strong>${{label}}</strong><br><span>${{value}}</span></div>`).join("");
    }}

    async function restartBot() {{
      if (!confirm("确认重启 Bot？当前连接会短暂断开。")) return;
      const button = document.getElementById("restartButton");
      const status = document.getElementById("restartStatus");
      button.disabled = true;
      status.textContent = "正在安排重启...";
      try {{
        await api("/admin/api/restart", {{ method: "POST" }});
        status.textContent = "重启已安排，页面会在 8 秒后刷新。";
        setTimeout(() => window.location.reload(), 8000);
      }} catch (error) {{
        button.disabled = false;
        status.textContent = `重启失败：${{error.message}}`;
      }}
    }}

    async function loadGroups() {{
      const groups = await api("/admin/api/groups");
      document.getElementById("status").insertAdjacentHTML(
        "beforeend",
        `<div><strong>已知群</strong><br><span>${{groups.length}}</span></div>`
      );
      await loadGroupControlConfig();
    }}

    let groupMessagePayload = {{ groups: [] }};

    async function loadGroupMessages() {{
      const status = document.getElementById("groupMessageStatus");
      status.textContent = "正在刷新...";
      const scrollState = captureSelectedMessageScroll();
      groupMessagePayload = await api("/admin/api/group-messages");
      const select = document.getElementById("messageGroupSelect");
      const currentValue = select.value;
      select.innerHTML = groupMessagePayload.groups.map(group => (
        `<option value="${{group.group_id}}">${{escapeHtml(group.display_name)}}（${{group.messages.length}}）</option>`
      )).join("");
      select.value = [...select.options].some(option => option.value === currentValue)
        ? currentValue
        : selectLatestMessageGroup();
      renderGroupMessages();
      restoreSelectedMessageScroll(scrollState);
      status.textContent = `已刷新：${{formatTime(Date.now() / 1000)}}`;
    }}

    function renderGroupMessages() {{
      const selected = document.getElementById("messageGroupSelect").value;
      const groups = groupMessagePayload.groups.filter(group => String(group.group_id) === selected);
      document.getElementById("groupMessages").innerHTML = groups.map(renderMessageGroup).join("")
        || `<div class="muted">暂无群消息。</div>`;
    }}

    function selectLatestMessageGroup() {{
      const latestGroup = groupMessagePayload.groups.reduce((latest, group) => {{
        const latestMessage = group.messages[group.messages.length - 1];
        const latestTimestamp = latest.message ? Number(latest.message.timestamp) : -1;
        const groupTimestamp = latestMessage ? Number(latestMessage.timestamp) : -1;
        return groupTimestamp > latestTimestamp
          ? {{ group, message: latestMessage }}
          : latest;
      }}, {{ group: groupMessagePayload.groups[0], message: null }});
      return latestGroup.group ? String(latestGroup.group.group_id) : "";
    }}

    function getSelectedMessageList() {{
      return document.querySelector("#groupMessages .message-list");
    }}

    function isMessageListAtBottom() {{
      const list = getSelectedMessageList();
      if (!list) return true;
      return list.scrollHeight - list.scrollTop - list.clientHeight <= 8;
    }}

    function captureSelectedMessageScroll() {{
      const select = document.getElementById("messageGroupSelect");
      const list = getSelectedMessageList();
      if (!list) {{
        return {{ groupId: select.value, atBottom: true, scrollTop: 0 }};
      }}
      return {{
        groupId: select.value,
        atBottom: isMessageListAtBottom(),
        scrollTop: list.scrollTop,
      }};
    }}

    function restoreSelectedMessageScroll(scrollState) {{
      const select = document.getElementById("messageGroupSelect");
      const list = getSelectedMessageList();
      if (!list) return;
      if (scrollState.atBottom || scrollState.groupId !== select.value) {{
        scrollSelectedMessageListToBottom();
        return;
      }}
      list.scrollTop = scrollState.scrollTop;
    }}

    function scrollSelectedMessageListToBottom() {{
      const list = getSelectedMessageList();
      if (list) list.scrollTop = list.scrollHeight;
    }}

    function readMemoryGroupId() {{
      const value = Number(document.getElementById("memoryGroupInput").value);
      if (!Number.isInteger(value) || value <= 0) throw new Error("请输入有效群号。");
      return value;
    }}

    async function debugMemorySearch() {{
      const status = document.getElementById("memoryStatus");
      status.textContent = "正在检索...";
      try {{
        const payload = await api("/admin/api/memory/debug", {{
          method: "POST",
          body: JSON.stringify({{
            group_id: readMemoryGroupId(),
            query: document.getElementById("memoryQueryInput").value,
            limit: Number(document.getElementById("memoryLimitInput").value || 6),
          }}),
        }});
        document.getElementById("memoryDebugOutput").textContent = JSON.stringify(payload, null, 2);
        status.textContent = "检索完成。";
      }} catch (error) {{
        status.textContent = `检索失败：${{error.message}}`;
      }}
    }}

    async function rebuildMemoryFacts() {{
      const status = document.getElementById("memoryStatus");
      status.textContent = "正在重建事实...";
      try {{
        const payload = await api("/admin/api/memory/facts/rebuild", {{
          method: "POST",
          body: JSON.stringify({{ group_id: readMemoryGroupId() }}),
        }});
        document.getElementById("memoryDebugOutput").textContent = JSON.stringify(payload, null, 2);
        status.textContent = "重建完成。";
      }} catch (error) {{
        status.textContent = `重建失败：${{error.message}}`;
      }}
    }}

    async function scanDomainKnowledge() {{
      const status = document.getElementById("memoryStatus");
      status.textContent = "正在扫描知识候选...";
      try {{
        const payload = await api("/admin/api/knowledge/scan", {{ method: "POST" }});
        document.getElementById("memoryDebugOutput").textContent = JSON.stringify(payload, null, 2);
        status.textContent = "知识候选扫描完成。";
      }} catch (error) {{
        status.textContent = `扫描失败：${{error.message}}`;
      }}
    }}

    async function loadPendingAiTasks() {{
      const status = document.getElementById("memoryStatus");
      status.textContent = "正在读取待处理任务...";
      try {{
        const payload = await api("/admin/api/ai/pending-tasks");
        document.getElementById("memoryDebugOutput").textContent = JSON.stringify(payload, null, 2);
        status.textContent = "待处理任务读取完成。";
      }} catch (error) {{
        status.textContent = `读取失败：${{error.message}}`;
      }}
    }}

    async function upsertMemoryFact() {{
      const status = document.getElementById("memoryStatus");
      status.textContent = "正在保存可信事实...";
      try {{
        const payload = await api("/admin/api/memory/facts", {{
          method: "POST",
          body: JSON.stringify({{
            group_id: readMemoryGroupId(),
            subject: document.getElementById("memoryFactSubject").value,
            predicate: document.getElementById("memoryFactPredicate").value,
            object: document.getElementById("memoryFactObject").value,
            confidence: Number(document.getElementById("memoryFactConfidence").value || 1),
            source_type: document.getElementById("memoryFactSourceType").value,
            trust_level: document.getElementById("memoryFactTrustLevel").value,
            topics: [],
            entities: [],
          }}),
        }});
        document.getElementById("memoryDebugOutput").textContent = JSON.stringify(payload, null, 2);
        status.textContent = "可信事实已保存。";
      }} catch (error) {{
        status.textContent = `保存失败：${{error.message}}`;
      }}
    }}

    async function updateMemoryFactStatus() {{
      const status = document.getElementById("memoryStatus");
      const factId = Number(document.getElementById("memoryFactIdInput").value);
      if (!Number.isInteger(factId) || factId <= 0) {{
        status.textContent = "请输入有效事实 ID。";
        return;
      }}
      try {{
        const payload = await api(`/admin/api/memory/facts/${{factId}}`, {{
          method: "PUT",
          body: JSON.stringify({{ status: document.getElementById("memoryFactStatusInput").value }}),
        }});
        document.getElementById("memoryDebugOutput").textContent = JSON.stringify(payload, null, 2);
        status.textContent = "事实状态已更新。";
      }} catch (error) {{
        status.textContent = `更新失败：${{error.message}}`;
      }}
    }}

    function renderMessageGroup(group) {{
      const messages = group.messages.map(renderMessageRow).join("")
        || `<div class="muted">这个群暂时没有消息。</div>`;
      return `
        <div class="message-group">
          <strong>${{escapeHtml(group.display_name)}}</strong>
          <div class="message-list">${{messages}}</div>
        </div>
      `;
    }}

    function renderMessageRow(message) {{
      const direction = message.direction === "bot" ? "bot" : "incoming";
      const sender = direction === "bot" ? "Bot" : message.sender_name;
      return `
        <div class="message-row ${{direction}}">
          <div class="message-bubble">
            <div class="message-meta">${{escapeHtml(sender)}} · ${{formatTime(message.timestamp)}}</div>
            <div class="message-text">${{escapeHtml(message.text)}}</div>
          </div>
        </div>
      `;
    }}

    function formatTime(timestamp) {{
      if (!timestamp) return "";
      const date = new Date(Number(timestamp) * 1000);
      return date.toLocaleTimeString("zh-CN", {{ hour12: false }});
    }}

    async function loadPlugins() {{
      const payload = await api("/admin/api/plugins");
      document.getElementById("pluginGrid").innerHTML = payload.plugins.map(plugin => {{
        const cls = plugin.global_enabled ? "enabled" : "disabled";
        const text = plugin.global_enabled ? "全局开启" : "全局关闭";
        const ai = plugin.ai_capabilities.length ? ` / AI: ${{plugin.ai_capabilities.join(", ")}}` : "";
        return `<button class="${{cls}}" onclick="togglePlugin('${{plugin.id}}', ${{!plugin.global_enabled}})">${{plugin.name}}：${{text}}${{ai}}</button>`;
      }}).join("");
    }}

    async function loadAiProvider() {{
      const payload = await api("/admin/api/ai");
      const select = document.getElementById("aiProviderSelect");
      select.innerHTML = payload.profiles.map(profile => {{
        const label = `${{profile.name}} / ${{profile.model}}`;
        return `<option value="${{escapeHtml(profile.name)}}">${{escapeHtml(label)}}</option>`;
      }}).join("");
      select.value = payload.current_profile;
      select.disabled = Boolean(payload.config_locked);
      document.getElementById("aiProviderStatus").textContent =
        `当前：${{payload.current_profile}}，默认：${{payload.default_profile}}，调用顺序：${{(payload.fallback_order || []).join(" → ")}}。${{payload.message || "配置来源：qqbot.toml，修改后重启 bot1。"}}`;
      renderAiProfilePriority(payload);
    }}

    async function saveAiProvider() {{
      const status = document.getElementById("aiProviderStatus");
      status.textContent = "AI 模型由 qqbot.toml 控制，修改配置后重启 bot1。";
    }}

    function renderAiProfilePriority(payload) {{
      const list = document.getElementById("aiProfilePriorityList");
      const profiles = payload.profiles || [];
      const byName = new Map(profiles.map(profile => [profile.name, profile]));
      const orderedNames = [...(payload.fallback_order || []), ...profiles.map(profile => profile.name)]
        .filter((name, index, names) => name && names.indexOf(name) === index && byName.has(name));
      if (!orderedNames.length) {{
        list.innerHTML = `<div class="muted">暂无可用 AI profile。</div>`;
        return;
      }}
      list.innerHTML = orderedNames.map((name, index) => {{
        const profile = byName.get(name) || {{}};
        return `
          <div class="binding-row" data-ai-profile="${{escapeHtml(name)}}">
            <div>
              <div class="binding-title">${{index + 1}}. ${{escapeHtml(name)}} / ${{escapeHtml(profile.model || "")}}</div>
              <div class="binding-meta">${{escapeHtml(profile.provider || "")}}${{profile.note ? ` / ${{escapeHtml(profile.note)}}` : ""}}</div>
            </div>
          </div>
        `;
      }}).join("");
    }}

    async function moveAiProfile(index, delta) {{
      const status = document.getElementById("aiProviderStatus");
      status.textContent = "AI 调用顺序由 qqbot.toml 控制，修改配置后重启 bot1。";
    }}

    async function loadAiDiagnostics() {{
      const status = document.getElementById("aiDiagnosticsStatus");
      status.textContent = "正在刷新...";
      try {{
        const payload = await api("/admin/api/ai/diagnostics");
        renderAiDiagnostics(payload);
        status.textContent = `已刷新：${{formatTime(Date.now() / 1000)}}`;
      }} catch (error) {{
        status.textContent = `刷新失败：${{error.message}}`;
      }}
    }}

    function renderAiDiagnostics(payload) {{
      const summary = [
        ["样本数", payload.count],
        ["成功 / 兜底", `${{payload.success_count}} / ${{payload.fallback_count}}`],
        ["重试后成功", payload.retry_success_count],
        ["排队等待均值", formatDuration(payload.avg_queue_wait_seconds)],
        ["本地准备均值", formatDuration(payload.avg_local_prepare_seconds)],
        ["准备阶段均值", formatPrepareStages(payload.avg_prepare_stages)],
        ["首字均值", formatDuration(payload.avg_first_token_seconds)],
        ["首字 P95", formatDuration(payload.p95_first_token_seconds)],
        ["TPS 均值", formatRate(payload.avg_tokens_per_second)],
        ["端到端均值", formatDuration(payload.avg_total_seconds)],
        ["空回复 / 超时", `${{payload.empty_count}} / ${{payload.timeout_count}}`],
      ];
      document.getElementById("aiDiagnosticsSummary").innerHTML = summary
        .map(([label, value]) => `<div><strong>${{label}}</strong><br><span>${{escapeHtml(value ?? "-")}}</span></div>`)
        .join("");
      const records = payload.records || [];
      document.getElementById("aiDiagnosticsList").innerHTML = records
        .slice(0, 20)
        .map(renderAiDiagnosticsRecord)
        .join("") || `<div class="muted">暂无 AI 回复诊断记录。</div>`;
    }}

    function renderAiDiagnosticsRecord(record) {{
      const scope = record.scope === "group" ? `群 ${{record.group_id}}` : "私聊";
      const result = record.fallback
        ? `兜底${{record.fallback_reason ? ` / ${{record.fallback_reason}}` : ""}}`
        : "成功";
      const attempts = (record.attempts || []).map(attempt => {{
        const ttft = attempt.first_token_seconds == null ? "-" : formatDuration(attempt.first_token_seconds);
        const tps = attempt.tokens_per_second == null ? "-" : formatRate(attempt.tokens_per_second);
        return `#${{attempt.attempt}} ${{attempt.result}}，首字 ${{ttft}}，总 ${{formatDuration(attempt.total_seconds)}}，TPS ${{tps}}`;
      }}).join("；");
      const prepareStages = formatPrepareStages(record.prepare_stages);
      return `
        <div class="diagnostic-row">
          <div class="diagnostic-title">${{escapeHtml(formatTime(record.timestamp))}} · ${{escapeHtml(record.profile)}} / ${{escapeHtml(record.model)}} · ${{escapeHtml(result)}}</div>
          <div class="diagnostic-meta">
            ${{escapeHtml(scope)}} · 排队 ${{escapeHtml(formatDuration(record.queue_wait_seconds))}} · 本地准备 ${{escapeHtml(formatDuration(record.local_prepare_seconds))}} · 端到端 ${{escapeHtml(formatDuration(record.total_seconds))}} · prompt ${{record.prompt_chars}} 字 · context ${{record.context_chars}} 字 · history ${{record.history_messages}} · image ${{record.image_count}}<br>
            准备阶段：${{escapeHtml(prepareStages)}}<br>
            ${{escapeHtml(attempts || "无 provider attempt 记录")}}
          </div>
        </div>
      `;
    }}

    function formatDuration(value) {{
      if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
      return `${{Number(value).toFixed(2)}}s`;
    }}

    function formatRate(value) {{
      if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
      return `${{Number(value).toFixed(2)}}/s`;
    }}

    function formatPrepareStages(stages) {{
      if (!stages || typeof stages !== "object") return "-";
      const entries = Object.entries(stages)
        .filter(([, value]) => value !== null && value !== undefined)
        .sort((left, right) => Number(right[1]) - Number(left[1]))
        .slice(0, 6);
      if (!entries.length) return "-";
      return entries.map(([name, value]) => `${{name}} ${{formatDuration(value)}}`).join("；");
    }}

    async function togglePlugin(pluginId, enabled) {{
      await api(`/admin/api/plugins/${{pluginId}}`, {{
        method: "PUT",
        body: JSON.stringify({{ enabled }}),
      }});
      await loadPlugins();
    }}

    async function loadGroupControlConfig() {{
      const status = document.getElementById("groupControlStatus");
      const payload = await api("/admin/api/group-control");
      document.getElementById("groupFileCleanupText").textContent = payload.file_cleanup_description || "未配置。";
      status.textContent = "已读取。";
    }}

    const kunEditableLabels = {{
      name: "名称",
      level: "等级",
      atk: "攻击",
      defense: "防御",
      hp: "血量",
      money: "萌泪币",
      rename_card: "改名卡",
      wash_card: "洗练卡",
      check_card: "查看卡",
      challenge_ticket: "挑战券",
    }};

    function renderKunUser(payload) {{
      const user = payload.user;
      document.getElementById("kunQqInput").value = user.qq;
      document.getElementById("kunUserSelect").value = user.qq;
      document.getElementById("kunReadonly").innerHTML = [
        ["QQ", user.qq],
        ["赛季", user.season],
        ["赛季提示", user.open_new_season_tip ? "开启" : "关闭"],
        ["摸鲲次数", user.mk_times],
        ["进击次数", user.jj_times],
        ["挑战次数", user.tz_times],
      ].map(([label, value]) => `<div><strong>${{label}}</strong><br><span>${{escapeHtml(value)}}</span></div>`).join("");
      document.getElementById("kunFields").innerHTML = payload.editable_fields.map(field => {{
        const label = kunEditableLabels[field] || field;
        const value = user[field] ?? "";
        const type = field === "name" ? "text" : "number";
        const attrs = field === "name" ? 'maxlength="8"' : 'min="0" step="1"';
        return `<div class="field"><label for="kun_${{field}}">${{escapeHtml(label)}}</label><input id="kun_${{field}}" data-kun-field="${{field}}" type="${{type}}" ${{attrs}} value="${{escapeHtml(value)}}"></div>`;
      }}).join("");
    }}

    async function loadKunUsers(autoLoadFirst = false) {{
      const payload = await api("/admin/api/kun/users");
      const select = document.getElementById("kunUserSelect");
      const currentQq = document.getElementById("kunQqInput").value;
      select.innerHTML = payload.users.map(user => {{
        const label = `${{user.display_name}} / Lv.${{user.level}} / ${{user.name}}`;
        return `<option value="${{user.qq}}">${{escapeHtml(label)}}</option>`;
      }}).join("");
      if (currentQq) select.value = currentQq;
      if (autoLoadFirst && payload.users.length) {{
        document.getElementById("kunQqInput").value = payload.users[0].qq;
        await loadKunUser();
      }} else {{
        if (!payload.users.length) select.innerHTML = `<option value="">暂无养鲲用户</option>`;
      }}
    }}

    async function loadKunUserFromSelect() {{
      const qq = document.getElementById("kunUserSelect").value;
      if (!qq) return;
      document.getElementById("kunQqInput").value = qq;
      await loadKunUser();
    }}

    async function loadKunUser() {{
      const input = document.getElementById("kunQqInput");
      const qq = Number(input.value.trim());
      const status = document.getElementById("kunStatus");
      if (!qq) return;
      status.textContent = "正在读取...";
      try {{
        const payload = await api(`/admin/api/kun/users/${{qq}}`);
        renderKunUser(payload);
        status.textContent = "已读取。";
      }} catch (error) {{
        document.getElementById("kunReadonly").innerHTML = "";
        document.getElementById("kunFields").innerHTML = "";
        status.textContent = `读取失败：${{error.message}}`;
      }}
    }}

    async function saveKunUser() {{
      const qq = Number(document.getElementById("kunQqInput").value.trim());
      const status = document.getElementById("kunStatus");
      if (!qq) return;
      const updates = {{}};
      document.querySelectorAll("[data-kun-field]").forEach(input => {{
        const field = input.dataset.kunField;
        updates[field] = field === "name" ? input.value : Number(input.value);
      }});
      status.textContent = "正在保存...";
      try {{
        const payload = await api(`/admin/api/kun/users/${{qq}}`, {{
          method: "PUT",
          body: JSON.stringify({{ updates }}),
        }});
        renderKunUser(payload);
        status.textContent = "已保存。";
        await loadKunUsers(false);
      }} catch (error) {{
        status.textContent = `保存失败：${{error.message}}`;
      }}
    }}

    async function loadAdmins() {{
      const payload = await api("/admin/api/author");
      const author = payload.author || {{
        qq: payload.author_qq,
        display_name: payload.author_qq,
      }};
      document.getElementById("adminList").innerHTML =
        `<li>作者：${{escapeHtml(author.display_name || author.qq)}}（唯一管理权限）</li>`;
    }}

    async function loadLogs() {{
      const runs = await api("/admin/api/logs");
      const runSelect = document.getElementById("logRunSelect");
      runSelect.innerHTML = runs.map(run => `<option value="${{run.run_id}}" data-files="${{run.files.join(",")}}">${{run.run_id}}</option>`).join("");
      updateLogFiles();
    }}

    function updateLogFiles() {{
      const runSelect = document.getElementById("logRunSelect");
      const option = runSelect.selectedOptions[0];
      const files = option ? option.dataset.files.split(",").filter(Boolean) : [];
      document.getElementById("logFileSelect").innerHTML = files.map(file => `<option value="${{file}}">${{file}}</option>`).join("");
    }}

    async function loadLogContent() {{
      const runId = document.getElementById("logRunSelect").value;
      const file = document.getElementById("logFileSelect").value;
      if (!runId || !file) return;
      const payload = await api(`/admin/api/logs/${{runId}}/${{file}}`);
      document.getElementById("logContent").textContent = payload.content || "(空)";
    }}

    document.getElementById("logRunSelect").addEventListener("change", updateLogFiles);
    function escapeHtml(value) {{
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }}
    setInterval(loadGroupMessages, 3000);
    Promise.all([loadStatus().then(loadGroups), loadGroupMessages(), loadPlugins(), loadAiProvider(), loadAiDiagnostics(), loadAdmins(), loadLogs(), loadKunUsers(true)]).catch(error => {{
      document.body.insertAdjacentHTML("beforeend", `<pre>${{error.message}}</pre>`);
    }});
  </script>
</body>
</html>"""


def _build_local_artifact_publish_file(
    payload: LocalArtifactPublishFileRequest,
    repo_path: Path,
) -> LocalArtifactPublishFile:
    targets = tuple(group_id for group_id in payload.targets if group_id > 0)
    if not targets:
        raise HTTPException(status_code=400, detail="Artifact targets must include at least one valid group id.")
    artifact = _validate_generic_local_artifact_path(payload.path, repo_path)
    return LocalArtifactPublishFile(
        path=artifact,
        name=payload.name.strip() or artifact.name,
        targets=targets,
        sha256=payload.sha256.strip(),
        message=payload.message.strip(),
    )


def _validate_generic_local_artifact_path(raw_path: str, repo_path: Path) -> Path:
    artifact = _normalize_local_path(raw_path)
    if artifact.suffix.lower() != ".zip":
        raise HTTPException(status_code=400, detail="Only zip artifacts can be uploaded.")
    if not artifact.is_file():
        raise HTTPException(status_code=404, detail="Artifact file does not exist.")
    try:
        artifact.resolve().relative_to(repo_path.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Artifact must be inside project repository.") from exc
    return artifact


def _infer_publish_repo_path(files: list[LocalArtifactPublishFileRequest]) -> Path:
    first_path = _normalize_local_path(files[0].path)
    repo_path = _find_git_repo_root(first_path.parent)
    if repo_path is None:
        raise HTTPException(status_code=400, detail="Cannot infer project git repository from artifact path.")
    for file_payload in files:
        artifact = _normalize_local_path(file_payload.path)
        try:
            artifact.resolve().relative_to(repo_path.resolve())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="All artifacts must be inside the same project repository.") from exc
    return repo_path


def _find_git_repo_root(start: Path) -> Path | None:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _normalize_local_path(raw_path: str) -> Path:
    text = raw_path.strip()
    if len(text) >= 3 and text[1] == ":":
        return Path(text)
    if text.startswith("/mnt/") and len(text) > 6 and text[6:7] == "/":
        drive = text[5:6].upper()
        rest = text[7:].replace("/", "\\")
        return Path(f"{drive}:\\{rest}")
    return Path(text)


def _validate_publish_timestamp(timestamp: str) -> None:
    text = timestamp.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Publish timestamp is required.")
    try:
        normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
        published_at = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid publish timestamp.") from exc
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    age_seconds = abs((datetime.now(timezone.utc) - published_at.astimezone(timezone.utc)).total_seconds())
    if age_seconds > LOCAL_ARTIFACT_PUBLISH_MAX_AGE_SECONDS:
        raise HTTPException(status_code=400, detail="Publish request timestamp is stale.")


def _validate_publish_metadata(payload: LocalArtifactPublishRequest) -> None:
    if not payload.branch.strip():
        raise HTTPException(status_code=400, detail="Publish branch is required.")
    if not payload.commit_hash.strip():
        raise HTTPException(status_code=400, detail="Publish commit hash is required.")
    if not payload.commit_detail.strip() and not any(file.message.strip() for file in payload.files):
        raise HTTPException(status_code=400, detail="Publish commit detail or file message is required.")


def _validate_publish_git_context(payload: LocalArtifactPublishRequest, repo_path: Path) -> None:
    current_branch = _read_git_output(repo_path, "branch", "--show-current")
    if not current_branch:
        raise HTTPException(status_code=400, detail="Cannot read project git branch.")
    if current_branch and current_branch != payload.branch.strip():
        raise HTTPException(status_code=400, detail="Publish branch does not match project checkout.")

    current_commit = _read_git_output(repo_path, "rev-parse", "HEAD")
    if not current_commit:
        raise HTTPException(status_code=400, detail="Cannot read project git commit.")
    requested_commit = payload.commit_hash.strip().lower()
    if current_commit and not current_commit.lower().startswith(requested_commit):
        raise HTTPException(status_code=400, detail="Publish commit does not match project checkout.")


def _read_git_output(repo_path: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_path,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _preview_group_file(file_info: GroupFileInfo) -> dict[str, object]:
    return {
        "file_id": file_info.file_id,
        "file_name": file_info.name,
        "size": file_info.size,
        "upload_time": file_info.uploaded_at,
        "uploader_id": file_info.uploader_id,
    }


async def get_connected_group_names(
    timeout_seconds: float = ONEBOT_GROUP_LIST_TIMEOUT_SECONDS,
) -> dict[int, str]:
    names: dict[int, str] = {}
    try:
        bots = nonebot.get_bots().values()
    except Exception:
        return names

    for bot in bots:
        try:
            groups = await asyncio.wait_for(
                bot.call_api("get_group_list"),
                timeout=max(0.01, timeout_seconds),
            )
        except Exception:
            continue
        for group in groups:
            try:
                group_id = int(group.get("group_id"))
            except (TypeError, ValueError):
                continue
            group_name = str(group.get("group_name") or "").strip()
            if group_name:
                names[group_id] = group_name
    return names
