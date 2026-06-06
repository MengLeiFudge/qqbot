from __future__ import annotations

from nonebot import on_regex
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.adapters.onebot.v11 import MessageEvent

from qqbot.services.async_tools import run_blocking
from qqbot.services.command_guard import direct_command_rule
from qqbot.features.lolicon.service import (
    LoliconImageStore,
    LoliconMode,
    fetch_lolicon_items,
    parse_lolicon_command,
)
from qqbot.config import load_settings
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


async def fetch_lolicon_items_async(mode: LoliconMode, num: int, tags: list[str]):
    return await run_blocking(fetch_lolicon_items, mode, num, tags)


async def prepare_lolicon_item_async(store: LoliconImageStore, item):
    return await run_blocking(store.prepare_item, item)


@lolicon_admin_matcher.handle()
async def handle_lolicon_admin(event: MessageEvent) -> None:
    store = get_settings_store()
    if not store.is_bot_admin(int(event.get_user_id())):
        await lolicon_admin_matcher.finish("只有作者才能调整美图配置哦！")

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
    settings = load_settings()
    if hasattr(event, "group_id"):
        group_r18, show_image = store.get_lolicon_config(event.group_id)
        if command.mode != LoliconMode.NON_R18 and not group_r18:
            await lolicon_matcher.finish("本群当前设置为群内只能查看非R18图片！\n请私聊发送指令QwQ")
    else:
        show_image = True

    items = await fetch_lolicon_items_async(command.mode, command.num, command.tags)
    if not items:
        await lolicon_matcher.finish("没有找到符合你要求的图片呢QAQ\n尝试减少一些tag吧！")

    image_store = LoliconImageStore(settings.data_root)
    for index, item in enumerate(items, start=1):
        item = await prepare_lolicon_item_async(image_store, item)
        message = Message(
            [
                MessageSegment.text(f"图片索引：{index} / {len(items)}\n"),
            ]
        )
        if show_image or not item.r18:
            image_source = item.local_path.as_posix() if item.local_path is not None else item.url
            message += MessageSegment.image(image_source)
        else:
            message += MessageSegment.text(item.url)
        message += MessageSegment.text(
            f"\n{item.title}(PID {item.pid})\nby {item.author}(UID {item.uid})"
            f"\nTags: {', '.join(item.tags) if item.tags else '-'}"
        )
        await lolicon_matcher.send(message)
