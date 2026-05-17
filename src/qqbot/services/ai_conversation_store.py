from __future__ import annotations

from pathlib import Path
import json

from qqbot.services.ai_gateway import AiMessage, is_safety_rejection_text
from qqbot.services.ai_output_style import sanitize_ai_output_text


class AiConversationStore:
    def __init__(self, data_root: Path, max_messages: int = 12) -> None:
        self.root = Path(data_root) / "ai" / "conversations"
        self.max_messages = max(2, max_messages)

    def private_key(self, user_id: str, profile: str, scope: str) -> str:
        return ":".join(("private", user_id, profile, scope))

    def group_user_key(
        self,
        group_id: str,
        user_id: str,
        profile: str,
        scope: str,
    ) -> str:
        return ":".join(("group_user", group_id, user_id, profile, scope))

    def load_messages(self, key: str) -> tuple[AiMessage, ...]:
        path = self._path_for_key(key)
        if not path.exists():
            return ()
        raw_messages = json.loads(path.read_text(encoding="utf-8"))
        messages = []
        for raw in raw_messages:
            if not isinstance(raw, dict):
                continue
            role = str(raw.get("role", ""))
            content = str(raw.get("content", ""))
            if role == "assistant":
                content = sanitize_ai_output_text(content)
            if is_safety_rejection_text(content):
                continue
            if role in {"user", "assistant"} and content:
                messages.append(AiMessage(role=role, content=content))
        return tuple(messages[-self.max_messages :])

    def append_turn(self, key: str, user_text: str, assistant_text: str) -> tuple[AiMessage, ...]:
        assistant_text = sanitize_ai_output_text(assistant_text)
        if is_safety_rejection_text(assistant_text):
            return self.load_messages(key)

        messages = list(self.load_messages(key))
        messages.append(AiMessage(role="user", content=user_text))
        messages.append(AiMessage(role="assistant", content=assistant_text))
        bounded = messages[-self.max_messages :]
        self._write_messages(key, bounded)
        return tuple(bounded)

    def _write_messages(self, key: str, messages: list[AiMessage]) -> None:
        path = self._path_for_key(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                [{"role": message.role, "content": message.content} for message in messages],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _path_for_key(self, key: str) -> Path:
        filename = key.replace(":", "__") + ".json"
        return self.root / filename
