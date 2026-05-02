from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, MessageEvent
from nonebot.params import CommandArg

from qqbot.config import load_settings
from qqbot.services.message_delivery import finish_split_text
from qqbot.services.status import build_status_lines

ping = on_command("ping", priority=10, block=True)
echo = on_command("echo", priority=10, block=True)
status = on_command("status", priority=10, block=True)


@ping.handle()
async def handle_ping() -> None:
    await ping.finish("pong")


@echo.handle()
async def handle_echo(event: MessageEvent, args: Message = CommandArg()) -> None:
    text = args.extract_plain_text().strip()
    if not text:
        await echo.finish("用法：/echo 你想让我复述的内容")
    await finish_split_text(echo, text, group_id=getattr(event, "group_id", None))


@status.handle()
async def handle_status(event: MessageEvent) -> None:
    settings = load_settings()
    lines = build_status_lines(settings)
    lines.append(f"Last Trigger User: {event.get_user_id()}")
    await finish_split_text(status, "\n".join(lines), group_id=getattr(event, "group_id", None))
