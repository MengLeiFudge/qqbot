from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from contextvars import ContextVar
import logging
from pathlib import Path
import time
from typing import Any, Callable
from uuid import uuid4

from nonebot.adapters.onebot.v11 import MessageSegment


MAX_TEXT_MESSAGE_CHARS = 1000
COLLAPSIBLE_TEXT_THRESHOLD_CHARS = 200
# NapCat/QQ forward node text was tested to display up to 4500 chars;
# keep 4000 as a conservative per-node payload limit.
FORWARD_NODE_TEXT_CHARS = 4000
MIN_GROUP_MESSAGE_INTERVAL_SECONDS = 0.5
RECALL_FALLBACK_WINDOW_SECONDS = 3.0
RECALL_FALLBACK_MAX_DEPTH = 8
_PART_PREFIX_RESERVE = 24
_group_locks: dict[str, asyncio.Lock] = {}
_group_last_sent_at: dict[str, float] = {}
_group_message_interval_already_waited: ContextVar[bool] = ContextVar(
    "group_message_interval_already_waited",
    default=False,
)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecallFallbackPayload:
    group_id: int | str
    text: str
    message: Any
    mode: str
    title: str = "棉花糖整理的长消息"
    depth: int = 0
    fragment_limit: int = 80


@dataclass
class _TrackedRecallMessage:
    bot: Any
    payload: RecallFallbackPayload
    sent_at: float
    expire_task: asyncio.Task[None] | None = None


_tracked_recall_messages: dict[str, _TrackedRecallMessage] = {}


def split_text_message(text: str, *, limit: int = MAX_TEXT_MESSAGE_CHARS) -> list[str]:
    chunks = split_text_message_body(text, limit=limit)
    total = len(chunks)
    if total <= 1:
        return chunks
    return [f"（{index}/{total}）\n{chunk}" for index, chunk in enumerate(chunks, start=1)]


def split_text_message_body(text: str, *, limit: int = MAX_TEXT_MESSAGE_CHARS) -> list[str]:
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

    return chunks


async def send_split_text(
    matcher: Any,
    message: Any,
    *,
    group_id: int | str | None = None,
    bot: Any | None = None,
) -> None:
    if bot is not None and group_id is not None:
        await call_split_text_api(bot, "send_group_msg", group_id=group_id, message=message)
        return
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
    if bot is not None and group_id is not None:
        if isinstance(message, str):
            await call_collapsible_text_api(
                bot,
                "send_group_msg",
                group_id=group_id,
                message=message,
                title=title,
            )
        else:
            await call_group_message_api(
                bot,
                group_id=group_id,
                message=message,
                text=str(message),
                mode="direct",
                title=title,
            )
        await matcher.finish()
        return

    if not isinstance(message, str):
        await wait_for_group_message_interval(group_id)
        await matcher.finish(message)
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
    message: Any,
    group_interval_sleep: Callable[[float], Any] | None = None,
    **data: object,
) -> None:
    if api == "send_group_msg" and data.get("group_id") is not None and not isinstance(message, str):
        await call_group_message_api(
            bot,
            group_id=data["group_id"],
            message=message,
            text=str(message),
            mode="direct",
            group_interval_sleep=group_interval_sleep,
        )
        return
    for chunk in split_text_message(message):
        if api == "send_group_msg":
            await call_group_message_api(
                bot,
                group_id=data["group_id"],
                message=chunk,
                text=chunk,
                mode="direct",
                group_interval_sleep=group_interval_sleep,
            )
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
            result = await bot.call_api(
                "send_group_forward_msg",
                group_id=group_id,
                messages=_build_forward_nodes(bot, message, title=title),
            )
            _track_recall_fallback(
                bot,
                result,
                RecallFallbackPayload(
                    group_id=group_id,
                    text=str(message),
                    message=str(message),
                    mode="collapsible",
                    title=title,
                ),
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


async def call_record_api(
    bot: Any,
    output_root: Path,
    *,
    audio_bytes: bytes,
    group_id: int | str | None = None,
    user_id: int | str | None = None,
) -> Path:
    audio_root = Path(output_root) / "ai" / "tts"
    audio_root.mkdir(parents=True, exist_ok=True)
    audio_path = audio_root / f"{int(time.time() * 1000)}-{uuid4().hex}.wav"
    audio_path.write_bytes(audio_bytes)
    message = MessageSegment.record(audio_path.resolve().as_uri())
    if group_id is not None:
        await wait_for_group_message_interval(group_id)
        await bot.call_api("send_group_msg", group_id=group_id, message=message)
        return audio_path
    if user_id is not None:
        await bot.call_api("send_private_msg", user_id=user_id, message=message)
        return audio_path
    raise ValueError("call_record_api requires group_id or user_id")


async def call_group_message_api(
    bot: Any,
    *,
    group_id: int | str,
    message: Any,
    text: str,
    mode: str,
    title: str = "棉花糖整理的长消息",
    group_interval_sleep: Callable[[float], Any] | None = None,
) -> None:
    await wait_for_group_message_interval(
        group_id,
        sleep=group_interval_sleep or asyncio.sleep,
    )
    token = _group_message_interval_already_waited.set(True)
    try:
        result = await bot.call_api("send_group_msg", group_id=group_id, message=message)
        _track_recall_fallback(
            bot,
            result,
            RecallFallbackPayload(
                group_id=group_id,
                text=str(text),
                message=message,
                mode=mode,
                title=title,
            ),
        )
    finally:
        _group_message_interval_already_waited.reset(token)


async def handle_group_message_recall(
    bot: Any,
    *,
    group_id: int | str,
    message_id: int | str,
    user_id: int | str | None = None,
    self_id: int | str | None = None,
    now: Callable[[], float] = time.monotonic,
) -> bool:
    if self_id is not None and user_id is not None and str(user_id) != str(self_id):
        return False
    key = _normalize_message_id(message_id)
    if key is None:
        return False
    tracked = _tracked_recall_messages.pop(key, None)
    if tracked is None:
        return False
    if tracked.expire_task is not None:
        tracked.expire_task.cancel()
    if now() - tracked.sent_at > RECALL_FALLBACK_WINDOW_SECONDS:
        return False
    resend_bot = tracked.bot or bot
    asyncio.create_task(_resend_recalled_payload(resend_bot, tracked.payload))
    return True


def reset_recall_fallback_state() -> None:
    for tracked in _tracked_recall_messages.values():
        if tracked.expire_task is not None:
            tracked.expire_task.cancel()
    _tracked_recall_messages.clear()


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


async def _resend_recalled_payload(bot: Any, payload: RecallFallbackPayload) -> None:
    if payload.depth >= RECALL_FALLBACK_MAX_DEPTH:
        logger.warning(
            "Stop recall fallback after max depth: group_id={}, mode={}, text_len={}",
            payload.group_id,
            payload.mode,
            len(payload.text),
        )
        return
    next_payload = _next_recall_fallback_payload(payload)
    if next_payload is None:
        return
    if next_payload.mode == "direct":
        for chunk in split_text_message(next_payload.text):
            await call_group_message_api(
                bot,
                group_id=next_payload.group_id,
                message=chunk,
                text=chunk,
                mode="direct",
                title=next_payload.title,
            )
        return
    if next_payload.mode == "sentence":
        for chunk in split_sentence_message(next_payload.text):
            await call_group_message_api(
                bot,
                group_id=next_payload.group_id,
                message=chunk,
                text=chunk,
                mode="sentence",
                title=next_payload.title,
            )
        return
    if next_payload.mode == "fragment":
        for chunk in split_text_message_body(next_payload.text, limit=next_payload.fragment_limit):
            await call_group_message_api(
                bot,
                group_id=next_payload.group_id,
                message=chunk,
                text=chunk,
                mode="fragment",
                title=next_payload.title,
            )


def _next_recall_fallback_payload(
    payload: RecallFallbackPayload,
) -> RecallFallbackPayload | None:
    if not payload.text:
        return None
    if payload.mode == "collapsible":
        return replace(payload, mode="direct", depth=payload.depth + 1)
    if payload.mode == "direct":
        return replace(payload, mode="sentence", depth=payload.depth + 1)
    if payload.mode == "sentence":
        return replace(payload, mode="fragment", depth=payload.depth + 1, fragment_limit=80)
    if payload.mode == "fragment":
        return replace(
            payload,
            mode="fragment",
            depth=payload.depth + 1,
            fragment_limit=max(1, payload.fragment_limit // 2),
        )
    return None


def split_sentence_message(text: str) -> list[str]:
    text = str(text)
    parts: list[str] = []
    buffer: list[str] = []
    index = 0
    while index < len(text):
        if text.startswith("……", index):
            buffer.append("……")
            _append_sentence_part(parts, buffer)
            index += 2
            continue
        char = text[index]
        buffer.append(char)
        if char in {"。", "？", "?", "！", "!", "\n"}:
            _append_sentence_part(parts, buffer)
        index += 1
    _append_sentence_part(parts, buffer)
    if not parts:
        return [text] if text else []
    result: list[str] = []
    for part in parts:
        result.extend(split_text_message_body(part, limit=MAX_TEXT_MESSAGE_CHARS))
    return result


def _append_sentence_part(parts: list[str], buffer: list[str]) -> None:
    part = "".join(buffer).strip()
    buffer.clear()
    if part:
        parts.append(part)


def _track_recall_fallback(
    bot: Any,
    result: Any,
    payload: RecallFallbackPayload,
    *,
    now: Callable[[], float] = time.monotonic,
) -> None:
    message_id = _extract_message_id(result)
    if message_id is None:
        return
    key = _normalize_message_id(message_id)
    if key is None:
        return
    task = asyncio.create_task(_expire_recall_fallback(key, RECALL_FALLBACK_WINDOW_SECONDS))
    _tracked_recall_messages[key] = _TrackedRecallMessage(
        bot=bot,
        payload=payload,
        sent_at=now(),
        expire_task=task,
    )


async def _expire_recall_fallback(message_id: str, delay: float) -> None:
    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        return
    _tracked_recall_messages.pop(message_id, None)


def _extract_message_id(result: Any) -> str | None:
    if isinstance(result, dict):
        raw = result.get("message_id")
    else:
        raw = getattr(result, "message_id", None)
    return _normalize_message_id(raw)


def _normalize_message_id(message_id: Any) -> str | None:
    if message_id is None:
        return None
    text = str(message_id).strip()
    return text or None


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
        for chunk in split_text_message_body(message, limit=FORWARD_NODE_TEXT_CHARS)
    ]
