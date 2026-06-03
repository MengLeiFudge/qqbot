from __future__ import annotations

import asyncio
import time
from typing import Any

from nonebot.adapters.onebot.v11 import Bot as OneBotV11Bot

from qqbot.config import load_settings
from qqbot.services.ai_group_context_store import AiGroupContextStore
from qqbot.services.chat_memory_store import ChatMemoryStore
from qqbot.services.group_message_log_store import GroupMessageLogStore
from qqbot.services.message_delivery import (
    has_waited_group_message_interval,
    wait_for_group_message_interval,
)
from qqbot.services.message_normalizer import normalize_onebot_message

_INSTALLED = False


def extract_group_message_group_id(api: str, data: dict[str, Any]) -> object | None:
    if api == "send_group_msg":
        return data.get("group_id")
    if api == "send_msg" and (data.get("message_type") == "group" or data.get("group_id") is not None):
        return data.get("group_id")
    return None


def get_group_message_log_store() -> GroupMessageLogStore:
    return GroupMessageLogStore(load_settings().data_root)


def get_chat_memory_store() -> ChatMemoryStore:
    return ChatMemoryStore(load_settings().data_root)


def get_ai_group_context_store() -> AiGroupContextStore:
    return AiGroupContextStore(load_settings().data_root)


def _looks_like_record_cq(text: str) -> bool:
    return text.strip().startswith("[CQ:record,")


def render_outgoing_group_message(message: object) -> str:
    if getattr(message, "type", "") == "record":
        return "[语音]"
    try:
        normalized = normalize_onebot_message(message)
    except TypeError:
        text = str(message or "").strip()
        return "[语音]" if _looks_like_record_cq(text) else text
    if normalized.outline:
        return normalized.outline
    text = str(message or "").strip()
    return "[语音]" if _looks_like_record_cq(text) else text


def extract_quote_message_id(message: object) -> str:
    try:
        for segment in message:
            if getattr(segment, "type", "") == "reply":
                raw_id = getattr(segment, "data", {}).get("id", "")
                return str(raw_id or "")
    except TypeError:
        pass
    try:
        normalized = normalize_onebot_message(message)
    except TypeError:
        return ""
    if normalized.reply is None:
        return ""
    return str(normalized.reply.message_id or "")


def infer_delivery_mode(api: str, message: object) -> str:
    if api == "send_group_forward_msg":
        return "collapsible"
    if getattr(message, "type", "") == "record":
        return "record"
    text = render_outgoing_group_message(message)
    if text == "[语音]" or _looks_like_record_cq(text):
        return "record"
    if text.startswith("（") and "）\n" in text[:16]:
        return "split"
    return "direct"


def record_bot_group_message(
    *,
    store: GroupMessageLogStore,
    memory_store: ChatMemoryStore | None = None,
    context_store: AiGroupContextStore | None = None,
    group_id: object,
    self_id: object,
    message: object,
    timestamp: float,
    result: object,
    api: str = "send_group_msg",
) -> None:
    text = render_outgoing_group_message(message)
    if not text:
        return

    message_id = ""
    if isinstance(result, dict):
        message_id = str(result.get("message_id", "") or "")
    store.append_message(
        group_id=str(group_id),
        direction="bot",
        user_id=str(self_id),
        sender_name="Bot",
        text=text,
        timestamp=timestamp,
        message_id=message_id,
        quote_message_id=extract_quote_message_id(message),
        delivery_mode=infer_delivery_mode(api, message),
    )
    if memory_store is not None:
        memory_store.append_message(
            group_id=str(group_id),
            direction="bot",
            user_id=str(self_id),
            sender_name="Bot",
            text=text,
            timestamp=timestamp,
            message_id=message_id,
        )
    if context_store is not None:
        context_store.append_message(
            group_id=str(group_id),
            user_id=str(self_id),
            sender_name="Bot",
            text=text,
            timestamp=int(timestamp),
            message_id=message_id,
        )


def install_onebot_group_message_throttle() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    original_call_api = OneBotV11Bot.call_api

    async def throttled_call_api(self: OneBotV11Bot, api: str, **data: Any) -> Any:
        group_id = extract_group_message_group_id(api, data)
        if group_id is not None and not has_waited_group_message_interval():
            await wait_for_group_message_interval(group_id)
        result = await original_call_api(self, api, **data)
        if group_id is not None:
            # 管理端消息流是旁路记录，不能影响真实群消息发送结果。
            try:
                await asyncio.to_thread(
                    record_bot_group_message,
                    store=get_group_message_log_store(),
                    memory_store=get_chat_memory_store(),
                    context_store=get_ai_group_context_store(),
                    group_id=group_id,
                    self_id=getattr(self, "self_id", ""),
                    message=data.get("message", ""),
                    timestamp=time.time(),
                    result=result,
                    api=api,
                )
            except Exception:
                pass
        return result

    OneBotV11Bot.call_api = throttled_call_api
    _INSTALLED = True
