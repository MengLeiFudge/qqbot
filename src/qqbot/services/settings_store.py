from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from qqbot.config import load_settings
from qqbot.services.feature_catalog import FeatureDefinition
from qqbot.services.plugin_registry import list_visible_plugin_specs

GLOBAL_CONFIG_KEY = "__global__"


class SettingsStore:
    def __init__(self, data_root: Path, author_qq: int) -> None:
        self.data_root = Path(data_root)
        self.author_qq = author_qq
        self.settings_root = self.data_root / "settings"
        self.func_state_root = self.settings_root / "func_state"

    def set_bot_admin(self, qq: int, is_admin: bool) -> None:
        admins = self._read_json(self.settings_root / "bot_admin.json", {})
        admins[str(qq)] = is_admin
        self._write_json(self.settings_root / "bot_admin.json", admins)

    def is_bot_admin(self, qq: int) -> bool:
        if qq == self.author_qq:
            return True
        admins = self._read_json(self.settings_root / "bot_admin.json", {})
        return bool(admins.get(str(qq), False))

    def is_bot_admin_or_self(self, qq: int, self_id: int | str | None) -> bool:
        if self_id is not None and str(qq) == str(self_id):
            return True
        return self.is_bot_admin(qq)

    def list_bot_admins(self) -> dict[str, bool]:
        return self._read_json(self.settings_root / "bot_admin.json", {})

    def get_group_feature_state(self, group_id: int, feature: FeatureDefinition) -> bool:
        return self.get_plugin_enabled(feature.plugin_id)

    def set_group_feature_state(
        self,
        group_id: int,
        feature: FeatureDefinition,
        is_open: bool,
    ) -> None:
        self.set_plugin_enabled(feature.plugin_id, is_open)

    def get_group_feature_states(self, group_id: int) -> dict[str, bool]:
        return self.list_plugin_states()

    def get_plugin_enabled(self, plugin_id: str) -> bool:
        states = self._read_json(self.settings_root / "plugin_state.json", {})
        return bool(states.get(plugin_id, True))

    def set_plugin_enabled(self, plugin_id: str, enabled: bool) -> None:
        states = self._read_json(self.settings_root / "plugin_state.json", {})
        states[plugin_id] = enabled
        self._write_json(self.settings_root / "plugin_state.json", states)

    def list_plugin_states(self) -> dict[str, bool]:
        states = self._read_json(self.settings_root / "plugin_state.json", {})
        return {
            spec.id: bool(states.get(spec.id, True))
            for spec in list_visible_plugin_specs()
        }

    def get_ai_provider(self, default_profile: str) -> str:
        settings = self._read_json(self.settings_root / "ai.json", {})
        profile = str(settings.get("provider", "")).strip()
        return profile or default_profile

    def set_ai_provider(self, profile: str) -> None:
        settings = self._read_json(self.settings_root / "ai.json", {})
        settings["provider"] = profile.strip()
        self._write_json(self.settings_root / "ai.json", settings)

    def list_codex_group_bindings(self) -> dict[str, str]:
        bindings = self._read_json(self.settings_root / "codex_group_bindings.json", {})
        return {
            str(group_id): str(project_id).strip()
            for group_id, project_id in bindings.items()
            if str(group_id).strip().isdigit() and str(project_id).strip()
        }

    def set_codex_group_binding(self, group_id: int, project_id: str) -> None:
        bindings = self.list_codex_group_bindings()
        cleaned_project = project_id.strip()
        key = str(group_id)
        if cleaned_project:
            bindings[key] = cleaned_project
        else:
            bindings.pop(key, None)
        self._write_json(self.settings_root / "codex_group_bindings.json", bindings)

    def remove_group_scoped_settings(self, group_id: int | str) -> list[str]:
        group_key = str(group_id).strip()
        removed: list[str] = []
        if not group_key.isdigit():
            return removed

        func_state_path = self.func_state_root / f"{group_key}.json"
        if func_state_path.exists():
            func_state_path.unlink()
            removed.append(str(func_state_path))

        for file_name in ("lolicon.json", "codex_group_bindings.json"):
            path = self.settings_root / file_name
            payload = self._read_json(path, {})
            if group_key in payload:
                payload.pop(group_key, None)
                self._write_json(path, payload)
                removed.append(f"{path}:{group_key}")
        return removed

    def get_reread_chance(self, group_id: int) -> float:
        chances = self._read_json(self.settings_root / "reread.json", {})
        return float(self._global_or_legacy_group_value(chances, 0.05))

    def set_reread_chance(self, group_id: int, chance: float) -> None:
        chances = self._read_json(self.settings_root / "reread.json", {})
        chances[GLOBAL_CONFIG_KEY] = chance
        self._write_json(self.settings_root / "reread.json", chances)

    def get_thunder_config(self, group_id: int) -> tuple[float, int, int]:
        configs = self._read_json(self.settings_root / "thunder.json", {})
        raw = self._global_or_legacy_group_value(
            configs,
            {"chance": 0.05, "min_seconds": 5, "max_seconds": 20},
        )
        return float(raw["chance"]), int(raw["min_seconds"]), int(raw["max_seconds"])

    def set_thunder_config(
        self,
        group_id: int,
        chance: float,
        min_seconds: int,
        max_seconds: int,
    ) -> None:
        configs = self._read_json(self.settings_root / "thunder.json", {})
        configs[GLOBAL_CONFIG_KEY] = {
            "chance": chance,
            "min_seconds": min_seconds,
            "max_seconds": max_seconds,
        }
        self._write_json(self.settings_root / "thunder.json", configs)

    def get_lolicon_config(self, group_id: int) -> tuple[bool, bool]:
        configs = self._read_json(self.settings_root / "lolicon.json", {})
        raw = configs.get(str(group_id), {"group_r18": False, "show_image": False})
        return bool(raw["group_r18"]), bool(raw["show_image"])

    def set_lolicon_config(self, group_id: int, group_r18: bool, show_image: bool) -> None:
        configs = self._read_json(self.settings_root / "lolicon.json", {})
        configs[str(group_id)] = {
            "group_r18": group_r18,
            "show_image": show_image,
        }
        self._write_json(self.settings_root / "lolicon.json", configs)

    def _read_json(self, path: Path, default: dict[str, object]) -> dict[str, object]:
        if not path.exists():
            return dict(default)
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, payload: dict[str, object]) -> None:
        # 统一在写入前创建目录，避免首次迁移时依赖手工建文件夹。
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _global_or_legacy_group_value(
        self,
        payload: dict[str, object],
        default: object,
    ) -> object:
        if GLOBAL_CONFIG_KEY in payload:
            return payload[GLOBAL_CONFIG_KEY]
        for key in sorted(payload):
            if str(key).isdigit():
                return payload[key]
        return default


@lru_cache(maxsize=1)
def get_settings_store() -> SettingsStore:
    settings = load_settings()
    return SettingsStore(settings.data_root, settings.author_qq)
