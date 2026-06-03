from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from qqbot.config import RuntimeSettings
from qqbot.services.ai_command import AiChatTriggerKind
from qqbot.services.message_normalizer import NormalizedMessage
from qqbot.services.settings_store import SettingsStore


@dataclass(frozen=True)
class AiMessageSource:
    bot: Any
    event: Any
    settings: RuntimeSettings
    store: SettingsStore
    normalized_message: NormalizedMessage
    prompt: str
    request_started: float
    request_wall_started: float
    event_time: object
    message_id: object
    group_id: object | None
    user_id: str
    trigger_kind: AiChatTriggerKind
    reply_scope: str


async def build_ai_message_source(
    *,
    bot: Any,
    event: Any,
    settings: RuntimeSettings,
    store: SettingsStore,
    normalizer,
    prompt_builder,
    trigger_resolver,
    reply_scope_builder,
) -> AiMessageSource:
    request_started = time.perf_counter()
    request_wall_started = time.time()
    normalized_message = await normalizer(event, bot.call_api)
    return AiMessageSource(
        bot=bot,
        event=event,
        settings=settings,
        store=store,
        normalized_message=normalized_message,
        prompt=prompt_builder(normalized_message),
        request_started=request_started,
        request_wall_started=request_wall_started,
        event_time=getattr(event, "time", None),
        message_id=getattr(event, "message_id", None),
        group_id=getattr(event, "group_id", None),
        user_id=event.get_user_id(),
        trigger_kind=trigger_resolver(event),
        reply_scope=reply_scope_builder(event),
    )
