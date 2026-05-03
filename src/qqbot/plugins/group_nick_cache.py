from __future__ import annotations

from nonebot import on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent

from qqbot.config import load_settings
from qqbot.services.ai_group_context_store import AiGroupContextStore
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


@group_nick_cache_matcher.handle()
async def handle_group_nick_cache(event: GroupMessageEvent) -> None:
    if not isinstance(event, GroupMessageEvent):
        return
    settings = load_settings()
    record_group_nick_event(event, get_group_nick_store())
    record_group_message_context(
        event,
        AiGroupContextStore(settings.data_root),
    )
