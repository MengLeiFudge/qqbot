from __future__ import annotations

import asyncio
from contextvars import ContextVar
import time
from typing import Any, Callable


MAX_TEXT_MESSAGE_CHARS = 1000
COLLAPSIBLE_TEXT_THRESHOLD_CHARS = 200
FORWARD_NODE_TEXT_CHARS = 1200
MIN_GROUP_MESSAGE_INTERVAL_SECONDS = 0.5
_PART_PREFIX_RESERVE = 24
_group_locks: dict[str, asyncio.Lock] = {}
_group_last_sent_at: dict[str, float] = {}
_group_message_interval_already_waited: ContextVar[bool] = ContextVar(
    "group_message_interval_already_waited",
    default=False,
)


def split_text_message(text: str, *, limit: int = MAX_TEXT_MESSAGE_CHARS) -> list[str]:
    text = str(text)
    if len(text) <= limit:
        return [text]

    body_limit = max(1, limit - _PART_PREFIX_RESERVE)
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= body_limit:
            chunks.append(remaining)
            break

        cut = _find_split_index(remaining, body_limit)
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()

    total = len(chunks)
    if total <= 1:
        return chunks
    return [f"（{index}/{total}）\n{chunk}" for index, chunk in enumerate(chunks, start=1)]


async def send_split_text(
    matcher: Any,
    message: Any,
    *,
    group_id: int | str | None = None,
) -> None:
    if not isinstance(message, str):
        await wait_for_group_message_interval(group_id)
        await matcher.send(message)
        return
    for chunk in split_text_message(message):
        await wait_for_group_message_interval(group_id)
        await matcher.send(chunk)


async def finish_split_text(
    matcher: Any,
    message: Any,
    *,
    group_id: int | str | None = None,
    bot: Any | None = None,
    title: str = "棉花糖整理的长消息",
) -> None:
    if not isinstance(message, str):
        await wait_for_group_message_interval(group_id)
        await matcher.finish(message)
        return

    if bot is not None and group_id is not None and len(message) > COLLAPSIBLE_TEXT_THRESHOLD_CHARS:
        await call_collapsible_text_api(
            bot,
            "send_group_msg",
            group_id=group_id,
            message=message,
            title=title,
        )
        await matcher.finish()
        return

    chunks = split_text_message(message)
    for chunk in chunks[:-1]:
        await wait_for_group_message_interval(group_id)
        await matcher.send(chunk)
    await wait_for_group_message_interval(group_id)
    await matcher.finish(chunks[-1])


async def call_split_text_api(
    bot: Any,
    api: str,
    *,
    message: str,
    group_interval_sleep: Callable[[float], Any] | None = None,
    **data: object,
) -> None:
    for chunk in split_text_message(message):
        if api == "send_group_msg":
            await wait_for_group_message_interval(
                data.get("group_id"),
                sleep=group_interval_sleep or asyncio.sleep,
            )
            token = _group_message_interval_already_waited.set(True)
            try:
                await bot.call_api(api, **data, message=chunk)
            finally:
                _group_message_interval_already_waited.reset(token)
            continue
        await bot.call_api(api, **data, message=chunk)


async def call_collapsible_text_api(
    bot: Any,
    api: str,
    *,
    message: str,
    title: str = "棉花糖整理的长消息",
    group_interval_sleep: Callable[[float], Any] | None = None,
    **data: object,
) -> None:
    if api != "send_group_msg" or len(str(message)) <= COLLAPSIBLE_TEXT_THRESHOLD_CHARS:
        await call_split_text_api(
            bot,
            api,
            message=message,
            group_interval_sleep=group_interval_sleep,
            **data,
        )
        return

    group_id = data.get("group_id")
    try:
        await wait_for_group_message_interval(
            group_id,
            sleep=group_interval_sleep or asyncio.sleep,
        )
        token = _group_message_interval_already_waited.set(True)
        try:
            await bot.call_api(
                "send_group_forward_msg",
                group_id=group_id,
                messages=_build_forward_nodes(bot, message, title=title),
            )
        finally:
            _group_message_interval_already_waited.reset(token)
    except Exception:
        await call_split_text_api(
            bot,
            api,
            message=message,
            group_interval_sleep=group_interval_sleep,
            **data,
        )


async def wait_for_group_message_interval(
    group_id: int | str | object | None,
    *,
    now=time.monotonic,
    sleep=asyncio.sleep,
) -> None:
    if group_id is None:
        return
    key = str(group_id).strip()
    if not key:
        return

    lock = _group_locks.setdefault(key, asyncio.Lock())
    async with lock:
        current = now()
        last_sent_at = _group_last_sent_at.get(key)
        if last_sent_at is not None:
            delay = MIN_GROUP_MESSAGE_INTERVAL_SECONDS - (current - last_sent_at)
            if delay > 0:
                await sleep(delay)
                current = now()
        _group_last_sent_at[key] = current


def reset_group_message_interval_state() -> None:
    _group_locks.clear()
    _group_last_sent_at.clear()


def has_waited_group_message_interval() -> bool:
    return _group_message_interval_already_waited.get()


def _find_split_index(text: str, limit: int) -> int:
    window = text[:limit]
    for separator in ("\n\n", "\n", "。", "！", "？", "；", "，", " "):
        index = window.rfind(separator)
        if index >= max(1, limit // 2):
            return index + len(separator)
    return limit


def _build_forward_nodes(bot: Any, message: str, *, title: str) -> list[dict[str, object]]:
    uin = str(getattr(bot, "self_id", "") or "10000")
    name = title.strip() or "棉花糖整理的长消息"
    return [
        {
            "type": "node",
            "data": {
                "name": name,
                "uin": uin,
                "content": chunk,
            },
        }
        for chunk in split_text_message(message, limit=FORWARD_NODE_TEXT_CHARS)
    ]
