from __future__ import annotations

from nonebot.adapters.onebot.v11 import Message


class RereadRepeatState:
    def __init__(self) -> None:
        self._groups: dict[str, tuple[str, bool]] = {}

    def should_repeat(self, group_id: int | str, text: str) -> bool:
        normalized = normalize_reread_key(text)
        if not normalized:
            return False
        group_key = str(group_id)
        previous_text, repeated = self._groups.get(group_key, ("", False))
        if previous_text != normalized:
            self._groups[group_key] = (normalized, False)
            return False
        if repeated:
            return False
        self._groups[group_key] = (normalized, True)
        return True


def clamp_reread_percent(percent: float) -> float:
    return min(50, max(percent, 0.01)) / 100


def format_reread_chance(chance: float) -> str:
    return f"{chance:.3%}"


def should_skip_reread_message(message: Message) -> bool:
    return any(segment.type in {"at", "file", "image"} for segment in message)


def normalize_reread_key(text: str) -> str:
    return " ".join(str(text).split()).strip()


def render_reread_message(message: Message) -> Message:
    if all(segment.type == "text" for segment in message):
        return Message(message.extract_plain_text())
    return message
