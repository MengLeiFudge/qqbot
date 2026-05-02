from __future__ import annotations

import re

from nonebot import on_regex
from nonebot.adapters.onebot.v11 import MessageEvent

from qqbot.config import load_settings
from qqbot.services.command_guard import direct_command_rule
from qqbot.services.sakura_service import SakuraService

sakura_matcher = on_regex(
    r"^(落樱之都|更新日志|玩法|注册.+|改名.+|个人信息|加经验[0-9]+|嘤[0-9]+|恢复|回复|加[0-9]+(力量|智力|体质|敏捷|魅力))$",
    priority=110,
    block=True,
    rule=direct_command_rule(),
)


def get_sakura_service() -> SakuraService:
    settings = load_settings()
    return SakuraService(settings.data_root / "data" / "sakura" / "players.json")


@sakura_matcher.handle()
async def handle_sakura(event: MessageEvent) -> None:
    text = event.get_plaintext().strip()
    service = get_sakura_service()
    player = service.get_player(int(event.get_user_id()))

    if text == "落樱之都":
        await sakura_matcher.finish(
            "-===🌸落樱之都🌸===-\n"
            "个人信息◇人物加点\n"
            "我的背包◇我的任务\n"
            "装备强化◇落樱商城\n"
            "单人副本◇魔塔挑战\n"
            "多人副本◇竞技战斗\n"
            "注册xxx / 改名xxx / 个人信息 / 加点"
        )

    if text == "更新日志":
        await sakura_matcher.finish("目前只是做了个框架，需要继续迁移副本、商城、排行等内容。")

    if text == "玩法":
        await sakura_matcher.finish("当前已迁移角色注册、改名、个人信息、经验、樱币、加点、恢复等基础玩法。")

    if text.startswith("注册"):
        name = text[2:].strip()
        if not name:
            await sakura_matcher.finish("要有名字哦！")
        if service.get_player(int(event.get_user_id())):
            await sakura_matcher.finish("已有角色，无法创建！")
        player = service.register_player(int(event.get_user_id()), name[:10])
        await sakura_matcher.finish(f"已创建角色【{player.name}】！")

    if player is None:
        return

    if text.startswith("改名"):
        await sakura_matcher.finish(service.rename_player(player, text[2:].strip()[:10]))

    if text == "个人信息":
        await sakura_matcher.finish(service.build_profile_summary(player))

    if match := re.match(r"^加经验([0-9]+)$", text):
        await sakura_matcher.finish(service.add_exp(player, int(match.group(1))))

    if match := re.match(r"^嘤([0-9]+)$", text):
        await sakura_matcher.finish(service.add_money(player, int(match.group(1))))

    if text in {"恢复", "回复"}:
        await sakura_matcher.finish(service.reset_player(player))

    if match := re.match(r"^加([0-9]+)(力量|智力|体质|敏捷|魅力)$", text):
        await sakura_matcher.finish(service.add_points(player, match.group(2), int(match.group(1))))
