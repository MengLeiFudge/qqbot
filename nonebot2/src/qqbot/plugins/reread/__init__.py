from __future__ import annotations

from nonebot import on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent

from qqbot.services.command_guard import is_likely_command
from qqbot.services.feature_catalog import get_feature_by_menu_key
from qqbot.services.offline_message_gate import is_before_onebot_connect
from qqbot.features.group.reread_service import (
    DEFAULT_REREAD_STATE,
    render_reread_message,
    should_skip_reread_message,
)
from qqbot.services.settings_store import get_settings_store

reread_message_matcher = on_message(priority=50, block=False)


def get_reread_feature():
    return get_feature_by_menu_key("复读")


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
    text = event.get_plaintext().strip()
    if not text:
        return
    if is_likely_command(text):
        return

    message = event.get_message()
    if should_skip_reread_message(message):
        return

    observation = DEFAULT_REREAD_STATE.observe(
        event.group_id,
        text,
        message_id=getattr(event, "message_id", ""),
    )
    if not observation.should_repeat:
        return

    await reread_message_matcher.send(render_reread_message(message))
