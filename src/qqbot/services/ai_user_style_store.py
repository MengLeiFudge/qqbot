from __future__ import annotations

import json
from pathlib import Path


class AiUserStyleStore:
    def __init__(self, data_root: Path) -> None:
        self.file_path = Path(data_root) / "ai" / "user_style.json"

    def add_preference(self, user_id: int | str, preference: str) -> None:
        self.add_user_preference(user_id, preference)

    def add_user_preference(self, user_id: int | str, preference: str) -> None:
        self._add_scoped_preference(f"user:{user_id}", preference)

    def add_group_preference(self, group_id: int | str, preference: str) -> None:
        self._add_scoped_preference(f"group:{group_id}", preference)

    def _add_scoped_preference(self, key: str, preference: str) -> None:
        normalized = preference.strip()
        if not normalized:
            return
        payload = self._read()
        preferences = list(payload.get(key, []))
        if normalized not in preferences:
            preferences.append(normalized)
        payload[key] = preferences[-20:]
        self._write(payload)

    def get_preferences(self, user_id: int | str) -> tuple[str, ...]:
        return self.get_user_preferences(user_id)

    def get_user_preferences(self, user_id: int | str) -> tuple[str, ...]:
        scoped = self._get_scoped_preferences(f"user:{user_id}")
        legacy = self._get_scoped_preferences(str(user_id))
        return tuple(dict.fromkeys((*legacy, *scoped)))

    def get_group_preferences(self, group_id: int | str) -> tuple[str, ...]:
        return self._get_scoped_preferences(f"group:{group_id}")

    def _get_scoped_preferences(self, key: str) -> tuple[str, ...]:
        payload = self._read()
        raw = payload.get(key, [])
        if not isinstance(raw, list):
            return ()
        return tuple(str(item).strip() for item in raw if str(item).strip())

    def build_context(self, user_id: int | str, group_id: int | str | None = None) -> str:
        group_preferences = self.get_group_preferences(group_id) if group_id is not None else ()
        user_preferences = self.get_user_preferences(user_id)
        if group_id is None and user_preferences:
            return "当前用户的回复偏好：" + "；".join(user_preferences)
        lines = []
        if group_preferences:
            lines.append("本群回复偏好：" + "；".join(group_preferences))
        if user_preferences:
            lines.append("当前用户回复偏好：" + "；".join(user_preferences))
        if not lines:
            return ""
        return "提示词偏好层：\n" + "\n".join(lines)

    def _read(self) -> dict[str, list[str]]:
        if not self.file_path.exists():
            return {}
        raw = json.loads(self.file_path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}

    def _write(self, payload: dict[str, list[str]]) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
