from __future__ import annotations

import re

from qqbot.services.message_normalizer import NormalizedMessage


def should_record_private_chat_memory(normalized_message: NormalizedMessage) -> bool:
    return not is_private_lightweight_chat(normalized_message)


def should_include_private_memory_context(normalized_message: NormalizedMessage) -> bool:
    return not is_private_lightweight_chat(normalized_message)


def is_private_lightweight_chat(normalized_message: NormalizedMessage) -> bool:
    if normalized_message.image_urls or normalized_message.reply is not None:
        return False
    compact = re.sub(r"\s+", "", (normalized_message.text or normalized_message.outline).strip())
    if not compact or len(compact) > 24:
        return False
    memory_markers = (
        "记得",
        "记不记得",
        "还记",
        "之前",
        "以前",
        "上次",
        "刚才",
        "刚刚",
        "说过",
        "提过",
        "聊过",
        "私聊",
        "我是谁",
        "你认识",
        "你知道",
    )
    if any(marker in compact for marker in memory_markers):
        return False
    lightweight_markers = (
        "在吗",
        "在嘛",
        "在不在",
        "人呢",
        "说句话",
        "说话",
        "看看",
        "醒着吗",
        "醒了吗",
        "睡了吗",
        "睡了没",
        "太慢",
        "慢了",
        "笨笨",
        "你好",
        "早",
        "晚安",
        "摸摸",
    )
    return any(marker in compact for marker in lightweight_markers)
