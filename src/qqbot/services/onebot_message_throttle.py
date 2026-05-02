from __future__ import annotations

from typing import Any

from nonebot.adapters.onebot.v11 import Bot as OneBotV11Bot

from qqbot.services.message_delivery import (
    has_waited_group_message_interval,
    wait_for_group_message_interval,
)

_INSTALLED = False


def extract_group_message_group_id(api: str, data: dict[str, Any]) -> object | None:
    if api == "send_group_msg":
        return data.get("group_id")
    if api == "send_msg" and (data.get("message_type") == "group" or data.get("group_id") is not None):
        return data.get("group_id")
    return None


def install_onebot_group_message_throttle() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    original_call_api = OneBotV11Bot.call_api

    async def throttled_call_api(self: OneBotV11Bot, api: str, **data: Any) -> Any:
        group_id = extract_group_message_group_id(api, data)
        if group_id is not None and not has_waited_group_message_interval():
            await wait_for_group_message_interval(group_id)
        return await original_call_api(self, api, **data)

    OneBotV11Bot.call_api = throttled_call_api
    _INSTALLED = True
