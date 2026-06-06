from __future__ import annotations

from nonebot import on_regex
from nonebot.adapters.onebot.v11 import MessageEvent

from qqbot.config import load_settings
from qqbot.services.command_guard import direct_command_rule
from qqbot.services.group_nick_store import get_group_nick_store
from qqbot.features.kun.service import KunService
from qqbot.services.settings_store import get_settings_store

kun_matcher = on_regex(
    r"^(养鲲|摸鲲|抓鲲|捕鲲|属性|洗练.+[0-9]+|查看.*|等级排行(榜|)?|财富排行(榜|)?|萌泪币排行(榜|)?|金钱排行(榜|)?|道具|背包|命名.+|商城|(购买|买|出售|卖).+|签到|设置重置时间 *[0-9]+|[开关]新赛季提示|.*赠送.*|赠送全部 *[0-9]+|boss|Boss|查看boss|查看Boss|查看boss属性|查看Boss属性|挑战|进击.*|(更改|修改).+[0-9]+)$",
    priority=100,
    block=True,
    rule=direct_command_rule(),
)


def get_kun_service() -> KunService:
    settings = load_settings()
    return KunService(settings.data_root / "data" / "kun" / "users.json")


@kun_matcher.handle()
async def handle_kun(event: MessageEvent) -> None:
    service = get_kun_service()
    store = get_settings_store()
    group_nick_store = get_group_nick_store()
    message = event.get_message()
    at_ids = [int(seg.data["qq"]) for seg in message if seg.type == "at"]
    response = service.handle_command(
        event.get_plaintext().strip(),
        int(event.get_user_id()),
        getattr(event, "time", 0) * 1000,
        is_group=getattr(event, "message_type", "") == "group",
        at_id=at_ids[0] if at_ids else None,
        is_admin=store.is_bot_admin(int(event.get_user_id())),
        group_id=getattr(event, "group_id", 0),
        resolve_display_name=group_nick_store.resolve_display_name,
    )
    if response is not None:
        await kun_matcher.finish(response)
