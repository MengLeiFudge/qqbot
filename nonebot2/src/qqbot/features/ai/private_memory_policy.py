from __future__ import annotations

import re

from qqbot.services.message_normalizer import NormalizedMessage


def should_record_private_chat_memory(normalized_message: NormalizedMessage) -> bool:
    return False


def should_include_private_memory_context(normalized_message: NormalizedMessage) -> bool:
    return looks_like_private_memory_query(normalized_message)


def looks_like_private_memory_query(normalized_message: NormalizedMessage) -> bool:
    compact = _compact_private_text(normalized_message)
    if not compact:
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
    return any(marker in compact for marker in memory_markers)


def _compact_private_text(normalized_message: NormalizedMessage) -> str:
    return re.sub(r"\s+", "", (normalized_message.text or normalized_message.outline).strip())
