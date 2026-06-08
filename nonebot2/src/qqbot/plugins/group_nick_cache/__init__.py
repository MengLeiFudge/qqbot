from __future__ import annotations

import asyncio

from nonebot import logger
from nonebot import on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent

from qqbot.config import load_settings
from qqbot.features.ai.group_context_store import AiGroupContextStore
from qqbot.features.ai.chat_memory_store import ChatMemoryStore
from qqbot.features.ai.rightcodes_draw_quota_store import RightCodesDrawQuotaStore
from qqbot.features.group.message_log_store import GroupMessageLogStore
from qqbot.features.group.nick_store import GroupNickStore, get_group_nick_store
from qqbot.services.message_normalizer import normalize_onebot_event

group_nick_cache_matcher = on_message(priority=1, block=False)
_GROUP_CACHE_QUEUE: asyncio.Queue[GroupMessageEvent] | None = None
_GROUP_CACHE_WORKER: asyncio.Task | None = None
_GROUP_CACHE_QUEUE_MAX_SIZE = 1000


def record_group_message_draw_points(event: GroupMessageEvent, store: RightCodesDrawQuotaStore) -> None:
    user_id = str(event.get_user_id() or "").strip()
    self_id = str(getattr(event, "self_id", "") or "").strip()
    if not user_id or user_id == self_id:
        return
    store.record_group_message(user_id)


def record_group_nick_event(event: GroupMessageEvent, store: GroupNickStore) -> None:
    card = (event.sender.card or "").strip()
    nickname = (event.sender.nickname or "").strip()
    if not card and not nickname:
        return
    store.record_group_sender(
        group_id=event.group_id,
        qq=int(event.get_user_id()),
        card=card,
        nickname=nickname,
        updated_at=event.time * 1000,
    )


def record_group_message_context(event: GroupMessageEvent, store: AiGroupContextStore) -> None:
    normalized = normalize_onebot_event(event)
    outline = normalized.outline.strip()
    if not outline:
        return

    card = (event.sender.card or "").strip()
    nickname = (event.sender.nickname or "").strip()
    store.append_message(
        group_id=event.group_id,
        user_id=event.get_user_id(),
        sender_name=card or nickname or event.get_user_id(),
        text=outline,
        timestamp=event.time,
        message_id=getattr(event, "message_id", ""),
    )


def record_group_message_log(event: GroupMessageEvent, store: GroupMessageLogStore) -> None:
    normalized = normalize_onebot_event(event)
    outline = normalized.outline.strip()
    if not outline:
        return

    card = (event.sender.card or "").strip()
    nickname = (event.sender.nickname or "").strip()
    store.append_message(
        group_id=event.group_id,
        direction="incoming",
        user_id=event.get_user_id(),
        sender_name=card or nickname or event.get_user_id(),
        text=outline,
        timestamp=event.time,
        message_id=getattr(event, "message_id", ""),
    )


def record_group_chat_memory(event: GroupMessageEvent, store: ChatMemoryStore) -> None:
    normalized = normalize_onebot_event(event)
    outline = normalized.outline.strip()
    if not outline:
        return

    card = (event.sender.card or "").strip()
    nickname = (event.sender.nickname or "").strip()
    store.append_message(
        group_id=event.group_id,
        message_id=getattr(event, "message_id", ""),
        direction="incoming",
        user_id=event.get_user_id(),
        sender_name=card or nickname or event.get_user_id(),
        text=outline,
        timestamp=event.time,
        has_image=bool(normalized.image_urls),
        has_at=bool(normalized.at_user_ids),
        reply_message_id=normalized.reply.message_id if normalized.reply is not None else "",
        reply_user_id=normalized.reply.user_id if normalized.reply is not None else "",
        reply_outline=normalized.reply.message.outline if normalized.reply is not None else "",
    )


def record_group_cache_event(event: GroupMessageEvent) -> None:
    settings = load_settings()
    record_group_nick_event(event, get_group_nick_store())
    record_group_message_context(
        event,
        AiGroupContextStore(settings.data_root),
    )
    record_group_message_log(
        event,
        GroupMessageLogStore(settings.data_root),
    )
    try:
        record_group_chat_memory(
            event,
            ChatMemoryStore(settings.data_root),
        )
    except Exception:
        pass


async def handle_group_nick_cache_event(event: GroupMessageEvent) -> None:
    settings = load_settings()
    try:
        record_group_message_draw_points(
            event,
            RightCodesDrawQuotaStore(settings.data_root),
        )
    except Exception as exc:
        logger.warning(
            "Group draw point write failed: group_id={}, user_id={}, message_id={}, error={}",
            getattr(event, "group_id", None),
            event.get_user_id() if hasattr(event, "get_user_id") else "",
            getattr(event, "message_id", ""),
            exc,
        )
    # 高频群聊旁路缓存不阻塞消息分发；慢写入交给单 worker 串行落库。
    queue = _ensure_group_cache_queue()
    try:
        queue.put_nowait(event)
    except asyncio.QueueFull:
        logger.warning(
            "Group cache queue full, drop event: group_id={}, user_id={}, message_id={}",
            getattr(event, "group_id", None),
            event.get_user_id() if hasattr(event, "get_user_id") else "",
            getattr(event, "message_id", ""),
        )


def _ensure_group_cache_queue() -> asyncio.Queue[GroupMessageEvent]:
    global _GROUP_CACHE_QUEUE
    global _GROUP_CACHE_WORKER
    if _GROUP_CACHE_QUEUE is None:
        _GROUP_CACHE_QUEUE = asyncio.Queue(maxsize=_GROUP_CACHE_QUEUE_MAX_SIZE)
    if _GROUP_CACHE_WORKER is None or _GROUP_CACHE_WORKER.done():
        _GROUP_CACHE_WORKER = asyncio.create_task(
            _run_group_cache_worker(_GROUP_CACHE_QUEUE)
        )
    return _GROUP_CACHE_QUEUE


async def _run_group_cache_worker(queue: asyncio.Queue[GroupMessageEvent]) -> None:
    while True:
        event = await queue.get()
        try:
            await _record_group_cache_event_in_background(event)
        finally:
            queue.task_done()


async def _record_group_cache_event_in_background(event: GroupMessageEvent) -> None:
    try:
        await asyncio.to_thread(record_group_cache_event, event)
    except Exception as exc:
        logger.warning(
            "Group cache background write failed: group_id={}, user_id={}, message_id={}, error={}",
            getattr(event, "group_id", None),
            event.get_user_id() if hasattr(event, "get_user_id") else "",
            getattr(event, "message_id", ""),
            exc,
        )


@group_nick_cache_matcher.handle()
async def handle_group_nick_cache(event: GroupMessageEvent) -> None:
    if not isinstance(event, GroupMessageEvent):
        return
    await handle_group_nick_cache_event(event)
