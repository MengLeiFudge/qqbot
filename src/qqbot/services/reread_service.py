from __future__ import annotations

from nonebot.adapters.onebot.v11 import Message


def clamp_reread_percent(percent: float) -> float:
    return min(50, max(percent, 0.01)) / 100


def format_reread_chance(chance: float) -> str:
    return f"{chance:.3%}"


def render_reread_message(message: Message, reverse_text: bool) -> Message:
    # 先保持与旧实现一致：纯文本有机会倒序，混合消息按原样发送，文件消息由插件层提前拦截。
    if all(segment.type == "text" for segment in message):
        text = message.extract_plain_text()
        return Message(text[::-1] if reverse_text else text)
    return message
