from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess

from qqbot.config import DEFAULT_AUTHOR_NAME, RuntimeSettings
from qqbot.services.ai_profile_registry import list_enabled_profiles, load_ai_profiles
from qqbot.services.ai_runtime import get_current_ai_profile_name, get_default_ai_profile_name
from qqbot.services.group_nick_store import GroupNickStore
from qqbot.services.kun_service import KunService
from qqbot.services.plugin_registry import get_plugin_spec_by_id, list_visible_plugin_specs
from qqbot.services.settings_store import SettingsStore
from qqbot.services.thunder_service import clamp_thunder_percent, normalize_thunder_range

STARTUP_LOG_FILES = {"launcher.log", "qqbot_stdout.log", "qqbot_stderr.log"}


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
            project_root=Path(__file__).resolve().parents[3],
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

    def get_group_control_config(self, group_id: int) -> dict[str, object]:
        chance, min_seconds, max_seconds = self.store.get_thunder_config(group_id)
        return self._build_group_control_config(group_id, chance, min_seconds, max_seconds)

    def set_group_control_config(
        self,
        group_id: int,
        probability_percent: float,
        min_seconds: int,
        max_seconds: int,
    ) -> dict[str, object]:
        chance = clamp_thunder_percent(probability_percent)
        min_seconds, max_seconds = normalize_thunder_range(min_seconds, max_seconds)
        self.store.set_thunder_config(group_id, chance, min_seconds, max_seconds)
        return self._build_group_control_config(group_id, chance, min_seconds, max_seconds)

    def get_kun_user(self, qq: int) -> dict[str, object]:
        payload = self._kun_service().build_admin_user_snapshot(qq)
        if payload is None:
            raise ValueError(f"Kun user not found: {qq}")
        return payload

    def update_kun_user(self, qq: int, updates: dict[str, object]) -> dict[str, object]:
        return self._kun_service().update_admin_user_fields(qq, updates)

    def list_ai(self) -> dict[str, object]:
        profiles = load_ai_profiles(self.settings.ai_profile_file)
        enabled_profiles = list_enabled_profiles(profiles)
        current_profile = get_current_ai_profile_name(self.settings, self.store, profiles)
        return {
            "enabled": self.settings.ai_enabled,
            "current_profile": current_profile,
            "default_profile": get_default_ai_profile_name(self.settings),
            "profiles": [
                {
                    "name": profile.name,
                    "provider": profile.provider,
                    "model": profile.model,
                    "note": profile.note,
                    "enabled": profile.enabled,
                    "supports_vision": profile.supports_vision,
                }
                for profile in enabled_profiles
            ],
        }

    def set_ai_provider(self, profile: str) -> dict[str, object]:
        profiles = load_ai_profiles(self.settings.ai_profile_file)
        if profile not in {item.name for item in list_enabled_profiles(profiles)}:
            raise ValueError(f"Unknown AI profile: {profile}")
        self.store.set_ai_provider(profile)
        return self.list_ai()

    def list_admins(self) -> dict[str, object]:
        admins = self.store.list_bot_admins()
        enabled_admins = sorted(int(qq) for qq, enabled in admins.items() if enabled)
        nick_store = GroupNickStore(self.settings.data_root / "settings" / "group_nick.json")
        return {
            "author_qq": self.settings.author_qq,
            "author_name": self.settings.author_name,
            "admins": enabled_admins,
            "author": self._build_admin_display_item(
                self.settings.author_qq,
                self.settings.author_name,
                nick_store,
            ),
            "admin_items": [
                self._build_admin_display_item(qq, nick_store=nick_store)
                for qq in enabled_admins
            ],
        }

    def set_admin(self, qq: int, enabled: bool) -> dict[str, object]:
        if qq == self.settings.author_qq:
            enabled = True
        self.store.set_bot_admin(qq, enabled)
        return self.list_admins()

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
        script = self.project_root / "scripts" / "start_all.bat"
        if not script.is_file():
            raise FileNotFoundError(f"Restart script not found: {script}")

        if os.name == "nt":
            creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
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
            "wt.exe",
            "-w",
            "-1",
            "new-tab",
            "--title",
            "QQBot-Restart",
            "-d",
            str(self.project_root),
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
        nick_path = self.store.settings_root / "group_nick.json"
        if nick_path.exists():
            try:
                nick_store = GroupNickStore(nick_path)
                group_ids.update(int(group_id) for group_id in nick_store.records if group_id.isdigit())
            except Exception:
                pass

        root = self.store.func_state_root
        if not root.exists():
            return sorted(group_ids)

        for path in root.glob("*.json"):
            if path.stem.isdigit():
                group_ids.add(int(path.stem))
        return sorted(group_ids)

    def _startup_logs_root(self) -> Path:
        return self.project_root / "logs" / "start_all"

    def _kun_service(self) -> KunService:
        return KunService(self.settings.data_root / "data" / "kun" / "users.json")

    @staticmethod
    def _is_safe_run_id(run_id: str) -> bool:
        return bool(run_id) and all(char.isdigit() or char == "-" for char in run_id)

    @staticmethod
    def _format_group_display_name(group_id: int, group_name: str) -> str:
        return f"{group_name}（{group_id}）" if group_name else str(group_id)

    @staticmethod
    def _build_group_control_config(
        group_id: int,
        chance: float,
        min_seconds: int,
        max_seconds: int,
    ) -> dict[str, object]:
        return {
            "group_id": group_id,
            "chance": chance,
            "probability_percent": chance * 100,
            "min_seconds": min_seconds,
            "max_seconds": max_seconds,
        }

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
