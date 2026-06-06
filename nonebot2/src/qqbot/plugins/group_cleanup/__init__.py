from __future__ import annotations

from nonebot import logger, on_notice
from nonebot.adapters.onebot.v11 import GroupDecreaseNoticeEvent

from qqbot.config import load_settings
from qqbot.features.group.cleanup_service import GroupCleanupService

group_cleanup_matcher = on_notice(priority=1, block=False)


def should_cleanup_group_decrease(event: GroupDecreaseNoticeEvent) -> bool:
    return int(event.user_id) == int(event.self_id)


@group_cleanup_matcher.handle()
async def handle_group_cleanup_notice(event: GroupDecreaseNoticeEvent) -> None:
    if not isinstance(event, GroupDecreaseNoticeEvent):
        return
    if not should_cleanup_group_decrease(event):
        return

    settings = load_settings()
    result = GroupCleanupService(settings.data_root, settings.author_qq).cleanup_group(
        event.group_id
    )
    logger.info(
        "Cleaned group scoped config after bot left group {}: {}",
        result.group_id,
        ", ".join(result.removed_items) or "nothing",
    )
