from __future__ import annotations

from nonebot import on_regex
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent

from qqbot.config import load_settings
from qqbot.services.command_guard import direct_command_rule
from qqbot.services.feature_catalog import get_feature_by_menu_key
from qqbot.services.group_file_cleanup_service import ShapezGroupFileCleanupService, ShapezGroupFileCleanupStore
from qqbot.services.group_control_service import parse_group_control_command
from qqbot.services.settings_store import get_settings_store

GROUP_FILE_CLEANUP_PATTERN = r"^(通知)?(大家|全员|群友)?(清理|整理)(群)?文件$|^(群)?文件(清理|整理)(通知)?$"
GROUP_CONTROL_PATTERN = r"(?i)^((禁|禁言)?[1-9][0-9]*[smh]?|解|解禁|群禁|群禁言|群解禁|踢|踢出)(\s|$)|" + GROUP_FILE_CLEANUP_PATTERN

group_control_matcher = on_regex(
    GROUP_CONTROL_PATTERN,
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
        return

    at_targets = []
    for segment in event.get_message():
        if segment.type == "at":
            qq = segment.data.get("qq")
            if qq and qq != "all":
                at_targets.append(int(qq))

    command = parse_group_control_command(text, at_targets)
    if command is None:
        return

    if command.action == "ban_member" and command.target_id and command.duration_seconds:
        await bot.call_api(
            "set_group_ban",
            group_id=event.group_id,
            user_id=command.target_id,
            duration=command.duration_seconds,
        )
        await group_control_matcher.finish(f"已禁言 {command.target_id} {command.duration_seconds} 秒。")

    if command.action == "unban_member" and command.target_id:
        await bot.call_api(
            "set_group_ban",
            group_id=event.group_id,
            user_id=command.target_id,
            duration=0,
        )
        await group_control_matcher.finish(f"已解除 {command.target_id} 的禁言。")

    if command.action == "ban_group":
        await bot.call_api("set_group_whole_ban", group_id=event.group_id, enable=True)
        await group_control_matcher.finish("已开启全群禁言。")

    if command.action == "unban_group":
        await bot.call_api("set_group_whole_ban", group_id=event.group_id, enable=False)
        await group_control_matcher.finish("已解除全群禁言。")

    if command.action == "kick_member" and command.target_id:
        await bot.call_api("set_group_kick", group_id=event.group_id, user_id=command.target_id)
        await group_control_matcher.finish(f"已将 {command.target_id} 移出群聊。")


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
