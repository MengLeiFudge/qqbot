from __future__ import annotations

from nonebot import logger, on_notice
from nonebot.adapters.onebot.v11 import Bot, GroupRecallNoticeEvent

from qqbot.services.message_delivery import handle_group_message_recall

message_recall_matcher = on_notice(priority=1, block=False)


@message_recall_matcher.handle()
async def handle_message_recall_notice(bot: Bot, event: GroupRecallNoticeEvent) -> None:
    if not isinstance(event, GroupRecallNoticeEvent):
        return
    handled = await handle_group_message_recall(
        bot,
        group_id=event.group_id,
        message_id=event.message_id,
        user_id=event.user_id,
        self_id=event.self_id,
    )
    if handled:
        logger.info(
            "Handled recalled bot message fallback: group_id={}, message_id={}",
            event.group_id,
            event.message_id,
        )
