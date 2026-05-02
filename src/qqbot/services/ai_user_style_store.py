from __future__ import annotations

import json
from pathlib import Path


class AiUserStyleStore:
    def __init__(self, data_root: Path) -> None:
        self.file_path = Path(data_root) / "ai" / "user_style.json"

    def add_preference(self, user_id: int | str, preference: str) -> None:
        normalized = preference.strip()
        if not normalized:
            return
        payload = self._read()
        key = str(user_id)
        preferences = list(payload.get(key, []))
        if normalized not in preferences:
            preferences.append(normalized)
        payload[key] = preferences[-20:]
        self._write(payload)

    def get_preferences(self, user_id: int | str) -> tuple[str, ...]:
        payload = self._read()
        raw = payload.get(str(user_id), [])
        if not isinstance(raw, list):
            return ()
        return tuple(str(item).strip() for item in raw if str(item).strip())

    def build_context(self, user_id: int | str) -> str:
        preferences = self.get_preferences(user_id)
        if not preferences:
            return ""
        return "当前用户的回复偏好：" + "；".join(preferences)

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
