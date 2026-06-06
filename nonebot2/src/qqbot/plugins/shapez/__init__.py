from __future__ import annotations

from nonebot import on_regex
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.adapters.onebot.v11 import MessageEvent

from qqbot.config import load_settings
from qqbot.services.command_guard import direct_command_rule
from qqbot.features.shapez.service import render_shape_chart, render_shape_code, render_shape_path

shapez_matcher = on_regex(
    r"^(i|view|chart|chart1|chart2|path|path1|path2|p|puzzle|puzzle1|puzzle2) .*$",
    priority=14,
    block=True,
    rule=direct_command_rule(),
)


@shapez_matcher.handle()
async def handle_shapez(event: MessageEvent) -> None:
    text = event.get_plaintext().strip()
    normalized_text = text.lower()
    if normalized_text.startswith(("p ", "puzzle ", "puzzle1 ", "puzzle2 ")):
        await shapez_matcher.finish("没获取到 shapez 谜题：在线谜题下载需要 shapez 登录 token，当前未配置。")

    command, _, argument = text.partition(" ")
    command = command.lower()
    if command not in {"i", "view", "chart", "chart1", "chart2", "path", "path1", "path2"}:
        return

    settings = load_settings()
    if command in {"path", "path1", "path2"}:
        tree, output, path_text = render_shape_path(settings.data_root, argument)
        message = Message(
            [
                MessageSegment.image(output.as_posix()),
                MessageSegment.text(f"\n短代码：{tree.shortcode}\n{path_text}"),
            ]
        )
    elif command in {"chart", "chart1", "chart2"}:
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
