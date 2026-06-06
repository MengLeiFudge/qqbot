from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess

from qqbot.config import DEFAULT_AUTHOR_NAME, RuntimeSettings
from qqbot.features.ai.diagnostics import AiDiagnosticsStore
from qqbot.features.ai.pending_task_store import AiPendingTaskStore
from qqbot.features.ai.profile_registry import list_enabled_profiles, load_ai_profiles
from qqbot.features.ai.runtime import (
    get_current_ai_profile_name,
    get_default_ai_profile_name,
    list_ai_profile_fallback_order,
)
from qqbot.features.ai.chat_memory_store import ChatMemoryStore
from qqbot.features.ai.domain_knowledge_store import (
    DomainKnowledgeStore,
    build_seed_knowledge_candidates,
)
from qqbot.services.group_message_log_store import GroupMessageLogStore
from qqbot.services.group_nick_store import GroupNickStore
from qqbot.services.kun_service import KunService
from qqbot.services.plugin_registry import get_plugin_spec_by_id, list_visible_plugin_specs
from qqbot.services.settings_store import SettingsStore

STARTUP_LOG_FILES = {"launcher.log", "qqbot_stdout.log", "qqbot_stderr.log"}
AI_CONFIG_LOCKED_MESSAGE = "AI 模型由 qqbot.toml 控制；请修改 [ai].default_profile / [ai.providers] 后重启 bot1。"


@dataclass(slots=True)
class AdminService:
    settings: RuntimeSettings
    store: SettingsStore
    project_root: Path

    @classmethod
    def from_settings(cls, settings: RuntimeSettings) -> "AdminService":
        return cls(
            settings=settings,
            store=SettingsStore(settings.data_root, settings.author_qq),
            project_root=Path(__file__).resolve().parents[4],
        )

    def list_groups(
        self,
        group_names: dict[int, str] | None = None,
    ) -> list[dict[str, object]]:
        group_names = group_names or {}
        group_ids = sorted(set(self._list_known_group_ids()) | set(group_names))
        return [
            {
                "group_id": group_id,
                "group_name": group_names.get(group_id, ""),
                "display_name": self._format_group_display_name(
                    group_id,
                    group_names.get(group_id, ""),
                ),
            }
            for group_id in group_ids
        ]

    def list_plugins(self) -> dict[str, object]:
        states = self.store.list_plugin_states()
        return {
            "plugins": [
                {
                    "id": spec.id,
                    "name": spec.name,
                    "global_enabled": states.get(spec.id, True),
                    "commands": list(spec.commands),
                    "scopes": list(spec.scopes),
                    "requires_direct_at": spec.requires_direct_at,
                    "ai_capabilities": list(spec.ai_capabilities),
                    "admin_only": spec.admin_only,
                }
                for spec in list_visible_plugin_specs()
            ],
        }

    def set_plugin_enabled(self, plugin_id: str, enabled: bool) -> dict[str, object]:
        spec = get_plugin_spec_by_id(plugin_id)
        if spec is None:
            raise ValueError(f"Unknown plugin id: {plugin_id}")
        self.store.set_plugin_enabled(spec.id, enabled)
        return {
            "plugin": {
                "id": spec.id,
                "name": spec.name,
                "global_enabled": self.store.get_plugin_enabled(spec.id),
                "ai_capabilities": list(spec.ai_capabilities),
                "admin_only": spec.admin_only,
            },
        }

    def get_group_control_config(self) -> dict[str, object]:
        return {
            "file_cleanup_enabled": True,
            "file_cleanup_description": "作者在群内 @机器人 发送“通知清理文件”，统计超过一周的外层群文件，并按上传者总大小禁言。",
        }

    def get_kun_user(self, qq: int) -> dict[str, object]:
        payload = self._kun_service().build_admin_user_snapshot(qq)
        if payload is None:
            raise ValueError(f"Kun user not found: {qq}")
        return payload

    def update_kun_user(self, qq: int, updates: dict[str, object]) -> dict[str, object]:
        return self._kun_service().update_admin_user_fields(qq, updates)

    def list_kun_users(self) -> dict[str, object]:
        service = self._kun_service()
        nick_store = GroupNickStore(self.settings.data_root / "settings" / "group_nick.json")
        return {
            "users": [
                {
                    "qq": user.qq,
                    "name": user.name,
                    "level": user.level,
                    "money": user.money,
                    "display_name": self._format_user_display_name(
                        user.qq,
                        nick_store.resolve_display_name(0, user.qq),
                    ),
                }
                for user in service.get_level_rank()
            ],
        }

    def list_group_messages(
        self,
        group_names: dict[int, str] | None = None,
    ) -> dict[str, object]:
        return GroupMessageLogStore(self.settings.data_root).list_group_messages(
            group_names or {},
            limit_per_group=80,
        )

    def rebuild_memory_facts(self, group_id: int) -> dict[str, int]:
        return ChatMemoryStore(self.settings.data_root).rebuild_facts(group_id)

    def debug_memory_search(
        self,
        group_id: int,
        query: str,
        limit: int = 6,
    ) -> dict[str, object]:
        return ChatMemoryStore(self.settings.data_root).debug_search(group_id, query, limit=limit)

    def upsert_memory_fact(self, payload: dict[str, object]) -> dict[str, object]:
        fact = ChatMemoryStore(self.settings.data_root).upsert_trusted_fact(
            group_id=int(payload.get("group_id", 0)),
            subject=str(payload.get("subject", "")),
            predicate=str(payload.get("predicate", "")),
            object=str(payload.get("object", "")),
            confidence=float(payload.get("confidence", 1.0)),
            source_type=str(payload.get("source_type", "system")),
            trust_level=str(payload.get("trust_level", "system")),
            topics=tuple(str(item) for item in payload.get("topics", []) if str(item).strip())
            if isinstance(payload.get("topics", []), list)
            else (),
            entities=tuple(str(item) for item in payload.get("entities", []) if str(item).strip())
            if isinstance(payload.get("entities", []), list)
            else (),
        )
        return {"fact": self._memory_fact_to_payload(fact)}

    def set_memory_fact_status(self, fact_id: int, status: str) -> dict[str, object]:
        updated = ChatMemoryStore(self.settings.data_root).set_fact_status(fact_id, status)
        return {"fact_id": fact_id, "status": status, "updated": updated}

    def list_domain_knowledge(
        self,
        *,
        status: str = "",
        domain: str = "",
        limit: int = 100,
    ) -> dict[str, object]:
        records = DomainKnowledgeStore(self.settings.data_root).list_records(
            status=status,
            domain=domain,
            limit=limit,
        )
        return {"records": [self._domain_knowledge_to_payload(record) for record in records]}

    def seed_domain_knowledge_candidates(self) -> dict[str, object]:
        store = DomainKnowledgeStore(self.settings.data_root)
        records = []
        for candidate in build_seed_knowledge_candidates():
            records.append(
                store.upsert_candidate(
                    domain=candidate["domain"],
                    space_id=candidate["space_id"],
                    source_type=candidate["source_type"],
                    source_uri=candidate["source_uri"],
                    title=candidate["title"],
                    summary=candidate["summary"],
                    evidence=candidate["evidence"],
                    trust_level=candidate["trust_level"],
                    risk=candidate["risk"],
                    auto_trust=candidate.get("auto_trust") == "true",
                )
            )
        return {"records": [self._domain_knowledge_to_payload(record) for record in records]}

    def set_domain_knowledge_status(self, record_id: str, status: str) -> dict[str, object]:
        updated = DomainKnowledgeStore(self.settings.data_root).set_status(record_id, status)
        return {"id": record_id, "status": status, "updated": updated}

    def list_ai_pending_tasks(self, *, status: str = "", limit: int = 100) -> dict[str, object]:
        records = AiPendingTaskStore(self.settings.data_root).list_records(status=status, limit=limit)
        return {"tasks": [self._pending_task_to_payload(record) for record in records]}

    def list_ai(self) -> dict[str, object]:
        profiles = load_ai_profiles(self.settings.ai_profile_file)
        enabled_profiles = list_enabled_profiles(profiles)
        current_profile = get_current_ai_profile_name(self.settings, self.store, profiles)
        fallback_order = list_ai_profile_fallback_order(self.settings, self.store, profiles)
        profile_payloads = [
            {
                "name": profile.name,
                "provider": profile.provider,
                "model": profile.model,
                "note": profile.note,
                "enabled": profile.enabled,
            }
            for profile in enabled_profiles
        ]
        return {
            "current_profile": current_profile,
            "default_profile": get_default_ai_profile_name(self.settings),
            "fallback_order": list(fallback_order),
            "profiles": profile_payloads,
            "config_locked": True,
            "config_source": str(self.settings.ai_profile_file),
            "message": AI_CONFIG_LOCKED_MESSAGE,
        }

    def set_ai_provider(self, profile: str) -> dict[str, object]:
        raise ValueError(AI_CONFIG_LOCKED_MESSAGE)

    def set_ai_profile_priority(self, profiles: list[str]) -> dict[str, object]:
        raise ValueError(AI_CONFIG_LOCKED_MESSAGE)

    def list_ai_diagnostics(self, limit: int = 100) -> dict[str, object]:
        safe_limit = max(1, min(int(limit), 500))
        return AiDiagnosticsStore(self.settings.data_root).summary(limit=safe_limit)

    def get_author(self) -> dict[str, object]:
        nick_store = GroupNickStore(self.settings.data_root / "settings" / "group_nick.json")
        return {
            "author_qq": self.settings.author_qq,
            "author_name": self.settings.author_name,
            "author": self._build_admin_display_item(
                self.settings.author_qq,
                self.settings.author_name,
                nick_store,
            ),
        }

    def get_status(self, connected_bot_count: int) -> dict[str, object]:
        return {
            "host": self.settings.host,
            "port": self.settings.port,
            "admin_url": f"http://{self.settings.host}:{self.settings.port}/admin",
            "onebot_ws_url": self.settings.onebot_ws_url,
            "data_root": str(self.settings.data_root),
            "connected_bot_count": connected_bot_count,
            "onebot_connected": connected_bot_count > 0,
        }

    def schedule_restart(self) -> dict[str, object]:
        script = self.project_root / "scripts" / "start-nonebot2.bat"
        if not script.is_file():
            raise FileNotFoundError(f"Restart script not found: {script}")

        if os.name == "nt":
            creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
                subprocess,
                "CREATE_NO_WINDOW",
                0,
            )
            subprocess.Popen(
                self._build_windows_restart_command(script),
                cwd=str(self.project_root),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
            )
        else:
            subprocess.Popen(
                ["sh", "-c", f"sleep 2 && {subprocess.list2cmdline([str(script), '-SkipInstall', '-RestartBot'])}"],
                cwd=str(self.project_root),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        return {
            "scheduled": True,
            "message": "Bot restart has been scheduled.",
        }

    def _build_windows_restart_command(self, script: Path) -> list[str]:
        return [
            str(script),
            "-SkipInstall",
            "-RestartBot",
        ]

    def list_startup_logs(self, limit: int = 10) -> list[dict[str, object]]:
        logs_root = self._startup_logs_root()
        if not logs_root.exists():
            return []

        runs = [
            path
            for path in logs_root.iterdir()
            if path.is_dir() and self._is_safe_run_id(path.name)
        ]
        runs.sort(key=lambda path: path.name, reverse=True)
        return [
            {
                "run_id": path.name,
                "files": sorted(
                    file_path.name
                    for file_path in path.iterdir()
                    if file_path.is_file() and file_path.name in STARTUP_LOG_FILES
                ),
            }
            for path in runs[:limit]
        ]

    def read_startup_log(
        self,
        run_id: str,
        file_name: str,
        tail_lines: int = 200,
    ) -> dict[str, object]:
        if not self._is_safe_run_id(run_id):
            raise ValueError("Unsafe startup log run id.")
        if file_name not in STARTUP_LOG_FILES:
            raise ValueError("Unsupported startup log file.")

        path = self._startup_logs_root() / run_id / file_name
        if not path.is_file():
            raise FileNotFoundError(f"Startup log not found: {run_id}/{file_name}")

        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return {
            "run_id": run_id,
            "file_name": file_name,
            "content": "\n".join(lines[-tail_lines:]),
        }

    def _list_known_group_ids(self) -> list[int]:
        group_ids: set[int] = set()
        group_ids.update(GroupMessageLogStore(self.settings.data_root).list_group_ids())

        root = self.store.func_state_root
        if not root.exists():
            return sorted(group_ids)

        for path in root.glob("*.json"):
            if path.stem.isdigit():
                group_ids.add(int(path.stem))
        return sorted(group_ids)

    def _startup_logs_root(self) -> Path:
        return self.settings.data_root.parent / "logs" / "start_all"

    def _kun_service(self) -> KunService:
        return KunService(self.settings.data_root / "data" / "kun" / "users.json")

    @staticmethod
    def _is_safe_run_id(run_id: str) -> bool:
        return bool(run_id) and all(char.isdigit() or char == "-" for char in run_id)

    @staticmethod
    def _format_group_display_name(group_id: int, group_name: str) -> str:
        return f"{group_name}（{group_id}）" if group_name else str(group_id)

    @staticmethod
    def _format_user_display_name(qq: int, name: str) -> str:
        name = name.strip()
        return f"{name}（{qq}）" if name and name != str(qq) else str(qq)

    def _build_admin_display_item(
        self,
        qq: int,
        fallback_name: str = "",
        nick_store: GroupNickStore | None = None,
    ) -> dict[str, object]:
        name = self._resolve_admin_name(qq, fallback_name, nick_store)
        return {
            "qq": qq,
            "name": name,
            "display_name": f"{name}（{qq}）" if name else str(qq),
        }

    def _resolve_admin_name(
        self,
        qq: int,
        fallback_name: str = "",
        nick_store: GroupNickStore | None = None,
    ) -> str:
        if nick_store is None:
            nick_store = GroupNickStore(
                self.settings.data_root / "settings" / "group_nick.json"
            )
        resolved = nick_store.resolve_display_name(0, qq).strip()
        if resolved and resolved != str(qq):
            return resolved

        fallback_name = fallback_name.strip()
        if fallback_name and fallback_name not in {str(qq), DEFAULT_AUTHOR_NAME}:
            return fallback_name
        return ""

    @staticmethod
    def _memory_fact_to_payload(fact: object) -> dict[str, object]:
        return {
            "id": getattr(fact, "id"),
            "group_id": getattr(fact, "group_id"),
            "subject": getattr(fact, "subject"),
            "predicate": getattr(fact, "predicate"),
            "object": getattr(fact, "object"),
            "confidence": getattr(fact, "confidence"),
            "source_message_ids": list(getattr(fact, "source_message_ids")),
            "topics": list(getattr(fact, "topics")),
            "entities": list(getattr(fact, "entities")),
            "updated_at": getattr(fact, "updated_at"),
            "source_type": getattr(fact, "source_type"),
            "trust_level": getattr(fact, "trust_level"),
            "status": getattr(fact, "status"),
        }

    @staticmethod
    def _domain_knowledge_to_payload(record: object) -> dict[str, object]:
        return {
            "id": getattr(record, "id"),
            "status": getattr(record, "status"),
            "domain": getattr(record, "domain"),
            "space_id": getattr(record, "space_id"),
            "source_type": getattr(record, "source_type"),
            "source_uri": getattr(record, "source_uri"),
            "title": getattr(record, "title"),
            "summary": getattr(record, "summary"),
            "evidence": getattr(record, "evidence"),
            "source_hash": getattr(record, "source_hash"),
            "trust_level": getattr(record, "trust_level"),
            "risk": getattr(record, "risk"),
            "updated_at": getattr(record, "updated_at"),
            "stale_of": getattr(record, "stale_of"),
        }

    @staticmethod
    def _pending_task_to_payload(record: object) -> dict[str, object]:
        return {
            "task_id": getattr(record, "task_id"),
            "status": getattr(record, "status"),
            "group_id": getattr(record, "group_id"),
            "user_id": getattr(record, "user_id"),
            "message_id": getattr(record, "message_id"),
            "prompt": getattr(record, "prompt"),
            "decision": getattr(record, "decision"),
            "created_at": getattr(record, "created_at"),
            "updated_at": getattr(record, "updated_at"),
            "ack_sent": getattr(record, "ack_sent"),
            "result_message_id": getattr(record, "result_message_id"),
            "error": getattr(record, "error"),
        }
