from __future__ import annotations

import asyncio
import random

from nonebot import on_notice, on_request
from nonebot.adapters.onebot.v11 import (
    Bot,
    FriendRequestEvent,
    GroupRequestEvent,
    Message,
    PokeNotifyEvent,
    RequestEvent,
)

from qqbot.services.message_delivery import call_split_text_api
from qqbot.services.social_service import plan_poke_response, should_auto_approve_request

request_matcher = on_request(priority=1, block=False)
poke_matcher = on_notice(priority=20, block=False)


@request_matcher.handle()
async def handle_request(bot: Bot, event: RequestEvent) -> None:
    if isinstance(event, FriendRequestEvent):
        if should_auto_approve_request(event.request_type, None):
            await event.approve(bot)
        return

    if isinstance(event, GroupRequestEvent):
        if should_auto_approve_request(event.request_type, event.sub_type):
            await event.approve(bot)


@poke_matcher.handle()
async def handle_poke(bot: Bot, event: PokeNotifyEvent) -> None:
    if int(event.user_id) == int(bot.self_id):
        return

    plan = plan_poke_response(
        self_id=int(bot.self_id),
        user_id=event.user_id,
        target_id=event.target_id,
        roll=random.randint(1, 100),
    )
    # 按旧 mirai 的顺序执行：先等，再发提示，再执行真实反戳动作。
    for step in plan.steps:
        if step.delay_ms > 0:
            await asyncio.sleep(step.delay_ms / 1000)
        if step.message is not None:
            await _send_session_message(bot, event, Message(step.message))
        if step.poke_target is not None:
            await _send_poke_action(bot, event, step.poke_target)


async def _send_session_message(bot: Bot, event: PokeNotifyEvent, message: Message) -> None:
    if event.group_id is not None:
        await call_split_text_api(
            bot,
            "send_group_msg",
            group_id=event.group_id,
            message=str(message),
            group_interval_sleep=asyncio.sleep,
        )
        return
    await bot.call_api("send_private_msg", user_id=event.user_id, message=message)


async def _send_poke_action(bot: Bot, event: PokeNotifyEvent, target_id: int) -> None:
    # NapCat 的反戳需要走专门 API；把 poke 消息段当普通消息发出去不会触发真实“拍一拍”动作。
    if event.group_id is not None:
        await bot.call_api("group_poke", group_id=str(event.group_id), user_id=str(target_id))
        return
    await bot.call_api("friend_poke", user_id=str(target_id))
