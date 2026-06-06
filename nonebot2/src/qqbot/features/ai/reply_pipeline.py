from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from typing import Any

from nonebot.adapters.onebot.v11 import Message, MessageSegment

from qqbot.config import RuntimeSettings
from qqbot.features.ai.group_context_store import AiGroupContextStore
from qqbot.services.message_delivery import finish_split_text, send_split_text

AI_CONTINUOUS_REPLY_CHARS_PER_SECOND = 18.0
AI_CONTINUOUS_REPLY_MIN_DELAY_SECONDS = 1.2
AI_CONTINUOUS_REPLY_MAX_DELAY_SECONDS = 3.0
AI_RECENT_REPLY_NO_QUOTE_MESSAGES = 5
LOW_INFORMATION_REPLY_OPENERS = {
    "哦哦",
    "哦哦原来是这样",
    "哦哦原来是这个",
    "原来是这样",
    "原来是这个",
    "明白了",
    "懂了",
}


def build_ai_reply_message(
    text: str,
    *,
    group_id: int | str | None,
    message_id: int | str | None,
    user_id: int | str,
    quote: bool = True,
) -> str | Message:
    if group_id is None or not str(user_id).isdigit():
        return text
    if not quote:
        return text

    message = Message()
    if message_id not in {None, ""} and str(message_id).isdigit():
        message += MessageSegment.reply(int(message_id))
    message += MessageSegment.at(int(user_id))
    message += MessageSegment.text(f" {text}")
    return message


def build_ai_reply_notice_message(
    *,
    group_id: int | str | None,
    message_id: int | str | None,
    user_id: int | str,
    quote: bool = True,
) -> str | Message:
    return build_ai_reply_message(
        "棉花糖整理了一段较长回复，稍后直接发出。",
        group_id=group_id,
        message_id=message_id,
        user_id=user_id,
        quote=quote,
    )


async def finish_continuous_group_ai_reply(
    text: str,
    *,
    group_id: int | str,
    message_id: int | str | None,
    user_id: int | str,
    quote: bool = True,
    bot: Any | None = None,
    matcher: Any,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    send_func: Callable[..., Awaitable[None]] = send_split_text,
    finish_func: Callable[..., Awaitable[None]] = finish_split_text,
) -> None:
    parts = split_continuous_ai_reply_text(text)
    messages: list[str | Message] = []
    for index, part in enumerate(parts):
        if index == 0:
            messages.append(
                build_ai_reply_message(
                    part,
                    group_id=group_id,
                    message_id=message_id,
                    user_id=user_id,
                    quote=quote,
                )
            )
            continue
        messages.append(part)

    for index, message in enumerate(messages[:-1]):
        if index > 0:
            await sleep(calculate_continuous_reply_delay_seconds(parts[index]))
        await send_func(matcher, message, group_id=group_id, bot=bot)
    if len(messages) > 1:
        await sleep(calculate_continuous_reply_delay_seconds(parts[-1]))
    await finish_func(matcher, messages[-1], group_id=group_id, bot=bot)


def calculate_continuous_reply_delay_seconds(text: str) -> float:
    if not str(text):
        return 0.0
    return min(
        AI_CONTINUOUS_REPLY_MAX_DELAY_SECONDS,
        max(
            AI_CONTINUOUS_REPLY_MIN_DELAY_SECONDS,
            len(str(text)) / AI_CONTINUOUS_REPLY_CHARS_PER_SECOND,
        ),
    )


def split_continuous_ai_reply_text(text: str) -> list[str]:
    normalized = "\n".join(part.strip() for part in str(text).splitlines() if part.strip())
    parts = _split_chatty_reply_sentences(normalized)
    parts = _drop_low_information_reply_opener(parts)
    if len(parts) > 5:
        return [normalized]
    return parts or [normalized]


def should_quote_group_ai_reply(
    settings: RuntimeSettings,
    *,
    group_id: int | str | None,
    message_id: int | str | None,
    event_time: object | None = None,
    recent_limit: int = AI_RECENT_REPLY_NO_QUOTE_MESSAGES,
    context_store: AiGroupContextStore | None = None,
) -> bool:
    if group_id is None:
        return False
    target_message_id = str(message_id or "").strip()
    if not target_message_id:
        return False
    store = context_store or AiGroupContextStore(settings.data_root)
    recent_records = store.load_messages(group_id, limit=max(1, recent_limit))
    if any(record.message_id == target_message_id for record in recent_records):
        return False
    if event_time is not None and recent_records:
        try:
            if max(record.timestamp for record in recent_records) <= int(float(event_time)):
                return False
        except (TypeError, ValueError):
            pass
    return True


def _split_chatty_reply_sentences(text: str) -> list[str]:
    parts: list[str] = []
    buffer: list[str] = []
    index = 0
    while index < len(text):
        if text.startswith("……", index):
            buffer.append("……")
            _append_chatty_part(parts, buffer)
            index += 2
            continue
        char = text[index]
        if char in {"。", "\n"}:
            _append_chatty_part(parts, buffer)
        elif char in {"？", "?", "！", "!"}:
            buffer.append(char)
            _append_chatty_part(parts, buffer)
        else:
            buffer.append(char)
        index += 1
    _append_chatty_part(parts, buffer)
    return parts


def _append_chatty_part(parts: list[str], buffer: list[str]) -> None:
    part = "".join(buffer).strip()
    if part:
        parts.append(part)
    buffer.clear()


def _drop_low_information_reply_opener(parts: list[str]) -> list[str]:
    if len(parts) <= 1:
        return parts
    first = re.sub(r"[，,。.!！?？~～\s]+", "", parts[0]).strip()
    if first in LOW_INFORMATION_REPLY_OPENERS:
        return parts[1:]
    return parts
