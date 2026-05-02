from __future__ import annotations

import random

from nonebot import on_message, on_regex
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent

from qqbot.services.command_guard import direct_command_rule, is_likely_command
from qqbot.services.feature_catalog import get_feature_by_index
from qqbot.services.settings_store import get_settings_store
from qqbot.services.thunder_service import parse_thunder_command

thunder_setting_matcher = on_regex(
    r"^设置(随机)?禁言(概率|时间).*$",
    priority=7,
    block=True,
    rule=direct_command_rule(),
)
thunder_message_matcher = on_message(priority=60, block=False)


def get_thunder_feature():
    return get_feature_by_index(2)


@thunder_setting_matcher.handle()
async def handle_thunder_setting(event: GroupMessageEvent) -> None:
    store = get_settings_store()
    if not store.is_bot_admin(int(event.get_user_id())):
        await thunder_setting_matcher.finish("只有Bot管理员才能设置随机禁言哦！")

    command = parse_thunder_command(event.get_plaintext().strip())
    if command is None:
        return

    chance, min_seconds, max_seconds = store.get_thunder_config(event.group_id)
    if command.action == "set_probability" and command.probability is not None:
        store.set_thunder_config(event.group_id, command.probability, min_seconds, max_seconds)
        await thunder_setting_matcher.finish(
            f"已将本群随机禁言概率设为 {command.probability:.3%}！"
        )
    if command.action == "set_range" and command.min_seconds and command.max_seconds:
        store.set_thunder_config(event.group_id, chance, command.min_seconds, command.max_seconds)
        await thunder_setting_matcher.finish(
            f"已将本群随机禁言时间设为 {command.min_seconds}s - {command.max_seconds}s！"
        )


@thunder_message_matcher.handle()
async def handle_thunder_message(bot: Bot, event: GroupMessageEvent) -> None:
    feature = get_thunder_feature()
    if feature is None:
        return
    store = get_settings_store()
    if not store.get_group_feature_state(event.group_id, feature):
        return

    text = event.get_plaintext().strip()
    if not text:
        return
    if is_likely_command(text):
        return

    chance, min_seconds, max_seconds = store.get_thunder_config(event.group_id)
    if random.random() >= chance:
        return

    seconds = random.randint(min_seconds, max_seconds)
    await bot.call_api(
        "set_group_ban",
        group_id=event.group_id,
        user_id=int(event.get_user_id()),
        duration=seconds,
    )
    await thunder_message_matcher.send(
        f"[CQ:at,qq={event.get_user_id()}]\n你被棉花糖的闪电击中，禁言{seconds}s！"
    )
