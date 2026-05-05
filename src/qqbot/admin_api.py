from __future__ import annotations

from collections.abc import Awaitable, Callable
from html import escape

import nonebot
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from qqbot.config import RuntimeSettings
from qqbot.services.admin_service import AdminService

LOCAL_CLIENT_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


class FeatureToggleRequest(BaseModel):
    enabled: bool


class AdminUpdateRequest(BaseModel):
    qq: int


class AiProviderUpdateRequest(BaseModel):
    profile: str


class GroupControlUpdateRequest(BaseModel):
    reread_probability_percent: float
    thunder_probability_percent: float
    min_seconds: int
    max_seconds: int


class KunUserUpdateRequest(BaseModel):
    updates: dict[str, object]


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

    @app.put("/admin/api/group-control")
    async def admin_update_group_control(
        payload: GroupControlUpdateRequest,
        _: None = Depends(require_local_request),
        admin_service: AdminService = Depends(service),
    ) -> dict[str, object]:
        return admin_service.set_group_control_config(
            payload.reread_probability_percent,
            payload.thunder_probability_percent,
            payload.min_seconds,
            payload.max_seconds,
        )

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
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/admin/api/admins")
    async def admin_list_admins(
        _: None = Depends(require_local_request),
        admin_service: AdminService = Depends(service),
    ) -> dict[str, object]:
        return admin_service.list_admins()

    @app.post("/admin/api/admins")
    async def admin_add_admin(
        payload: AdminUpdateRequest,
        _: None = Depends(require_local_request),
        admin_service: AdminService = Depends(service),
    ) -> dict[str, object]:
        return admin_service.set_admin(payload.qq, True)

    @app.delete("/admin/api/admins/{qq}")
    async def admin_remove_admin(
        qq: int,
        _: None = Depends(require_local_request),
        admin_service: AdminService = Depends(service),
    ) -> dict[str, object]:
        return admin_service.set_admin(qq, False)

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
          <h2>群管管理</h2>
          <h3>群管配置</h3>
          <div class="row">
            <button onclick="loadGroupControlConfig()">读取</button>
            <button onclick="saveGroupControlConfig()">保存</button>
            <span id="groupControlStatus" class="muted"></span>
          </div>
          <div class="form-grid">
            <div class="field">
              <label for="rereadProbabilityInput">随机复读概率（%）</label>
              <input id="rereadProbabilityInput" type="number" min="0.01" max="50" step="0.01">
            </div>
            <div class="field">
              <label for="thunderProbabilityInput">随机禁言概率（%）</label>
              <input id="thunderProbabilityInput" type="number" min="0.01" max="50" step="0.01">
            </div>
            <div class="field">
              <label for="thunderMinSecondsInput">最短禁言秒数</label>
              <input id="thunderMinSecondsInput" type="number" min="1" max="30" step="1">
            </div>
            <div class="field">
              <label for="thunderMaxSecondsInput">最长禁言秒数</label>
              <input id="thunderMaxSecondsInput" type="number" min="1" max="30" step="1">
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
            <button onclick="saveAiProvider()">保存</button>
            <span id="aiProviderStatus" class="muted"></span>
          </div>
        </div>
        <div class="panel-block">
          <h3>Bot 管理员</h3>
          <div class="row">
            <input id="adminInput" inputmode="numeric" placeholder="QQ 号">
            <button onclick="addAdmin()">添加</button>
          </div>
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
      document.getElementById("aiProviderStatus").textContent =
        `当前：${{payload.current_profile}}，默认：${{payload.default_profile}}`;
    }}

    async function saveAiProvider() {{
      const profile = document.getElementById("aiProviderSelect").value;
      const status = document.getElementById("aiProviderStatus");
      if (!profile) return;
      status.textContent = "正在保存...";
      const payload = await api("/admin/api/ai/provider", {{
        method: "PUT",
        body: JSON.stringify({{ profile }}),
      }});
      status.textContent = `当前：${{payload.current_profile}}，默认：${{payload.default_profile}}`;
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
      document.getElementById("rereadProbabilityInput").value = Number(payload.reread_probability_percent).toFixed(2);
      document.getElementById("thunderProbabilityInput").value = Number(payload.thunder_probability_percent).toFixed(2);
      document.getElementById("thunderMinSecondsInput").value = payload.thunder_min_seconds;
      document.getElementById("thunderMaxSecondsInput").value = payload.thunder_max_seconds;
      status.textContent = `当前：复读 ${{Number(payload.reread_probability_percent).toFixed(2)}}%，禁言 ${{Number(payload.thunder_probability_percent).toFixed(2)}}%，${{payload.thunder_min_seconds}}s-${{payload.thunder_max_seconds}}s`;
    }}

    async function saveGroupControlConfig() {{
      const status = document.getElementById("groupControlStatus");
      status.textContent = "正在保存...";
      const payload = await api("/admin/api/group-control", {{
        method: "PUT",
        body: JSON.stringify({{
          reread_probability_percent: Number(document.getElementById("rereadProbabilityInput").value),
          thunder_probability_percent: Number(document.getElementById("thunderProbabilityInput").value),
          min_seconds: Number(document.getElementById("thunderMinSecondsInput").value),
          max_seconds: Number(document.getElementById("thunderMaxSecondsInput").value),
        }}),
      }});
      document.getElementById("rereadProbabilityInput").value = Number(payload.reread_probability_percent).toFixed(2);
      document.getElementById("thunderProbabilityInput").value = Number(payload.thunder_probability_percent).toFixed(2);
      document.getElementById("thunderMinSecondsInput").value = payload.thunder_min_seconds;
      document.getElementById("thunderMaxSecondsInput").value = payload.thunder_max_seconds;
      status.textContent = `已保存：复读 ${{Number(payload.reread_probability_percent).toFixed(2)}}%，禁言 ${{Number(payload.thunder_probability_percent).toFixed(2)}}%，${{payload.thunder_min_seconds}}s-${{payload.thunder_max_seconds}}s`;
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
      const payload = await api("/admin/api/admins");
      const author = payload.author || {{
        qq: payload.author_qq,
        display_name: payload.author_qq,
      }};
      const adminItems = payload.admin_items || payload.admins.map(qq => ({{
        qq,
        display_name: qq,
      }}));
      const admins = adminItems.map(item => {{
        const qq = Number(item.qq);
        const displayName = item.display_name || qq;
        return `<li>${{escapeHtml(displayName)}} <button onclick="removeAdmin(${{qq}})">删除</button></li>`;
      }}).join("");
      document.getElementById("adminList").innerHTML = `<li>作者：${{escapeHtml(author.display_name || author.qq)}}（固定管理员）</li>${{admins}}`;
    }}

    async function addAdmin() {{
      const input = document.getElementById("adminInput");
      const qq = Number(input.value.trim());
      if (!qq) return;
      await api("/admin/api/admins", {{ method: "POST", body: JSON.stringify({{ qq }}) }});
      input.value = "";
      await loadAdmins();
    }}

    async function removeAdmin(qq) {{
      await api(`/admin/api/admins/${{qq}}`, {{ method: "DELETE" }});
      await loadAdmins();
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
    Promise.all([loadStatus().then(loadGroups), loadGroupMessages(), loadPlugins(), loadAiProvider(), loadAdmins(), loadLogs(), loadKunUsers(true)]).catch(error => {{
      document.body.insertAdjacentHTML("beforeend", `<pre>${{error.message}}</pre>`);
    }});
  </script>
</body>
</html>"""


async def get_connected_group_names() -> dict[int, str]:
    names: dict[int, str] = {}
    try:
        bots = nonebot.get_bots().values()
    except Exception:
        return names

    for bot in bots:
        try:
            groups = await bot.call_api("get_group_list")
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
