from __future__ import annotations

import asyncio
from datetime import datetime

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import Bot, PrivateMessageEvent

from qqbot.config import load_settings
from qqbot.services.ai_conversation_store import AiConversationStore
from qqbot.services.ai_gateway import AiRequest
from qqbot.services.ai_group_context_store import AiGroupContextStore
from qqbot.services.ai_profile_registry import load_ai_profiles
from qqbot.services.ai_runtime import build_ai_gateway, get_current_ai_profile_name
from qqbot.services.ai_user_style_store import AiUserStyleStore
from qqbot.services.chat_memory_store import ChatMemoryStore, build_user_actor_id
from qqbot.services.message_delivery import call_split_text_api
from qqbot.services.message_normalizer import normalize_onebot_event
from qqbot.services.offline_message_gate import is_before_onebot_connect
from qqbot.services.settings_store import get_settings_store

OFFLINE_PRIVATE_REPLAY_DELAY_SECONDS = 3.0
OFFLINE_PRIVATE_PENDING_USERS: set[str] = set()
_OFFLINE_PRIVATE_REPLAYED_USERS: set[str] = set()
_OFFLINE_PRIVATE_PENDING_MESSAGE_IDS: dict[str, list[str]] = {}
_OFFLINE_PRIVATE_REPLAY_TASKS: dict[str, asyncio.Task] = {}

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


def record_private_memory_cache_event(event: PrivateMessageEvent) -> None:
    try:
        record_private_chat_memory(event, ChatMemoryStore(load_settings().data_root))
    except Exception:
        pass


async def handle_private_memory_cache_event(
    event: PrivateMessageEvent,
    bot: Bot | None = None,
) -> None:
    # 私聊长期记忆写入 SQLite；放到线程池，避免影响命令和管理端响应。
    await asyncio.to_thread(record_private_memory_cache_event, event)
    if bot is not None and is_before_onebot_connect(getattr(event, "time", None)):
        user_id = event.get_user_id()
        if user_id in _OFFLINE_PRIVATE_REPLAYED_USERS:
            return
        OFFLINE_PRIVATE_PENDING_USERS.add(user_id)
        message_id = str(getattr(event, "message_id", "") or "").strip()
        if message_id:
            _OFFLINE_PRIVATE_PENDING_MESSAGE_IDS.setdefault(user_id, []).append(message_id)
        schedule_offline_private_ai_replay(bot, user_id)


@private_memory_cache_matcher.handle()
async def handle_private_memory_cache(bot: Bot, event: PrivateMessageEvent) -> None:
    if not isinstance(event, PrivateMessageEvent):
        return
    await handle_private_memory_cache_event(event, bot=bot)


def schedule_offline_private_ai_replay(
    bot: Bot,
    user_id: str,
    *,
    delay_seconds: float | None = None,
) -> None:
    delay = OFFLINE_PRIVATE_REPLAY_DELAY_SECONDS if delay_seconds is None else delay_seconds
    existing = _OFFLINE_PRIVATE_REPLAY_TASKS.get(user_id)
    if existing is not None and not existing.done():
        existing.cancel()
    _OFFLINE_PRIVATE_REPLAY_TASKS[user_id] = asyncio.create_task(
        _run_offline_private_ai_replay_after_delay(bot, user_id, delay)
    )


def reset_offline_private_ai_replay_state() -> None:
    for task in _OFFLINE_PRIVATE_REPLAY_TASKS.values():
        if not task.done():
            task.cancel()
    _OFFLINE_PRIVATE_REPLAY_TASKS.clear()
    _OFFLINE_PRIVATE_PENDING_MESSAGE_IDS.clear()
    OFFLINE_PRIVATE_PENDING_USERS.clear()
    _OFFLINE_PRIVATE_REPLAYED_USERS.clear()


async def _run_offline_private_ai_replay_after_delay(
    bot: Bot,
    user_id: str,
    delay_seconds: float,
) -> None:
    try:
        await asyncio.sleep(max(0.0, delay_seconds))
        await replay_offline_private_ai_once(bot, user_id)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("Offline private AI replay failed: user_id={}, error={}", user_id, exc)
    finally:
        task = _OFFLINE_PRIVATE_REPLAY_TASKS.get(user_id)
        if task is asyncio.current_task():
            _OFFLINE_PRIVATE_REPLAY_TASKS.pop(user_id, None)
        OFFLINE_PRIVATE_PENDING_USERS.discard(user_id)


async def replay_offline_private_ai_once(bot: Bot, user_id: str) -> None:
    if user_id in _OFFLINE_PRIVATE_REPLAYED_USERS:
        return
    _OFFLINE_PRIVATE_REPLAYED_USERS.add(user_id)
    settings = load_settings()
    store = get_settings_store()
    profiles = load_ai_profiles(settings.ai_profile_file)
    profile = get_current_ai_profile_name(settings, store, profiles)
    memory_store = ChatMemoryStore(settings.data_root)
    message_ids = tuple(_OFFLINE_PRIVATE_PENDING_MESSAGE_IDS.pop(user_id, ()))
    if not message_ids:
        return
    recent_records = memory_store.load_messages_by_message_ids(f"private:{user_id}", message_ids)
    incoming_records = tuple(
        sorted(
            (
                record
                for record in recent_records
                if record.direction == "incoming" and record.user_id == str(user_id)
            ),
            key=lambda record: (record.timestamp, record.id),
        )
    )
    if not incoming_records:
        return

    prompt = build_offline_private_replay_prompt(incoming_records)
    fake_event = OfflinePrivateAiEvent(user_id=user_id, text=prompt, timestamp=incoming_records[-1].timestamp)
    normalized = normalize_onebot_event(fake_event)
    from qqbot.plugins.ai_test import build_ai_context, format_ai_response

    conversation_store = AiConversationStore(
        settings.data_root,
        max_messages=settings.ai_max_context_messages,
    )
    conversation_scope = AiUserStyleStore.rotation_slot_id(datetime.now())
    key = conversation_store.private_key(user_id, profile, conversation_scope)
    gateway = build_ai_gateway(settings, profile)
    response = await gateway.complete(
        AiRequest(
            plugin_id="ai",
            capability="chat",
            prompt=prompt,
            user_id=user_id,
            context=build_ai_context(
                settings,
                fake_event,
                AiGroupContextStore(settings.data_root),
                normalized,
                settings_store=store,
            ),
            history=conversation_store.load_messages(key),
        )
    )
    if not response.fallback:
        conversation_store.append_turn(key, prompt, response.text)
    await call_split_text_api(
        bot,
        "send_private_msg",
        user_id=int(user_id) if str(user_id).isdigit() else user_id,
        message=format_ai_response(profile, response, show_metrics=settings.ai_show_metrics),
    )


def build_offline_private_replay_prompt(records) -> str:
    lines = [f"{record.sender_name}: {record.text}" for record in records]
    return (
        "我刚刚恢复在线。下面是同一个用户在我离线期间发来的私聊消息，"
        "这些消息已经写入长期记忆。请把它们当成一个连续上下文，只回复一次：\n"
        + "\n".join(lines)
    )


class OfflinePrivateAiEvent:
    message_type = "private"

    def __init__(self, *, user_id: str, text: str, timestamp: int) -> None:
        self.user_id = str(user_id)
        self.text = text
        self.time = timestamp
        self.message_id = ""

    def get_user_id(self) -> str:
        return self.user_id

    def get_plaintext(self) -> str:
        return self.text

    @property
    def original_message(self):
        return OfflinePrivateAiMessage(self.text)

    @property
    def message(self):
        return self.original_message


class OfflinePrivateAiMessage:
    def __init__(self, text: str) -> None:
        self.text = text

    def extract_plain_text(self) -> str:
        return self.text

    def __iter__(self):
        return iter(())
