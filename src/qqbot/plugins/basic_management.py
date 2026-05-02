from __future__ import annotations

import re

from nonebot import on_regex
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    Message,
    MessageEvent,
    MessageSegment,
)

from qqbot.services.feature_catalog import (
    build_feature_menu_text,
    build_group_menu_text,
    get_feature_by_index,
    get_feature_by_menu_key,
    list_visible_features,
)
from qqbot.services.command_guard import direct_command_rule
from qqbot.services.settings_store import get_settings_store
from qqbot.services.message_delivery import finish_split_text

FEATURE_MENU_PATTERN = r"^菜单\S+$"

menu_matcher = on_regex(r"^(菜单|帮助|指令)$", priority=5, block=True, rule=direct_command_rule())
feature_menu_matcher = on_regex(FEATURE_MENU_PATTERN, priority=5, block=True, rule=direct_command_rule())
feature_switch_matcher = on_regex(
    r"^(开启|关闭)(功能)?\d+$",
    priority=5,
    block=True,
    rule=direct_command_rule(),
)
admin_matcher = on_regex(
    r"^((增加|设置|设|加)(管理|管理员)|(删除|取消|删)(管理|管理员))",
    priority=5,
    block=True,
    rule=direct_command_rule(),
)


@menu_matcher.handle()
async def handle_menu(event: MessageEvent) -> None:
    if not isinstance(event, GroupMessageEvent):
        await menu_matcher.finish("请在群中发送【菜单】以了解Bot各功能开启情况！")

    store = get_settings_store()
    feature_states = {
        feature.index: store.get_group_feature_state(event.group_id, feature)
        for feature in list_visible_features()
    }
    await finish_split_text(
        menu_matcher,
        build_group_menu_text(feature_states),
        group_id=event.group_id,
    )


@feature_menu_matcher.handle()
async def handle_feature_menu(event: MessageEvent) -> None:
    key = event.get_plaintext().strip().removeprefix("菜单")

    feature = get_feature_by_menu_key(key)
    if feature is None:
        await feature_menu_matcher.finish("没有这个功能编号哦！")
    menu_text = build_feature_menu_text(feature.index)
    if menu_text is None:
        await feature_menu_matcher.finish("没有这个功能编号哦！")
    await finish_split_text(
        feature_menu_matcher,
        menu_text,
        group_id=getattr(event, "group_id", None),
    )


@feature_switch_matcher.handle()
async def handle_feature_switch(event: MessageEvent) -> None:
    if not isinstance(event, GroupMessageEvent):
        await feature_switch_matcher.finish("只能在群内开关功能哦！")

    store = get_settings_store()
    if not store.is_bot_admin(int(event.get_user_id())):
        await feature_switch_matcher.finish("只有Bot管理员才能开关功能哦！")

    text = event.get_plaintext().strip()
    match = re.search(r"(\d+)", text)
    if match is None:
        await feature_switch_matcher.finish()

    feature = get_feature_by_index(int(match.group(1)))
    if feature is None:
        await feature_switch_matcher.finish("没有这个功能编号哦！")

    is_open = text.startswith("开")
    store.set_group_feature_state(event.group_id, feature, is_open)
    action = "已开启" if is_open else "已关闭"
    await feature_switch_matcher.finish(f"{action}{feature.name}！")


@admin_matcher.handle()
async def handle_admin_manage(event: MessageEvent) -> None:
    store = get_settings_store()
    if int(event.get_user_id()) != store.author_qq:
        return

    at_targets = []
    for segment in event.get_message():
        if segment.type == "at":
            qq = segment.data.get("qq")
            if qq and qq != "all":
                at_targets.append(int(qq))

    if not at_targets:
        return

    text = event.get_plaintext().strip()
    if re.match(r"^(增加|设置|设|加)(管理|管理员)", text):
        for target in at_targets:
            store.set_bot_admin(target, True)
        message = Message("已将 ")
        for index, target in enumerate(at_targets):
            if index > 0:
                message += MessageSegment.text("、")
            message += MessageSegment.at(target)
        message += MessageSegment.text(" 设为Bot管理！")
        await admin_matcher.finish(message)

    if re.match(r"^(删除|取消|删)(管理|管理员)", text):
        for target in at_targets:
            store.set_bot_admin(target, False)
        message = Message("已取消 ")
        for index, target in enumerate(at_targets):
            if index > 0:
                message += MessageSegment.text("、")
            message += MessageSegment.at(target)
        message += MessageSegment.text(" 的Bot管理权限！")
        await admin_matcher.finish(message)
