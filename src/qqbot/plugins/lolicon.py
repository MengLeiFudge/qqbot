from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from nonebot import on_regex
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.adapters.onebot.v11 import MessageEvent

from qqbot.services.async_tools import run_blocking
from qqbot.services.command_guard import direct_command_rule
from qqbot.services.lolicon_service import LoliconMode, parse_lolicon_command, parse_lolicon_response
from qqbot.services.settings_store import get_settings_store

lolicon_admin_matcher = on_regex(
    r"^[开关](群色图|图片显示)$",
    priority=12,
    block=True,
    rule=direct_command_rule(),
)
lolicon_matcher = on_regex(
    r"^(来点)?([美色涩蛇]图|混合).*",
    priority=90,
    block=True,
    rule=direct_command_rule(),
)


def fetch_lolicon_items(mode: LoliconMode, num: int, tags: list[str]):
    query = {
        "r18": mode.value,
        "num": min(max(num, 1), 20),
        "size": "original",
    }
    if tags:
        query["tag"] = tags
    url = "https://api.lolicon.app/setu/v2?" + urlencode(query, doseq=True)
    request = Request(url, headers={"User-Agent": "qqbot/0.1"})
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return parse_lolicon_response(payload)


async def fetch_lolicon_items_async(mode: LoliconMode, num: int, tags: list[str]):
    return await run_blocking(fetch_lolicon_items, mode, num, tags)


@lolicon_admin_matcher.handle()
async def handle_lolicon_admin(event: MessageEvent) -> None:
    store = get_settings_store()
    if not store.is_bot_admin(int(event.get_user_id())):
        await lolicon_admin_matcher.finish("只有Bot管理员才能调整美图配置哦！")

    text = event.get_plaintext().strip()
    group_r18, show_image = store.get_lolicon_config(getattr(event, "group_id", 0))
    if text == "开群色图":
        store.set_lolicon_config(getattr(event, "group_id", 0), True, show_image)
        await lolicon_admin_matcher.finish("已开启群色图！")
    if text == "关群色图":
        store.set_lolicon_config(getattr(event, "group_id", 0), False, show_image)
        await lolicon_admin_matcher.finish("已关闭群色图！")
    if text == "开图片显示":
        store.set_lolicon_config(getattr(event, "group_id", 0), group_r18, True)
        await lolicon_admin_matcher.finish(
            "已开启图片显示！\n注意，开启此功能极有可能导致无法接收到消息！\n即使开启，r18图片也不会有缩略图显示~"
        )
    if text == "关图片显示":
        store.set_lolicon_config(getattr(event, "group_id", 0), group_r18, False)
        await lolicon_admin_matcher.finish("已关闭图片显示！")


@lolicon_matcher.handle()
async def handle_lolicon(event: MessageEvent) -> None:
    command = parse_lolicon_command(event.get_plaintext().strip())
    if command is None:
        return

    store = get_settings_store()
    if hasattr(event, "group_id"):
        group_r18, show_image = store.get_lolicon_config(event.group_id)
        if command.mode != LoliconMode.NON_R18 and not group_r18:
            await lolicon_matcher.finish("本群当前设置为群内只能查看非R18图片！\n请私聊发送指令QwQ")
    else:
        show_image = True

    items = await fetch_lolicon_items_async(command.mode, command.num, command.tags)
    if not items:
        await lolicon_matcher.finish("没有找到符合你要求的图片呢QAQ\n尝试减少一些tag吧！")

    for index, item in enumerate(items, start=1):
        message = Message(
            [
                MessageSegment.text(f"图片索引：{index} / {len(items)}\n"),
            ]
        )
        if show_image or not item.r18:
            message += MessageSegment.image(item.url)
        else:
            message += MessageSegment.text(item.url)
        message += MessageSegment.text(
            f"\n{item.title}(PID {item.pid})\nby {item.author}(UID {item.uid})"
        )
        await lolicon_matcher.send(message)
