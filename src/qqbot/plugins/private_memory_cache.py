from __future__ import annotations

from nonebot import on_message
from nonebot.adapters.onebot.v11 import PrivateMessageEvent

from qqbot.config import load_settings
from qqbot.services.chat_memory_store import ChatMemoryStore, build_user_actor_id
from qqbot.services.message_normalizer import normalize_onebot_event

private_memory_cache_matcher = on_message(priority=1, block=False)


def record_private_chat_memory(event: PrivateMessageEvent, store: ChatMemoryStore) -> None:
    normalized = normalize_onebot_event(event)
    outline = normalized.outline.strip()
    if not outline:
        return

    user_id = event.get_user_id()
    store.append_message(
        group_id=f"private:{user_id}",
        message_id=getattr(event, "message_id", ""),
        direction="incoming",
        user_id=user_id,
        sender_name=user_id,
        text=outline,
        timestamp=event.time,
        space_id=f"qq:private:{user_id}",
        actor_id=build_user_actor_id(user_id),
        visibility="private",
        memory_type="raw_message",
        has_image=bool(normalized.image_urls),
        has_at=bool(normalized.at_user_ids),
        reply_message_id=normalized.reply.message_id if normalized.reply is not None else "",
        reply_user_id=normalized.reply.user_id if normalized.reply is not None else "",
        reply_outline=normalized.reply.message.outline if normalized.reply is not None else "",
    )


@private_memory_cache_matcher.handle()
async def handle_private_memory_cache(event: PrivateMessageEvent) -> None:
    if not isinstance(event, PrivateMessageEvent):
        return
    try:
        record_private_chat_memory(event, ChatMemoryStore(load_settings().data_root))
    except Exception:
        pass
