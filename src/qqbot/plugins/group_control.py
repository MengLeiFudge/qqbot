from __future__ import annotations

from nonebot import on_regex
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent

from qqbot.services.command_guard import direct_command_rule
from qqbot.services.group_control_service import parse_group_control_command
from qqbot.services.settings_store import get_settings_store

GROUP_CONTROL_PATTERN = r"(?i)^((禁|禁言)?[1-9][0-9]*[smh]?|解|解禁|群禁|群禁言|群解禁|踢|踢出)(\s|$)"

group_control_matcher = on_regex(
    GROUP_CONTROL_PATTERN,
    priority=8,
    block=True,
    rule=direct_command_rule(),
)


@group_control_matcher.handle()
async def handle_group_control(bot: Bot, event: GroupMessageEvent) -> None:
    store = get_settings_store()
    if not store.is_bot_admin(int(event.get_user_id())):
        return

    at_targets = []
    for segment in event.get_message():
        if segment.type == "at":
            qq = segment.data.get("qq")
            if qq and qq != "all":
                at_targets.append(int(qq))

    command = parse_group_control_command(event.get_plaintext().strip(), at_targets)
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
