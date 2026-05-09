from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import time
import tomllib

from qqbot.config import DEFAULT_CONFIG_FILE
from qqbot.services.settings_store import SettingsStore


DEFAULT_CODEX_MODEL = "gpt-5.5"
DEFAULT_CODEX_TIMEOUT_SECONDS = 30 * 60
DEFAULT_CODEX_SESSION_IDLE_TTL_SECONDS = 20 * 60
PROJECT_INDEX_FILE_NAMES = {"README.md", "AGENTS.md", "info.json", "locale.cfg", "changelog.txt"}
PROJECT_INDEX_EXTENSIONS = {".md", ".json", ".cfg", ".txt"}


@dataclass(frozen=True, slots=True)
class CodexProjectBinding:
    project_id: str
    display_name: str
    repo_path: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CodexProjectMatch:
    project: CodexProjectBinding
    confidence: float
    reason: str


@dataclass(frozen=True, slots=True)
class CodexTaskRequest:
    project: CodexProjectBinding
    actor_user_id: str
    group_id: str | None
    prompt: str
    evidence: str
    model: str = DEFAULT_CODEX_MODEL
    timeout_seconds: int = DEFAULT_CODEX_TIMEOUT_SECONDS
    progress_callback: Callable[["CodexProgressEvent"], Awaitable[None]] | None = None


@dataclass(frozen=True, slots=True)
class CodexSessionRequest:
    project: CodexProjectBinding
    actor_user_id: str
    group_id: str | None
    session_id: str
    prompt: str
    transcript: tuple[tuple[str, str], ...]
    source_context: tuple[str, ...] = ()
    mode: str = "discuss"
    model: str = DEFAULT_CODEX_MODEL
    timeout_seconds: int = DEFAULT_CODEX_TIMEOUT_SECONDS
    progress_callback: Callable[["CodexProgressEvent"], Awaitable[None]] | None = None


@dataclass(frozen=True, slots=True)
class CodexTaskResult:
    ok: bool
    message: str
    exit_code: int | None = None


@dataclass(frozen=True, slots=True)
class CodexProgressEvent:
    phase: str
    message: str
    stream: str = ""
    created_at: int = 0


@dataclass(frozen=True, slots=True)
class _CodexProcessOutput:
    stdout: str
    stderr: str
    returncode: int | None


@dataclass(frozen=True, slots=True)
class CodexDiscussionTask:
    task_id: str
    project_id: str
    project_display_name: str
    status: str
    summary: str
    raw_messages: tuple[str, ...]
    evidence: tuple[str, ...]
    created_by: str
    group_id: str | None
    last_codex_result: str = ""
    created_at: int = 0
    updated_at: int = 0


@dataclass(frozen=True, slots=True)
class CodexSession:
    session_id: str
    project_id: str
    project_display_name: str
    status: str
    created_by: str
    group_id: str | None
    transcript: tuple[tuple[str, str], ...] = ()
    pending_messages: tuple[str, ...] = ()
    created_at: int = 0
    updated_at: int = 0


DEFAULT_CODEX_PROJECTS: dict[str, CodexProjectBinding] = {
    "mlj_dspmods": CodexProjectBinding(
        project_id="mlj_dspmods",
        display_name="MLJ_DSPmods",
        repo_path="/mnt/d/project/csharp/DSP MOD/MLJ_DSPmods",
        aliases=("分馏", "万物分馏", "FE", "FractionateEverything", "DSP MOD", "MLJ_DSPmods"),
    ),
    "dsp_calc": CodexProjectBinding(
        project_id="dsp_calc",
        display_name="dsp-calc",
        repo_path="/mnt/d/project/js/dsp-calc",
        aliases=("dsp-calc", "DSP 计算器", "计算器"),
    ),
    "qqbot": CodexProjectBinding(
        project_id="qqbot",
        display_name="qqbot",
        repo_path="/mnt/d/project/python/qqbot",
        aliases=("机器人", "bot", "qqbot", "棉花糖"),
    ),
    "tfwr_simulator": CodexProjectBinding(
        project_id="tfwr_simulator",
        display_name="TFWR_Simulator",
        repo_path="/mnt/d/project/python/TFWR_Simulator",
        aliases=("TFWR", "模拟器", "排行榜", "GameSimulator", "TFWR_Simulator"),
    ),
    "factorio_mods": CodexProjectBinding(
        project_id="factorio_mods",
        display_name="MLJ_Factorio_Mods",
        repo_path="/mnt/d/project/lua/factorio/MLJ_Factorio_Mods",
        aliases=("Factorio", "异星工厂", "异星模组", "MLJ_Factorio_Mods", "section autocraft", "section-autocraft"),
    ),
}
DEFAULT_CODEX_GROUPS = {
    "319567534": "mlj_dspmods",
}


class CodexTaskStore:
    def __init__(self, data_root: Path) -> None:
        self.path = Path(data_root) / "ai" / "codex_tasks.json"

    def list_tasks(self) -> tuple[CodexDiscussionTask, ...]:
        payload = self._read_payload()
        tasks = payload.get("tasks", [])
        if not isinstance(tasks, list):
            return ()
        return tuple(_task_from_json(item) for item in tasks if isinstance(item, dict))

    def get_task(self, task_id: str) -> CodexDiscussionTask | None:
        normalized_id = task_id.strip().upper()
        for task in self.list_tasks():
            if task.task_id == normalized_id:
                return task
        return None

    def create_draft(
        self,
        *,
        project: CodexProjectBinding,
        actor_user_id: str,
        group_id: str | None,
        message: str,
        evidence: str,
    ) -> CodexDiscussionTask:
        payload = self._read_payload()
        now = int(time.time())
        next_number = int(payload.get("next_id", 1))
        task = CodexDiscussionTask(
            task_id=f"CODEX-{next_number:04d}",
            project_id=project.project_id,
            project_display_name=project.display_name,
            status="draft",
            summary=_summarize_codex_task(message),
            raw_messages=(message.strip(),),
            evidence=_clean_tuple(evidence),
            created_by=actor_user_id,
            group_id=group_id,
            created_at=now,
            updated_at=now,
        )
        payload["next_id"] = next_number + 1
        payload.setdefault("tasks", []).append(_task_to_json(task))
        self._write_payload(payload)
        return task

    def append_message(
        self,
        task_id: str,
        message: str,
        *,
        evidence: str = "",
    ) -> CodexDiscussionTask:
        task = self.get_task(task_id)
        if task is None:
            raise ValueError(f"Codex 任务不存在：{task_id}")
        updated = CodexDiscussionTask(
            task_id=task.task_id,
            project_id=task.project_id,
            project_display_name=task.project_display_name,
            status=task.status,
            summary=task.summary,
            raw_messages=(*task.raw_messages, message.strip()),
            evidence=(*task.evidence, *_clean_tuple(evidence)),
            created_by=task.created_by,
            group_id=task.group_id,
            last_codex_result=task.last_codex_result,
            created_at=task.created_at,
            updated_at=int(time.time()),
        )
        self._replace_task(updated)
        return updated

    def record_result(self, task_id: str, result: CodexTaskResult) -> CodexDiscussionTask:
        task = self.get_task(task_id)
        if task is None:
            raise ValueError(f"Codex 任务不存在：{task_id}")
        updated = CodexDiscussionTask(
            task_id=task.task_id,
            project_id=task.project_id,
            project_display_name=task.project_display_name,
            status="done" if result.ok else "failed",
            summary=task.summary,
            raw_messages=task.raw_messages,
            evidence=task.evidence,
            created_by=task.created_by,
            group_id=task.group_id,
            last_codex_result=result.message.strip(),
            created_at=task.created_at,
            updated_at=int(time.time()),
        )
        self._replace_task(updated)
        return updated

    def mark_running(self, task_id: str) -> CodexDiscussionTask:
        task = self.get_task(task_id)
        if task is None:
            raise ValueError(f"Codex 任务不存在：{task_id}")
        updated = CodexDiscussionTask(
            task_id=task.task_id,
            project_id=task.project_id,
            project_display_name=task.project_display_name,
            status="running",
            summary=task.summary,
            raw_messages=task.raw_messages,
            evidence=task.evidence,
            created_by=task.created_by,
            group_id=task.group_id,
            last_codex_result=task.last_codex_result,
            created_at=task.created_at,
            updated_at=int(time.time()),
        )
        self._replace_task(updated)
        return updated

    def find_latest_draft(
        self,
        *,
        actor_user_id: str,
        group_id: str | None,
        project_id: str | None = None,
    ) -> CodexDiscussionTask | None:
        candidates = [
            task
            for task in self.list_tasks()
            if task.status == "draft"
            and task.created_by == actor_user_id
            and task.group_id == group_id
            and (project_id is None or task.project_id == project_id)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda task: task.updated_at)

    def _replace_task(self, updated: CodexDiscussionTask) -> None:
        payload = self._read_payload()
        tasks = payload.get("tasks", [])
        if not isinstance(tasks, list):
            tasks = []
        replaced = False
        for index, item in enumerate(tasks):
            if isinstance(item, dict) and str(item.get("task_id", "")).upper() == updated.task_id:
                tasks[index] = _task_to_json(updated)
                replaced = True
                break
        if not replaced:
            tasks.append(_task_to_json(updated))
        payload["tasks"] = tasks
        self._write_payload(payload)

    def _read_payload(self) -> dict[str, object]:
        if not self.path.exists():
            return {"next_id": 1, "tasks": []}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {"next_id": 1, "tasks": []}
        payload.setdefault("next_id", 1)
        payload.setdefault("tasks", [])
        return payload

    def _write_payload(self, payload: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class CodexSessionStore:
    def __init__(
        self,
        data_root: Path,
        idle_ttl_seconds: int = DEFAULT_CODEX_SESSION_IDLE_TTL_SECONDS,
    ) -> None:
        self.path = Path(data_root) / "ai" / "codex_sessions.json"
        self.idle_ttl_seconds = max(1, int(idle_ttl_seconds))

    def list_sessions(self) -> tuple[CodexSession, ...]:
        payload = self._read_payload()
        sessions = payload.get("sessions", [])
        if not isinstance(sessions, list):
            return ()
        return tuple(_session_from_json(item) for item in sessions if isinstance(item, dict))

    def get_session(self, session_id: str) -> CodexSession | None:
        normalized_id = session_id.strip().upper()
        for session in self.list_sessions():
            if session.session_id == normalized_id:
                return session
        return None

    def get_active_session(self, *, actor_user_id: str, group_id: str | None) -> CodexSession | None:
        if group_id is not None:
            return self.get_active_group_session(group_id)
        return self.get_active_private_session(actor_user_id)

    def get_active_group_session(self, group_id: str) -> CodexSession | None:
        candidates = [
            session
            for session in self.list_sessions()
            if session.status in {"discussing", "running"}
            and session.group_id == group_id
            and self._is_session_active_by_time(session)
        ]
        return _pick_latest_session(candidates)

    def get_active_private_session(self, actor_user_id: str) -> CodexSession | None:
        candidates = [
            session
            for session in self.list_sessions()
            if session.status in {"discussing", "running"}
            and session.created_by == actor_user_id
            and session.group_id is None
            and self._is_session_active_by_time(session)
        ]
        return _pick_latest_session(candidates)

    def get_running_project_session(
        self,
        project_id: str,
        *,
        exclude_session_id: str = "",
    ) -> CodexSession | None:
        candidates = [
            session
            for session in self.list_sessions()
            if session.status == "running"
            and session.project_id == project_id
            and session.session_id != exclude_session_id
        ]
        return _pick_latest_session(candidates)

    def create_session(
        self,
        *,
        project: CodexProjectBinding,
        actor_user_id: str,
        group_id: str | None,
    ) -> CodexSession:
        payload = self._read_payload()
        now = int(time.time())
        next_number = int(payload.get("next_id", 1))
        active = self.get_active_session(actor_user_id=actor_user_id, group_id=group_id)
        if active is not None:
            return active
        session = CodexSession(
            session_id=f"CODEX-S{next_number:04d}",
            project_id=project.project_id,
            project_display_name=project.display_name,
            status="discussing",
            created_by=actor_user_id,
            group_id=group_id,
            created_at=now,
            updated_at=now,
        )
        payload["next_id"] = next_number + 1
        payload.setdefault("sessions", []).append(_session_to_json(session))
        self._write_payload(payload)
        return session

    def append_turn(self, session_id: str, *, user_message: str, codex_message: str) -> CodexSession:
        session = self.get_session(session_id)
        if session is None:
            raise ValueError(f"Codex 会话不存在：{session_id}")
        updated = CodexSession(
            session_id=session.session_id,
            project_id=session.project_id,
            project_display_name=session.project_display_name,
            status=session.status,
            created_by=session.created_by,
            group_id=session.group_id,
            transcript=(
                *session.transcript,
                ("user", user_message.strip()),
                ("codex", codex_message.strip()),
            ),
            pending_messages=session.pending_messages,
            created_at=session.created_at,
            updated_at=int(time.time()),
        )
        self._replace_session(updated)
        return updated

    def append_pending_message(self, session_id: str, message: str) -> CodexSession:
        session = self.get_session(session_id)
        if session is None:
            raise ValueError(f"Codex 会话不存在：{session_id}")
        cleaned = message.strip()
        if not cleaned:
            return session
        updated = CodexSession(
            session_id=session.session_id,
            project_id=session.project_id,
            project_display_name=session.project_display_name,
            status=session.status,
            created_by=session.created_by,
            group_id=session.group_id,
            transcript=session.transcript,
            pending_messages=(*session.pending_messages, cleaned),
            created_at=session.created_at,
            updated_at=int(time.time()),
        )
        self._replace_session(updated)
        return updated

    def pop_pending_messages(self, session_id: str) -> tuple[str, ...]:
        session = self.get_session(session_id)
        if session is None:
            raise ValueError(f"Codex 会话不存在：{session_id}")
        pending = session.pending_messages
        if not pending:
            return ()
        updated = CodexSession(
            session_id=session.session_id,
            project_id=session.project_id,
            project_display_name=session.project_display_name,
            status=session.status,
            created_by=session.created_by,
            group_id=session.group_id,
            transcript=session.transcript,
            pending_messages=(),
            created_at=session.created_at,
            updated_at=int(time.time()),
        )
        self._replace_session(updated)
        return pending

    def mark_status(self, session_id: str, status: str) -> CodexSession:
        session = self.get_session(session_id)
        if session is None:
            raise ValueError(f"Codex 会话不存在：{session_id}")
        updated = CodexSession(
            session_id=session.session_id,
            project_id=session.project_id,
            project_display_name=session.project_display_name,
            status=status,
            created_by=session.created_by,
            group_id=session.group_id,
            transcript=session.transcript,
            pending_messages=session.pending_messages,
            created_at=session.created_at,
            updated_at=int(time.time()),
        )
        self._replace_session(updated)
        return updated

    def close_session(self, session_id: str) -> CodexSession:
        return self.mark_status(session_id, "closed")

    def _is_session_active_by_time(self, session: CodexSession) -> bool:
        if session.status == "running":
            return True
        updated_at = session.updated_at or session.created_at
        if updated_at <= 0:
            return False
        return int(time.time()) - updated_at <= self.idle_ttl_seconds

    def _replace_session(self, updated: CodexSession) -> None:
        payload = self._read_payload()
        sessions = payload.get("sessions", [])
        if not isinstance(sessions, list):
            sessions = []
        replaced = False
        for index, item in enumerate(sessions):
            if isinstance(item, dict) and str(item.get("session_id", "")).upper() == updated.session_id:
                sessions[index] = _session_to_json(updated)
                replaced = True
                break
        if not replaced:
            sessions.append(_session_to_json(updated))
        payload["sessions"] = sessions
        self._write_payload(payload)

    def _read_payload(self) -> dict[str, object]:
        if not self.path.exists():
            return {"next_id": 1, "sessions": []}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {"next_id": 1, "sessions": []}
        payload.setdefault("next_id", 1)
        payload.setdefault("sessions", [])
        return payload

    def _write_payload(self, payload: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _pick_latest_session(candidates: list[CodexSession]) -> CodexSession | None:
    if not candidates:
        return None
    return max(candidates, key=lambda session: session.updated_at)


def load_codex_projects(config_file: Path | None = None) -> dict[str, CodexProjectBinding]:
    config_path = Path(config_file or DEFAULT_CONFIG_FILE)
    if not config_path.exists():
        return dict(DEFAULT_CODEX_PROJECTS)
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    raw_codex = data.get("codex")
    if not isinstance(raw_codex, dict):
        return dict(DEFAULT_CODEX_PROJECTS)
    raw_projects = raw_codex.get("projects")
    if not isinstance(raw_projects, dict):
        return dict(DEFAULT_CODEX_PROJECTS)

    projects: dict[str, CodexProjectBinding] = {}
    for project_id, raw in raw_projects.items():
        if not isinstance(raw, dict):
            continue
        aliases = raw.get("aliases", ())
        if not isinstance(aliases, list):
            aliases = ()
        repo_path = str(raw.get("repo_path", "")).strip()
        if not repo_path:
            continue
        project = CodexProjectBinding(
            project_id=str(project_id),
            display_name=str(raw.get("display_name", project_id)).strip() or str(project_id),
            repo_path=repo_path,
            aliases=tuple(str(alias).strip() for alias in aliases if str(alias).strip()),
        )
        projects[project.project_id] = project
    return projects or dict(DEFAULT_CODEX_PROJECTS)


def get_codex_project_by_id(
    project_id: str,
    config_file: Path | None = None,
) -> CodexProjectBinding | None:
    return load_codex_projects(config_file).get(project_id.strip())


def load_codex_group_bindings(config_file: Path | None = None) -> dict[str, str]:
    config_path = Path(config_file or DEFAULT_CONFIG_FILE)
    if not config_path.exists():
        return dict(DEFAULT_CODEX_GROUPS)
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    raw_codex = data.get("codex")
    if not isinstance(raw_codex, dict):
        return dict(DEFAULT_CODEX_GROUPS)
    raw_groups = raw_codex.get("groups")
    if not isinstance(raw_groups, dict):
        return dict(DEFAULT_CODEX_GROUPS)
    groups: dict[str, str] = {}
    for group_id, raw in raw_groups.items():
        if isinstance(raw, str):
            groups[str(group_id)] = raw.strip()
        elif isinstance(raw, dict):
            project_id = str(raw.get("project", "")).strip()
            if project_id:
                groups[str(group_id)] = project_id
    return groups


def load_runtime_codex_group_bindings(data_root: Path) -> dict[str, str]:
    return SettingsStore(Path(data_root), 0).list_codex_group_bindings()


def get_codex_project_for_group(
    group_id: str | None,
    config_file: Path | None = None,
    data_root: Path | None = None,
) -> CodexProjectBinding | None:
    if group_id is None:
        return None
    group_key = str(group_id).strip()
    project_id = ""
    if data_root is not None:
        project_id = load_runtime_codex_group_bindings(data_root).get(group_key, "")
    if not project_id:
        project_id = load_codex_group_bindings(config_file).get(group_key, "")
    if not project_id:
        return None
    return get_codex_project_by_id(project_id, config_file)


def resolve_codex_project_for_session_start(
    project_query: str,
    *,
    group_id: str | None,
    data_root: Path,
    config_file: Path | None = None,
) -> CodexProjectMatch | None:
    cleaned = project_query.strip()
    if cleaned:
        return resolve_codex_project_for_text(
            cleaned,
            group_id=None,
            data_root=data_root,
            config_file=config_file,
        )

    group_project = get_codex_project_for_group(group_id, config_file, data_root=data_root)
    if group_project is not None:
        return CodexProjectMatch(group_project, 0.35, "当前群绑定项目")

    current_project = get_codex_project_by_id("qqbot", config_file)
    if current_project is None:
        return None
    return CodexProjectMatch(current_project, 0.2, "当前机器人仓库")


def resolve_codex_project_for_text(
    text: str,
    *,
    group_id: str | None,
    data_root: Path,
    config_file: Path | None = None,
) -> CodexProjectMatch | None:
    projects = load_codex_projects(config_file)
    learned_aliases = load_learned_project_aliases(data_root)
    query = _normalize_match_text(text)
    best: tuple[int, str, CodexProjectBinding] | None = None

    for project in projects.values():
        score, reason = _score_project_match(query, project, learned_aliases)
        if score <= 0:
            continue
        if best is None or score > best[0]:
            best = (score, reason, project)

    if best is None:
        group_project = get_codex_project_for_group(group_id, config_file, data_root=data_root)
        if group_project is None:
            return None
        return CodexProjectMatch(group_project, 0.35, "当前群绑定项目")

    confidence = min(0.99, best[0] / 100)
    return CodexProjectMatch(best[2], confidence, best[1])


def load_learned_project_aliases(data_root: Path) -> dict[str, str]:
    path = Path(data_root) / "settings" / "codex_project_aliases.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return {str(alias): str(project_id) for alias, project_id in payload.items()}


def learn_codex_project_alias(data_root: Path, alias: str, project_id: str) -> None:
    cleaned_alias = alias.strip(" ：:，,。")
    cleaned_project = project_id.strip()
    if not cleaned_alias or not cleaned_project:
        return
    path = Path(data_root) / "settings" / "codex_project_aliases.json"
    aliases = load_learned_project_aliases(data_root)
    aliases[cleaned_alias] = cleaned_project
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(aliases, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_project_name(
    text: str,
    projects: dict[str, CodexProjectBinding] | None = None,
) -> CodexProjectBinding | None:
    projects = projects or load_codex_projects()
    query = _normalize_match_text(text)
    for project in projects.values():
        names = (project.project_id, project.display_name, Path(project.repo_path).name, *project.aliases)
        if any(_normalize_match_text(name) in query for name in names if name):
            return project
    return None


def build_codex_fix_prompt(request: CodexTaskRequest) -> str:
    return (
        "本次是 QQ bot 转发给 Codex 的本地项目调用。\n"
        f"项目：{request.project.display_name}\n"
        f"触发用户：{request.actor_user_id}\n"
        f"来源群：{request.group_id or '未知'}\n"
        "以下只提供 QQ bot 收到的原始需求和上下文证据，不附加项目执行规则。\n"
        "用户原话：\n"
        f"{request.prompt.strip()}\n"
        "上下文证据：\n"
        f"{request.evidence.strip()}"
    )


def build_codex_session_prompt(request: CodexSessionRequest) -> str:
    transcript = "\n".join(f"{role}: {content}" for role, content in request.transcript)
    source_context = "\n".join(request.source_context)
    return (
        "本次是 QQ bot 转发给 Codex 的本地会话调用。\n"
        f"项目：{request.project.display_name}\n"
        f"会话：{request.session_id}\n"
        f"触发用户：{request.actor_user_id}\n"
        f"来源群：{request.group_id or '未知'}\n"
        f"本轮模式：{request.mode}\n"
        "以下只提供 QQ bot 中转的历史对话和当前用户消息，不附加项目执行规则。\n"
        "历史对话：\n"
        f"{transcript or '无'}\n"
        "来源上下文：\n"
        f"{source_context or '无'}\n"
        "当前用户消息：\n"
        f"{request.prompt.strip()}"
    )


def build_codex_exec_command(repo_path: str, model: str, *, sandbox: str = "workspace-write") -> list[str]:
    wsl_repo = to_wsl_path(repo_path)
    codex_prelude = (
        'codex_bin="codex"; '
        'if ! command -v codex >/dev/null 2>&1; then '
        'export NVM_DIR="$HOME/.nvm"; '
        '[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"; '
        'fi; '
        'if ! command -v codex >/dev/null 2>&1; then '
        'for candidate in "$HOME"/.nvm/versions/node/*/bin/codex "$HOME"/.local/bin/codex /usr/local/bin/codex; do '
        '[ -x "$candidate" ] && codex_bin="$candidate" && break; '
        'done; '
        'fi; '
        'if ! command -v "$codex_bin" >/dev/null 2>&1 && [ ! -x "$codex_bin" ]; then '
        'echo "找不到 Codex CLI，请先在 WSL 中安装或配置 PATH。" >&2; exit 127; '
        'fi'
    )
    script = (
        f"cd {shlex.quote(wsl_repo)} && "
        f"{codex_prelude} && "
        f'"$codex_bin" -a never exec -C {shlex.quote(wsl_repo)} -m {shlex.quote(model)} '
        f"-c model_provider=custom -s {shlex.quote(sandbox)} -"
    )
    return ["wsl.exe", "-e", "bash", "-lc", script]


def to_wsl_path(path: str | Path) -> str:
    raw = str(path).replace("\\", "/")
    if raw.startswith("/mnt/"):
        return raw
    if len(raw) >= 3 and raw[1] == ":" and raw[2] == "/":
        drive = raw[0].lower()
        return f"/mnt/{drive}/{raw[3:]}"
    return raw


def to_windows_path(path: str | Path) -> str:
    raw = str(path).replace("\\", "/")
    if raw.startswith("/mnt/") and len(raw) >= 7 and raw[6] == "/":
        drive = raw[5].upper()
        tail = raw[7:].replace("/", "\\")
        return f"{drive}:\\{tail}"
    return str(path)


def normalize_local_path(path: str | Path) -> Path:
    raw = str(path).strip().strip("\"'“”‘’")
    candidates: list[Path] = [Path(raw)]
    if _looks_like_windows_drive_path(raw):
        candidates.append(Path(to_wsl_path(raw)))
    if raw.replace("\\", "/").startswith("/mnt/"):
        candidates.append(Path(to_windows_path(raw)))

    for candidate in candidates:
        if candidate.exists():
            return candidate
    if os.name == "nt" and raw.replace("\\", "/").startswith("/mnt/"):
        return Path(to_windows_path(raw))
    if os.name != "nt" and _looks_like_windows_drive_path(raw):
        return Path(to_wsl_path(raw))
    return Path(raw)


def extract_codex_zip_artifacts(text: str, repo_path: str | Path) -> tuple[Path, ...]:
    repo_wsl = _normalize_wsl_path_for_compare(repo_path)
    artifacts: list[Path] = []
    seen: set[str] = set()
    for raw_path in _iter_zip_path_candidates(text):
        candidate_wsl = _normalize_wsl_path_for_compare(raw_path)
        if not _is_same_or_child_path(candidate_wsl, repo_wsl):
            continue
        local_path = normalize_local_path(raw_path)
        if local_path.suffix.lower() != ".zip" or not local_path.is_file():
            continue
        key = str(local_path.resolve())
        if key in seen:
            continue
        seen.add(key)
        artifacts.append(local_path)
    return tuple(artifacts)


async def run_codex_task(request: CodexTaskRequest) -> CodexTaskResult:
    if shutil.which("wsl.exe") is None:
        return CodexTaskResult(False, "没有找到 wsl.exe，无法启动本地 Codex。")

    command = build_codex_exec_command(request.project.repo_path, request.model)
    prompt = build_codex_fix_prompt(request)
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        return CodexTaskResult(False, f"启动 Codex 失败：{exc}")

    try:
        output = await _communicate_with_codex_process(
            process,
            prompt=prompt,
            timeout_seconds=request.timeout_seconds,
            progress_callback=request.progress_callback,
        )
    except TimeoutError:
        process.kill()
        await process.wait()
        return CodexTaskResult(False, "Codex 修复任务超时。", exit_code=None)

    stdout = _tail_text(output.stdout)
    stderr = _tail_text(output.stderr)
    if output.returncode == 0:
        return CodexTaskResult(True, stdout or "Codex 修复任务已结束。", exit_code=0)
    message = stderr or stdout or "Codex 修复任务失败，但没有输出错误详情。"
    return CodexTaskResult(False, message, exit_code=output.returncode)


async def run_codex_session_turn(request: CodexSessionRequest) -> CodexTaskResult:
    if shutil.which("wsl.exe") is None:
        return CodexTaskResult(False, "没有找到 wsl.exe，无法启动本地 Codex。")

    sandbox = "workspace-write" if request.mode == "execute" else "read-only"
    command = build_codex_exec_command(request.project.repo_path, request.model, sandbox=sandbox)
    prompt = build_codex_session_prompt(request)
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        return CodexTaskResult(False, f"启动 Codex 失败：{exc}")

    try:
        output = await _communicate_with_codex_process(
            process,
            prompt=prompt,
            timeout_seconds=request.timeout_seconds,
            progress_callback=request.progress_callback,
        )
    except TimeoutError:
        process.kill()
        await process.wait()
        return CodexTaskResult(False, "Codex 会话超时。", exit_code=None)

    stdout = _tail_text(output.stdout)
    stderr = _tail_text(output.stderr)
    if output.returncode == 0:
        return CodexTaskResult(True, stdout or "Codex 已回复。", exit_code=0)
    message = stderr or stdout or "Codex 会话失败，但没有输出错误详情。"
    return CodexTaskResult(False, message, exit_code=output.returncode)


async def _communicate_with_codex_process(
    process,
    *,
    prompt: str,
    timeout_seconds: int,
    progress_callback: Callable[[CodexProgressEvent], Awaitable[None]] | None = None,
) -> _CodexProcessOutput:
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []

    async def write_prompt() -> None:
        if process.stdin is None:
            return
        process.stdin.write(prompt.encode("utf-8"))
        await process.stdin.drain()
        process.stdin.close()
        if hasattr(process.stdin, "wait_closed"):
            await process.stdin.wait_closed()

    async def read_stream(stream, stream_name: str, chunks: list[str]) -> None:
        if stream is None:
            return
        while True:
            line = await stream.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace")
            chunks.append(text)
            cleaned = text.strip()
            if cleaned:
                await _emit_codex_progress(
                    progress_callback,
                    CodexProgressEvent(
                        phase="output",
                        message=cleaned,
                        stream=stream_name,
                        created_at=int(time.time()),
                    ),
                )

    await _emit_codex_progress(
        progress_callback,
        CodexProgressEvent(
            phase="started",
            message="Codex 进程已启动，正在等待输出。",
            created_at=int(time.time()),
        ),
    )
    await asyncio.wait_for(
        asyncio.gather(
            write_prompt(),
            read_stream(process.stdout, "stdout", stdout_chunks),
            read_stream(process.stderr, "stderr", stderr_chunks),
            process.wait(),
        ),
        timeout=timeout_seconds,
    )
    return _CodexProcessOutput(
        stdout="".join(stdout_chunks),
        stderr="".join(stderr_chunks),
        returncode=process.returncode,
    )


async def _emit_codex_progress(
    progress_callback: Callable[[CodexProgressEvent], Awaitable[None]] | None,
    event: CodexProgressEvent,
) -> None:
    if progress_callback is None:
        return
    await progress_callback(event)


def _tail_text(text: str, limit: int = 1200) -> str:
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[-limit:].strip()


def _iter_zip_path_candidates(text: str) -> tuple[str, ...]:
    patterns = (
        r"(?P<path>/mnt/[A-Za-z]/[^\r\n]*?\.zip)",
        r"(?P<path>[A-Za-z]:[\\/][^\r\n]*?\.zip)",
    )
    candidates: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            candidates.append(_clean_zip_path_candidate(match.group("path")))
    return tuple(candidate for candidate in candidates if candidate)


def _clean_zip_path_candidate(path: str) -> str:
    return path.strip().strip("\"'“”‘’`，,。；;：:")


def _normalize_wsl_path_for_compare(path: str | Path) -> str:
    return to_wsl_path(str(path).strip().strip("\"'“”‘’`")).replace("\\", "/").rstrip("/").lower()


def _looks_like_windows_drive_path(path: str) -> bool:
    return len(path) >= 3 and path[1] == ":" and path[2] in {"\\", "/"} and path[0].isalpha()


def _is_same_or_child_path(candidate: str, parent: str) -> bool:
    return candidate == parent or candidate.startswith(parent + "/")


def _task_from_json(payload: dict[str, object]) -> CodexDiscussionTask:
    return CodexDiscussionTask(
        task_id=str(payload.get("task_id", "")).upper(),
        project_id=str(payload.get("project_id", "")),
        project_display_name=str(payload.get("project_display_name", "")),
        status=str(payload.get("status", "draft")),
        summary=str(payload.get("summary", "")),
        raw_messages=tuple(str(item) for item in payload.get("raw_messages", []) if str(item).strip()),
        evidence=tuple(str(item) for item in payload.get("evidence", []) if str(item).strip()),
        created_by=str(payload.get("created_by", "")),
        group_id=str(payload["group_id"]) if payload.get("group_id") is not None else None,
        last_codex_result=str(payload.get("last_codex_result", "")),
        created_at=int(payload.get("created_at", 0) or 0),
        updated_at=int(payload.get("updated_at", 0) or 0),
    )


def _task_to_json(task: CodexDiscussionTask) -> dict[str, object]:
    return {
        "task_id": task.task_id,
        "project_id": task.project_id,
        "project_display_name": task.project_display_name,
        "status": task.status,
        "summary": task.summary,
        "raw_messages": list(task.raw_messages),
        "evidence": list(task.evidence),
        "created_by": task.created_by,
        "group_id": task.group_id,
        "last_codex_result": task.last_codex_result,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def _session_from_json(payload: dict[str, object]) -> CodexSession:
    transcript = []
    raw_transcript = payload.get("transcript", [])
    if isinstance(raw_transcript, list):
        for item in raw_transcript:
            if isinstance(item, dict):
                role = str(item.get("role", "")).strip()
                content = str(item.get("content", "")).strip()
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                role = str(item[0]).strip()
                content = str(item[1]).strip()
            else:
                continue
            if role and content:
                transcript.append((role, content))
    return CodexSession(
        session_id=str(payload.get("session_id", "")).upper(),
        project_id=str(payload.get("project_id", "")),
        project_display_name=str(payload.get("project_display_name", "")),
        status=str(payload.get("status", "discussing")),
        created_by=str(payload.get("created_by", "")),
        group_id=str(payload["group_id"]) if payload.get("group_id") is not None else None,
        transcript=tuple(transcript),
        pending_messages=tuple(
            str(item).strip()
            for item in payload.get("pending_messages", [])
            if str(item).strip()
        ),
        created_at=int(payload.get("created_at", 0) or 0),
        updated_at=int(payload.get("updated_at", 0) or 0),
    )


def _session_to_json(session: CodexSession) -> dict[str, object]:
    return {
        "session_id": session.session_id,
        "project_id": session.project_id,
        "project_display_name": session.project_display_name,
        "status": session.status,
        "created_by": session.created_by,
        "group_id": session.group_id,
        "transcript": [
            {"role": role, "content": content}
            for role, content in session.transcript
        ],
        "pending_messages": list(session.pending_messages),
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


def _clean_tuple(text: str) -> tuple[str, ...]:
    cleaned = text.strip()
    return (cleaned,) if cleaned else ()


def _summarize_codex_task(text: str, limit: int = 80) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip(" ：:，,。")
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "..."


def _score_project_match(
    query: str,
    project: CodexProjectBinding,
    learned_aliases: dict[str, str],
) -> tuple[int, str]:
    for alias, project_id in learned_aliases.items():
        if project_id == project.project_id and _normalize_match_text(alias) in query:
            return 110, f"已学习别名：{alias}"

    names = (project.project_id, project.display_name, Path(project.repo_path).name, *project.aliases)
    for alias in names:
        normalized = _normalize_match_text(alias)
        if normalized and normalized in query:
            return 100, f"项目别名：{alias}"

    hits = []
    for term in _iter_project_index_terms(project.repo_path):
        normalized = _normalize_match_text(term)
        if len(normalized) >= 2 and normalized in query:
            hits.append(term)
            if len(hits) >= 4:
                break
    if hits:
        return 70 + min(20, len(hits) * 5), "项目索引命中：" + "、".join(hits)
    return 0, ""


def _iter_project_index_terms(repo_path: str) -> tuple[str, ...]:
    root = Path(repo_path)
    if not root.exists():
        return ()
    terms: set[str] = {root.name}
    files_seen = 0
    for path in root.rglob("*"):
        if files_seen >= 240:
            break
        if any(part in {".git", ".venv", "node_modules", "__pycache__", "ModZips"} for part in path.parts):
            continue
        if path.is_dir():
            terms.add(path.name)
            continue
        if path.name not in PROJECT_INDEX_FILE_NAMES and path.suffix not in PROJECT_INDEX_EXTENSIONS:
            continue
        files_seen += 1
        terms.update(_split_index_text(path.stem))
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")[:120_000]
        except OSError:
            continue
        terms.update(_split_index_text(text))
    return tuple(sorted(terms, key=len, reverse=True))


def _split_index_text(text: str) -> set[str]:
    terms = set()
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,12}|[A-Za-z][A-Za-z0-9_-]{2,48}", text):
        terms.add(chunk)
    return terms


def _normalize_match_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text)).lower()
