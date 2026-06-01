from __future__ import annotations

import asyncio

from nonebot import on_regex
from nonebot.adapters.onebot.v11 import MessageEvent

from qqbot.services.command_guard import direct_command_rule
from qqbot.services.factorio_download_service import (
    FactorioDownloadError,
    FactorioDownloadService,
    render_factorio_download_safety_message,
)


FACTORIO_DOWNLOAD_PATTERN = (
    r"(?i)^.*(?:factorio|异星|太空时代|space\s*age|spaceage).*(?:下载|安装包).*(?:链接|地址)?$"
)


factorio_download_matcher = on_regex(
    FACTORIO_DOWNLOAD_PATTERN,
    priority=14,
    block=True,
    rule=direct_command_rule(),
)


@factorio_download_matcher.handle()
async def handle_factorio_download(event: MessageEvent) -> None:
    try:
        link = await asyncio.to_thread(
            FactorioDownloadService().fetch_space_age_windows_link
        )
    except FactorioDownloadError as exc:
        await factorio_download_matcher.finish(
            "Factorio: Space Age Windows 安装包请从 Factorio 官网账号下载页获取。"
            f"本轮没有生成群聊下载直链：{exc}"
        )
    await factorio_download_matcher.finish(render_factorio_download_safety_message(link.version))
