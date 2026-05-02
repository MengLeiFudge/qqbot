from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from qqbot.config import load_settings
from qqbot.services.feature_catalog import FeatureDefinition
from qqbot.services.plugin_registry import (
    get_plugin_spec_by_feature_index,
    list_visible_plugin_specs,
)


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

    def list_bot_admins(self) -> dict[str, bool]:
        return self._read_json(self.settings_root / "bot_admin.json", {})

    def get_group_feature_state(self, group_id: int, feature: FeatureDefinition) -> bool:
        spec = get_plugin_spec_by_feature_index(feature.index)
        if spec is not None and not self.get_plugin_enabled(spec.id):
            return False

        states = self._read_json(self.func_state_root / f"{group_id}.json", {})
        if feature.name in states:
            return bool(states[feature.name])
        for legacy_name in feature.legacy_names:
            if legacy_name in states:
                return bool(states[legacy_name])
        return False

    def set_group_feature_state(
        self,
        group_id: int,
        feature: FeatureDefinition,
        is_open: bool,
    ) -> None:
        states = self._read_json(self.func_state_root / f"{group_id}.json", {})
        states[feature.name] = is_open
        for legacy_name in feature.legacy_names:
            states.pop(legacy_name, None)
        self._write_json(self.func_state_root / f"{group_id}.json", states)

    def get_group_feature_states(self, group_id: int) -> dict[str, bool]:
        return self._read_json(self.func_state_root / f"{group_id}.json", {})

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

    def get_reread_chance(self, group_id: int) -> float:
        chances = self._read_json(self.settings_root / "reread.json", {})
        return float(chances.get(str(group_id), 0.05))

    def set_reread_chance(self, group_id: int, chance: float) -> None:
        chances = self._read_json(self.settings_root / "reread.json", {})
        chances[str(group_id)] = chance
        self._write_json(self.settings_root / "reread.json", chances)

    def get_thunder_config(self, group_id: int) -> tuple[float, int, int]:
        configs = self._read_json(self.settings_root / "thunder.json", {})
        raw = configs.get(str(group_id), {"chance": 0.05, "min_seconds": 5, "max_seconds": 20})
        return float(raw["chance"]), int(raw["min_seconds"]), int(raw["max_seconds"])

    def set_thunder_config(
        self,
        group_id: int,
        chance: float,
        min_seconds: int,
        max_seconds: int,
    ) -> None:
        configs = self._read_json(self.settings_root / "thunder.json", {})
        configs[str(group_id)] = {
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


@lru_cache(maxsize=1)
def get_settings_store() -> SettingsStore:
    settings = load_settings()
    return SettingsStore(settings.data_root, settings.author_qq)
