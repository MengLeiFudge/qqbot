from __future__ import annotations

import random
import re

from nonebot import on_message, on_regex
from nonebot.adapters.onebot.v11 import GroupMessageEvent

from qqbot.services.command_guard import direct_command_rule, is_likely_command
from qqbot.services.feature_catalog import get_feature_by_menu_key
from qqbot.services.offline_message_gate import is_before_onebot_connect
from qqbot.services.reread_service import (
    clamp_reread_percent,
    format_reread_chance,
    render_reread_message,
    should_skip_reread_message,
)
from qqbot.services.settings_store import get_settings_store

reread_setting_matcher = on_regex(
    r"^设置复读(概率)? *[0-9]+(\.[0-9]+)?%?$",
    priority=6,
    block=True,
    rule=direct_command_rule(),
)
reread_message_matcher = on_message(priority=50, block=False)


def get_reread_feature():
    return get_feature_by_menu_key("群管助手")


@reread_setting_matcher.handle()
async def handle_reread_setting(event: GroupMessageEvent) -> None:
    store = get_settings_store()
    if not store.is_bot_admin_or_self(int(event.get_user_id()), getattr(event, "self_id", None)):
        await reread_setting_matcher.finish("只有Bot管理员才能设置复读概率哦！")

    match = re.search(r"([0-9]+(\.[0-9]+)?)", event.get_plaintext())
    if match is None:
        await reread_setting_matcher.finish()

    chance = clamp_reread_percent(float(match.group(1)))
    store.set_reread_chance(event.group_id, chance)
    await reread_setting_matcher.finish(
        f"已将全局复读概率设为 {format_reread_chance(chance)}！"
    )


@reread_message_matcher.handle()
async def handle_reread_message(event: GroupMessageEvent) -> None:
    if is_before_onebot_connect(getattr(event, "time", None)):
        return

    feature = get_reread_feature()
    if feature is None:
        return

    store = get_settings_store()
    if not store.get_group_feature_state(event.group_id, feature):
        return
    if not store.is_bot_admin_or_self(int(event.get_user_id()), getattr(event, "self_id", None)):
        return

    text = event.get_plaintext().strip()
    if not text:
        return
    if is_likely_command(text):
        return

    message = event.get_message()
    if should_skip_reread_message(message):
        return

    chance = store.get_reread_chance(event.group_id)
    if random.random() > chance:
        return

    await reread_message_matcher.send(render_reread_message(message))
