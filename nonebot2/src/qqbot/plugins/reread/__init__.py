from __future__ import annotations

from nonebot import on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent

from qqbot.services.command_guard import is_likely_command
from qqbot.services.feature_catalog import get_feature_by_menu_key
from qqbot.services.offline_message_gate import is_before_onebot_connect
from qqbot.features.group.reread_service import (
    RereadRepeatState,
    render_reread_message,
    should_skip_reread_message,
)
from qqbot.services.settings_store import get_settings_store

reread_message_matcher = on_message(priority=50, block=False)
_REREAD_STATE = RereadRepeatState()


def get_reread_feature():
    return get_feature_by_menu_key("群管助手")


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

    if not _REREAD_STATE.should_repeat(event.group_id, text):
        return

    await reread_message_matcher.send(render_reread_message(message))
