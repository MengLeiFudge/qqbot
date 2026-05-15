from __future__ import annotations

import asyncio

from nonebot import on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent

from qqbot.config import load_settings
from qqbot.services.ai_group_context_store import AiGroupContextStore
from qqbot.services.chat_memory_store import ChatMemoryStore
from qqbot.services.group_message_log_store import GroupMessageLogStore
from qqbot.services.group_nick_store import GroupNickStore, get_group_nick_store
from qqbot.services.message_normalizer import normalize_onebot_event

group_nick_cache_matcher = on_message(priority=1, block=False)


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
    # 群聊记录会写 JSON 和 SQLite；放到线程池，避免积压消息堵住 NoneBot 事件循环。
    await asyncio.to_thread(record_group_cache_event, event)


@group_nick_cache_matcher.handle()
async def handle_group_nick_cache(event: GroupMessageEvent) -> None:
    if not isinstance(event, GroupMessageEvent):
        return
    await handle_group_nick_cache_event(event)
