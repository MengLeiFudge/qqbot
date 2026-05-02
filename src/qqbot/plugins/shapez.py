from __future__ import annotations

from pathlib import Path

from nonebot import on_regex
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.adapters.onebot.v11 import MessageEvent

from qqbot.config import load_settings
from qqbot.services.command_guard import direct_command_rule
from qqbot.services.shapez_service import render_shape_code

shapez_matcher = on_regex(r"^[ip] .*$", priority=14, block=True, rule=direct_command_rule())


@shapez_matcher.handle()
async def handle_shapez(event: MessageEvent) -> None:
    text = event.get_plaintext().strip()
    if text.startswith("p "):
        await shapez_matcher.finish("功能还没有写好捏~")

    if not text.startswith("i "):
        return

    settings = load_settings()
    shape, output = render_shape_code(settings.data_root, text[2:])
    message = Message(
        [
            MessageSegment.image(output.as_posix()),
            MessageSegment.text(f"\n短代码：{shape.short_key}"),
        ]
    )
    await shapez_matcher.finish(message)
