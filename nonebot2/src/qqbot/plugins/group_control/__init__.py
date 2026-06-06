from __future__ import annotations

from nonebot import on_regex
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent

from qqbot.config import load_settings
from qqbot.services.command_guard import direct_command_rule
from qqbot.services.feature_catalog import get_feature_by_menu_key
from qqbot.features.group.file_cleanup_service import ShapezGroupFileCleanupService, ShapezGroupFileCleanupStore
from qqbot.services.settings_store import get_settings_store

GROUP_FILE_CLEANUP_PATTERN = r"^(通知)?(大家|全员|群友)?(清理|整理)(群)?文件$|^(群)?文件(清理|整理)(通知)?$"

group_control_matcher = on_regex(
    GROUP_FILE_CLEANUP_PATTERN,
    priority=8,
    block=True,
    rule=direct_command_rule(),
)


@group_control_matcher.handle()
async def handle_group_control(bot: Bot, event: GroupMessageEvent) -> None:
    store = get_settings_store()
    feature = get_feature_by_menu_key("群管助手")
    if feature is None or not store.get_group_feature_state(event.group_id, feature):
        return
    if not store.is_bot_admin_or_self(int(event.get_user_id()), bot.self_id):
        return

    text = event.get_plaintext().strip()
    if is_group_file_cleanup_command(text):
        await handle_group_file_cleanup_command(bot, event.group_id)


def is_group_file_cleanup_command(text: str) -> bool:
    import re

    return re.match(GROUP_FILE_CLEANUP_PATTERN, text.strip()) is not None


async def handle_group_file_cleanup_command(bot: Bot, group_id: int) -> dict[str, object]:
    settings = load_settings()
    service = ShapezGroupFileCleanupService(
        store=ShapezGroupFileCleanupStore(settings.data_root / "data" / "shapez_file_cleanup_state.json"),
        group_id=str(group_id),
        timezone_name=settings.timezone,
    )
    result = await service.scan_and_notify_group(bot)
    if result.get("violating_user_count") == 0:
        await bot.call_api("send_group_msg", group_id=group_id, message="当前没有超过一周的外层群文件需要清理。")
    elif result.get("failed_group_message_count"):
        await bot.call_api("send_group_msg", group_id=group_id, message="部分文件清理名单没有发出，对应名单已跳过禁言。")
    return result
