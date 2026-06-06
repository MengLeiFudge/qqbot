from __future__ import annotations

from nonebot import on_regex
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.adapters.onebot.v11 import MessageEvent

from qqbot.config import load_settings
from qqbot.services.command_guard import direct_command_rule
from qqbot.features.shapez.service import render_shape_chart, render_shape_code

shapez_matcher = on_regex(
    r"^(i|view|chart|chart1|chart2|p) .*$",
    priority=14,
    block=True,
    rule=direct_command_rule(),
)


@shapez_matcher.handle()
async def handle_shapez(event: MessageEvent) -> None:
    text = event.get_plaintext().strip()
    if text.startswith("p "):
        await shapez_matcher.finish("谜题下载需要 shapez 在线接口 token，当前未接入。")

    command, _, argument = text.partition(" ")
    if command not in {"i", "view", "chart", "chart1", "chart2"}:
        return

    settings = load_settings()
    if command in {"chart", "chart1", "chart2"}:
        shape, output, shape_text = render_shape_chart(settings.data_root, argument)
        message = Message(
            [
                MessageSegment.image(output.as_posix()),
                MessageSegment.text(f"\n短代码：{shape.short_key}\n{shape_text}"),
            ]
        )
    else:
        shape, output = render_shape_code(settings.data_root, argument)
        message = Message(
            [
                MessageSegment.image(output.as_posix()),
                MessageSegment.text(f"\n短代码：{shape.short_key}"),
            ]
        )
    await shapez_matcher.finish(message)
