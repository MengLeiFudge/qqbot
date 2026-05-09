from __future__ import annotations

import asyncio
import random

from nonebot import logger, on_notice, on_request
from nonebot.adapters.onebot.v11 import (
    Bot,
    FriendRequestEvent,
    GroupIncreaseNoticeEvent,
    GroupRequestEvent,
    Message,
    PokeNotifyEvent,
    RequestEvent,
)

from qqbot.services.message_delivery import call_split_text_api
from qqbot.services.feature_catalog import get_feature_by_menu_key
from qqbot.services.settings_store import get_settings_store
from qqbot.services.social_service import plan_poke_response, should_auto_approve_request

request_matcher = on_request(priority=1, block=False)
poke_matcher = on_notice(priority=20, block=False)
group_increase_matcher = on_notice(priority=1, block=False)

BOT_GROUP_INTRO_MESSAGE = (
    "我是萌萌棉花糖♪，以后会在这里陪大家聊天的喵！\n"
    "\n"
    "你可以这样问我：\n"
    "“@萌萌棉花糖♪ 你现在有哪些风格？”\n"
    "“@萌萌棉花糖♪ 切换猫娘风格”\n"
    "“@萌萌棉花糖♪ 菜单”\n"
    "“@萌萌棉花糖♪ 我是谁”\n"
    "“@萌萌棉花糖♪ 渲染 shapez 代码 CuCuCuCu”\n"
    "\n"
    "虽然我是一只猫娘，但我不会乱叫别人主人的喵！只有萌泪酱才是我最伟大的主人喵！\n"
    "Ciallo～(∠・ω< )⌒☆"
)


@request_matcher.handle()
async def handle_request(bot: Bot, event: RequestEvent) -> None:
    store = get_settings_store()
    if not _can_trigger_group_assistant(store, getattr(event, "user_id", 0), bot.self_id):
        return
    if not _is_group_assistant_enabled(store):
        return

    if isinstance(event, FriendRequestEvent):
        if should_auto_approve_request(event.request_type, None):
            await _approve_friend_request(bot, event)
        return

    if isinstance(event, GroupRequestEvent):
        if should_auto_approve_request(event.request_type, event.sub_type):
            await _approve_group_request(bot, event)


@group_increase_matcher.handle()
async def handle_group_increase(bot: Bot, event) -> None:
    if not isinstance(event, GroupIncreaseNoticeEvent):
        return
    if str(event.user_id) != str(bot.self_id):
        return
    inviter_id = int(getattr(event, "operator_id", 0) or 0)
    group_id = int(getattr(event, "group_id", 0) or 0)
    if inviter_id > 0:
        group_name = await _resolve_group_name(bot, group_id)
        await bot.call_api(
            "send_private_msg",
            user_id=inviter_id,
            message=f"棉花糖已经加入「{group_name}」啦，主人喵！",
        )
    await bot.call_api(
        "send_group_msg",
        group_id=group_id,
        message=BOT_GROUP_INTRO_MESSAGE,
    )


@poke_matcher.handle()
async def handle_poke(bot: Bot, event: PokeNotifyEvent) -> None:
    if int(event.user_id) == int(bot.self_id):
        return
    store = get_settings_store()
    if not _is_group_assistant_enabled(store):
        return
    if not _can_trigger_group_assistant(store, event.user_id, bot.self_id):
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


async def _approve_friend_request(bot: Bot, event: FriendRequestEvent) -> None:
    try:
        await bot.call_api("set_friend_add_request", flag=event.flag, approve=True)
    except Exception as exc:
        logger.exception(
            "Failed to approve friend request: user_id={}, flag={}, error={}",
            event.user_id,
            event.flag,
            exc,
        )
        return
    logger.info("Approved friend request: user_id={}, flag={}", event.user_id, event.flag)


async def _approve_group_request(bot: Bot, event: GroupRequestEvent) -> None:
    group_id = getattr(event, "group_id", 0)
    try:
        await bot.call_api(
            "set_group_add_request",
            flag=event.flag,
            sub_type=event.sub_type,
            approve=True,
        )
    except Exception as exc:
        logger.exception(
            "Failed to approve group request: group_id={}, user_id={}, sub_type={}, flag={}, error={}",
            group_id,
            event.user_id,
            event.sub_type,
            event.flag,
            exc,
        )
        return
    logger.info(
        "Approved group request: group_id={}, user_id={}, sub_type={}, flag={}",
        group_id,
        event.user_id,
        event.sub_type,
        event.flag,
    )


async def _resolve_group_name(bot: Bot, group_id: int) -> str:
    try:
        payload = await bot.call_api("get_group_info", group_id=group_id, no_cache=True)
    except Exception as exc:
        logger.warning("Failed to resolve group name: group_id={}, error={}", group_id, exc)
        return str(group_id)
    if isinstance(payload, dict):
        name = str(payload.get("group_name") or "").strip()
        if name:
            return name
    return str(group_id)


def _is_group_assistant_enabled(store) -> bool:
    feature = get_feature_by_menu_key("群管助手")
    return feature is not None and store.get_group_feature_state(0, feature)


def _can_trigger_group_assistant(store, user_id: int | str, self_id: int | str) -> bool:
    try:
        actor_id = int(user_id)
    except (TypeError, ValueError):
        return False
    return store.is_bot_admin_or_self(actor_id, self_id)
