from __future__ import annotations

from nonebot import on_regex
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.adapters.onebot.v11 import MessageEvent

from qqbot.config import load_settings
from qqbot.services.command_guard import direct_command_rule
from qqbot.features.donate.service import build_donate_caption, locate_donate_image

donate_matcher = on_regex(
    r"(?i)^(/?donate|捐献|支持)$",
    priority=9,
    block=True,
    rule=direct_command_rule(),
)


@donate_matcher.handle()
async def handle_donate(event: MessageEvent) -> None:
    settings = load_settings()
    caption = build_donate_caption(int(event.get_user_id()), settings.author_name)
    message = Message(
        [
            MessageSegment.at(int(event.get_user_id())),
            MessageSegment.text(f"\n{caption.splitlines()[-1]}\n"),
        ]
    )

    donate_image = locate_donate_image(settings.data_root)
    if donate_image is not None:
        message += MessageSegment.image(donate_image.as_posix())

    await donate_matcher.finish(message)
