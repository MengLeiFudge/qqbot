from __future__ import annotations

from nonebot import on_regex
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    MessageEvent,
)

from qqbot.services.feature_catalog import (
    build_feature_menu_text,
    build_group_menu_text,
    get_feature_by_menu_key,
    list_visible_features,
)
from qqbot.services.command_guard import direct_command_rule
from qqbot.services.settings_store import get_settings_store
from qqbot.services.message_delivery import finish_split_text

FEATURE_MENU_PATTERN = r"^菜单(?!\d+$)\S+$"

menu_matcher = on_regex(r"^(菜单|帮助|指令)$", priority=5, block=True, rule=direct_command_rule())
feature_menu_matcher = on_regex(FEATURE_MENU_PATTERN, priority=5, block=True, rule=direct_command_rule())
@menu_matcher.handle()
async def handle_menu(event: MessageEvent) -> None:
    if not isinstance(event, GroupMessageEvent):
        await menu_matcher.finish("请在群中发送【菜单】以了解Bot各功能开启情况！")

    store = get_settings_store()
    feature_states = {
        feature.plugin_id: store.get_group_feature_state(event.group_id, feature)
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
        await feature_menu_matcher.finish("没有这个模块哦！")
    menu_text = build_feature_menu_text(feature.name)
    if menu_text is None:
        await feature_menu_matcher.finish("没有这个模块哦！")
    await finish_split_text(
        feature_menu_matcher,
        menu_text,
        group_id=getattr(event, "group_id", None),
    )
