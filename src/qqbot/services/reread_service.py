from __future__ import annotations

from nonebot.adapters.onebot.v11 import Message


def clamp_reread_percent(percent: float) -> float:
    return min(50, max(percent, 0.01)) / 100


def format_reread_chance(chance: float) -> str:
    return f"{chance:.3%}"


def should_skip_reread_message(message: Message) -> bool:
    return any(segment.type in {"at", "file", "image"} for segment in message)


def render_reread_message(message: Message) -> Message:
    if all(segment.type == "text" for segment in message):
        return Message(message.extract_plain_text())
    return message
