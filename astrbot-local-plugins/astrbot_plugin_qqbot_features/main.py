from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import os
from pathlib import Path
import random
import re
import sys
import time
import tomllib
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import HTTPRedirectHandler, Request, build_opener

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.event import filter
from astrbot.api.message_components import At, Image, Plain, Poke
from astrbot.api.star import Context, Star, register
from astrbot.core.star.filter.event_message_type import EventMessageType

from .menu_image import render_feature_menu_image
from .menu_image import render_overview_menu_image
from .twin_poke import should_follow_poke_notice


FACTORIO_DOWNLOAD_PATTERN = (
    r"(?i)^.*(?:factorio|异星|太空时代|space\s*age|spaceage).*(?:下载|安装包).*(?:链接|地址)?$"
)
MENU_PATTERN = r"^(?:菜单|帮助|指令)$"
FEATURE_MENU_PATTERN = r"^菜单\s*(?!\d+$)\S+$"
GROUP_FILE_CLEANUP_PATTERN = r"^(?:通知)?(?:大家|全员|群友)?(?:清理|整理)(?:群)?文件$|^(?:群)?文件(?:清理|整理)(?:通知)?$"
LOLICON_ADMIN_PATTERN = r"^[开关](?:群色图|图片显示)$"
LOLICON_PATTERN = r"^(?:来点)?(?:[美色涩蛇]图|混合).*$"
ARC_RECOMMEND_PATTERN = r"^arctj\s*[0-9]+(?:\.[0-9]+)?$"
ARC_ACTIVITY_PATTERN = r"^arc(?:hd|tz)$"
ARC_APK_UPDATE_PATTERN = r"^(?:xz|arcxz)$"
ARC_GUESS_START_PATTERN = r"^(?:arczm|zm)(?:\s*[1-9][0-9]*)?$"
ARC_GUESS_ART_START_PATTERN = r"(?i)^(?:arcqh|qh)(?:\s*(?:[1-9][0-9]*|max))?$"
ARC_GUESS_ART_TILE_PATTERN = r"^arcqh\s*(?:bt|补图)$"
ARC_GUESS_REVEAL_PATTERN = r"^(?:arcjx|jx)$"
SHAPEZ_PATTERN = r"^(?:i|view|chart|chart1|chart2|path|path1|path2|p|puzzle|puzzle1|puzzle2) .*$"
KUN_PATTERN = (
    r"^(?:养鲲|摸鲲|抓鲲|捕鲲|属性|洗练.+[0-9]+|查看.*|等级排行(?:榜)?|财富排行(?:榜)?|"
    r"萌泪币排行(?:榜)?|金钱排行(?:榜)?|道具|背包|命名.+|商城|(?:购买|买|出售|卖).+|签到|"
    r"设置重置时间 *[0-9]+|[开关]新赛季提示|.*赠送.*|赠送全部 *[0-9]+|boss|Boss|查看boss|"
    r"查看Boss|查看boss属性|查看Boss属性|挑战|进击.*|(?:更改|修改).+[0-9]+)$"
)
SAKURA_PATTERN = (
    r"^(?:落樱之都|更新日志|玩法|注册.+|改名.+|个人信息|加经验[0-9]+|嘤[0-9]+|"
    r"恢复|回复|加[0-9]+(?:力量|智力|体质|敏捷|魅力))$"
)
REREAD_COOLDOWN_SECONDS = 120.0
FEATURE_MODE_ENV = "QQBOT_ASTRBOT_FEATURE_MODE"
COMMAND_OWNER_ENV = "QQBOT_ASTRBOT_COMMAND_OWNER"
FEATURE_MODE_DUAL = "dual"
FEATURE_MODE_FULL = "full"
FEATURE_MODES = {FEATURE_MODE_DUAL, FEATURE_MODE_FULL}
NONEBOT2_HOST = "127.0.0.1"
NONEBOT2_PORT = 8080
OWNER_QQ = "605738729"
DEFAULT_COMMAND_OWNER_QQ = "2629227874"


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    name: str
    aliases: tuple[str, ...] = ()
    status: str = "已移植"
    lines: tuple[str, ...] = ()


FEATURES: tuple[FeatureSpec, ...] = (
    FeatureSpec(
        name="群管助手",
        aliases=("群管", "群管理", "群功能"),
        lines=(
            "通知清理文件：作者或机器人自身限定，统计超过一周的外层群文件并按大小禁言上传者",
        ),
    ),
    FeatureSpec(
        name="好友邀请处理",
        aliases=("好友申请", "邀请入群", "社交事件"),
        status="部分移植",
        lines=(
            "收到好友申请或入群邀请时记录日志；自动同意属于副作用动作，未默认启用",
        ),
    ),
    FeatureSpec(
        name="入群欢迎",
        aliases=("欢迎", "新人欢迎", "社交事件"),
        lines=("新成员入群时发送欢迎消息；机器人自身入群时发送自我介绍",),
    ),
    FeatureSpec(
        name="戳一戳响应",
        aliases=("戳一戳", "反戳", "社交事件"),
        lines=("戳机器人时按概率回复和反戳；戳群成员时小概率跟戳",),
    ),
    FeatureSpec(
        name="复读",
        aliases=("随机复读",),
        lines=("群里连续出现相同纯文本消息时概率复读，复读后短时间内冷却",),
    ),
    FeatureSpec(
        name="Lolicon美图",
        aliases=("Lolicon", "美图", "色图"),
        lines=(
            "来点美图 / 色图 / 混合：复用 bot1 Lolicon API、图片缓存和元数据存储",
            "开群色图 / 关群色图：作者限定，控制当前群是否允许 R18",
            "开图片显示 / 关图片显示：作者限定，控制 R18 结果是否直接发图",
        ),
    ),
    FeatureSpec(
        name="养鲲",
        aliases=("鲲",),
        lines=(
            "摸鲲 / 养鲲 / 抓鲲 / 捕鲲：私聊创建或获取鲲",
            "属性 / 背包 / 商城 / 签到 / 挑战 / 排行 / 进击 / 赠送：复用 bot1 存档与状态机",
        ),
    ),
    FeatureSpec(
        name="落樱之都",
        aliases=("樱花", "落樱"),
        status="基础玩法已移植",
        lines=("落樱之都 / 注册 / 改名 / 个人信息 / 加经验 / 嘤 / 加点 / 恢复：复用 bot1 存档",),
    ),
    FeatureSpec(
        name="Arc",
        aliases=("Arc查询", "Arc狼人杀", "Arc吃鸡", "arcaea"),
        status="部分移植",
        lines=(
            "arctj10.5：按 PTT 推荐谱面，复用 bot1 本地 Arcaea 曲库和定数缓存",
            "archd / arctz：查看当前活动梯子",
            "zm / arczm：字母猜歌；qh / arcqh：曲绘猜歌；jx / arcjx：揭晓",
            "xz / arcxz：作者限定，查询并下载最新 c 版安装包",
        ),
    ),
    FeatureSpec(
        name="Factorio",
        aliases=("异星工厂", "太空时代", "Space Age", "spaceage"),
        lines=("Factorio下载链接 / 异星下载链接：获取 Space Age Windows 安装包下载链接",),
    ),
    FeatureSpec(
        name="异形工厂",
        aliases=("shapez",),
        lines=("i/view/chart/path：渲染 shapez 短代码图片；p/puzzle 在线谜题仍提示未配置 token",),
    ),
    FeatureSpec(
        name="RightCodes生图",
        aliases=("生图", "画图", "RightCodes"),
        lines=(
            "棉花糖生图 [模型名] 提示词：提交 RightCodes 生图任务",
            "生图模型 / 生图价格：查看模型、价格和积分消耗",
            "查看积分 / balance / points：查询当前 QQ 的生图积分",
        ),
    ),
    FeatureSpec(
        name="AI对话",
        aliases=("AI测试", "主动接话", "长期记忆"),
        status="使用 AstrBot 原生链路",
        lines=("bot1 的 NoneBot2 AI runtime 不直接迁移；bot2 使用 AstrBot provider/persona/记忆插件",),
    ),
)


@dataclass(frozen=True, slots=True)
class FactorioCredentials:
    username: str
    token: str


@dataclass(frozen=True, slots=True)
class FactorioDownloadLink:
    version: str
    url: str


@dataclass(frozen=True, slots=True)
class ShapezRenderResult:
    image_path: Path
    text: str


@dataclass(frozen=True, slots=True)
class LoliconRenderResult:
    prefix: str
    suffix: str
    image_path: Path | None = None
    image_url: str = ""
    image_text: str = ""


@dataclass(frozen=True, slots=True)
class ArcRecommendationResult:
    text: str
    image_path: Path | None = None


class FactorioDownloadError(RuntimeError):
    pass


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


class RereadRepeatState:
    def __init__(
        self,
        *,
        cooldown_seconds: float = REREAD_COOLDOWN_SECONDS,
        rng: random.Random | None = None,
    ) -> None:
        self._groups: dict[str, dict[str, object]] = {}
        self._cooldown_seconds = max(0.0, float(cooldown_seconds))
        self._rng = rng or random.Random()

    def observe(self, group_id: str, text: str, *, message_id: str = "") -> bool:
        normalized = normalize_reread_key(text)
        if not normalized:
            return False
        state = self._groups.setdefault(
            group_id,
            {
                "last_key": "",
                "consecutive_count": 0,
                "repeated_current_run": False,
                "cooldown_key": "",
                "cooldown_until": 0.0,
                "last_message_id": "",
            },
        )
        if message_id and state.get("last_message_id") == message_id:
            return False
        state["last_message_id"] = message_id

        if state.get("last_key") != normalized:
            state["last_key"] = normalized
            state["consecutive_count"] = 1
            state["repeated_current_run"] = False
            return False

        consecutive_count = int(state.get("consecutive_count") or 0) + 1
        state["consecutive_count"] = consecutive_count
        now = time.monotonic()
        in_cooldown = (
            state.get("cooldown_key") == normalized
            and now < float(state.get("cooldown_until") or 0.0)
        )
        if bool(state.get("repeated_current_run")) or in_cooldown:
            return False
        if self._rng.random() >= reread_probability(consecutive_count):
            return False

        state["repeated_current_run"] = True
        state["cooldown_key"] = normalized
        state["cooldown_until"] = now + self._cooldown_seconds
        return True


@register(
    "astrbot_plugin_qqbot_features",
    "local",
    "Selected qqbot NoneBot2 features migrated as local AstrBot plugin handlers.",
    "0.8.0",
)
class QQBotFeaturesPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self._feature_mode = read_feature_mode(config)
        self._reread_state = RereadRepeatState()
        self._arc_apk_update_manager = None
        logger.info(
            "[QQBotFeatures] migrated feature plugin loaded, mode=%s",
            self._feature_mode,
        )

    @filter.regex(MENU_PATTERN)
    async def menu(self, event: AstrMessageEvent):
        if not _should_handle_migrated_command(event, self._feature_mode):
            return
        try:
            image_path = render_overview_menu_image(
                features=FEATURES,
                feature_mode=self._feature_mode,
                output_dir=get_menu_image_cache_root(),
            )
            yield event.chain_result([Image.fromFileSystem(str(image_path))])
        except Exception as exc:
            logger.exception("[QQBotFeatures] failed to render overview menu image: %s", exc)
            yield event.plain_result(build_menu_text(self._feature_mode))
        event.stop_event()

    @filter.regex(FEATURE_MENU_PATTERN)
    async def feature_menu(self, event: AstrMessageEvent):
        if not _should_handle_migrated_command(event, self._feature_mode):
            return
        key = re.sub(r"^菜单\s*", "", event.get_message_str().strip(), count=1)
        feature = find_feature(key)
        if feature is None:
            yield event.plain_result("没有这个模块哦！")
            event.stop_event()
            return
        try:
            image_path = render_feature_menu_image(
                feature=feature,
                feature_mode=self._feature_mode,
                output_dir=get_menu_image_cache_root(),
            )
            yield event.chain_result([Image.fromFileSystem(str(image_path))])
        except Exception as exc:
            logger.exception("[QQBotFeatures] failed to render feature menu image: %s", exc)
            yield event.plain_result(build_feature_menu_text(feature))
        event.stop_event()

    @filter.platform_adapter_type("aiocqhttp")
    @filter.regex(GROUP_FILE_CLEANUP_PATTERN)
    async def group_file_cleanup(self, event: AstrMessageEvent):
        if not _should_handle_migrated_command(event, self._feature_mode):
            return
        if event.is_private_chat() or not event.get_group_id():
            yield event.plain_result("群文件清理只能在群聊中使用。")
            event.stop_event()
            return
        if not is_bot_admin_or_self(event):
            return
        if not is_nonebot2_plugin_enabled("group_assistant"):
            return
        try:
            await run_group_file_cleanup(event)
        except Exception as exc:
            yield event.plain_result(f"群文件清理失败：{exc}")
        event.stop_event()

    @filter.regex(FACTORIO_DOWNLOAD_PATTERN)
    async def factorio_download(self, event: AstrMessageEvent):
        if not _should_handle_migrated_command(event, self._feature_mode):
            return
        try:
            link = await asyncio.to_thread(fetch_factorio_space_age_windows_link)
        except FactorioDownloadError as exc:
            yield event.plain_result(f"Factorio: 没获取到 Space Age Windows 下载链接：{exc}")
            event.stop_event()
            return
        yield event.plain_result(
            f"Factorio: Space Age Windows {link.version} 下载链接：\n{link.url}"
        )
        event.stop_event()

    @filter.regex(SHAPEZ_PATTERN)
    async def shapez_render(self, event: AstrMessageEvent):
        if not _should_handle_migrated_command(event, self._feature_mode):
            return
        text = event.get_message_str().strip()
        command, _, argument = text.partition(" ")
        command = command.lower()
        if command in {"p", "puzzle", "puzzle1", "puzzle2"}:
            yield event.plain_result("没获取到 shapez 谜题：在线谜题下载需要 shapez 登录 token，当前未配置。")
            event.stop_event()
            return
        try:
            result = await asyncio.to_thread(render_shapez_command, command, argument)
        except Exception as exc:
            yield event.plain_result(f"shapez 渲染失败：{exc}")
            event.stop_event()
            return
        chain = [Image.fromFileSystem(str(result.image_path)), Plain(result.text)]
        yield event.chain_result(chain)
        event.stop_event()

    @filter.regex(LOLICON_ADMIN_PATTERN)
    async def lolicon_admin(self, event: AstrMessageEvent):
        if not _should_handle_migrated_command(event, self._feature_mode):
            return
        if str(event.get_sender_id()) != get_nonebot2_config_value("bot", "author_qq", "0"):
            yield event.plain_result("只有作者才能调整美图配置哦！")
            event.stop_event()
            return
        if event.is_private_chat() or not event.get_group_id():
            yield event.plain_result("这个指令只能在群聊中使用。")
            event.stop_event()
            return
        response = await asyncio.to_thread(
            handle_lolicon_admin_command,
            int(event.get_group_id()),
            event.get_message_str().strip(),
        )
        yield event.plain_result(response)
        event.stop_event()

    @filter.regex(LOLICON_PATTERN)
    async def lolicon_image(self, event: AstrMessageEvent):
        if not _should_handle_migrated_command(event, self._feature_mode):
            return
        try:
            results = await asyncio.to_thread(
                build_lolicon_results,
                event.get_message_str().strip(),
                event.is_private_chat(),
                int(event.get_group_id() or 0),
            )
        except Exception as exc:
            yield event.plain_result(f"Lolicon 美图获取失败：{exc}")
            event.stop_event()
            return
        if not results:
            return
        for result in results:
            chain = [Plain(result.prefix)]
            if result.image_path:
                chain.append(Image.fromFileSystem(str(result.image_path)))
            elif result.image_url:
                chain.append(Image.fromURL(result.image_url))
            elif result.image_text:
                chain.append(Plain(result.image_text))
            chain.append(Plain(result.suffix))
            yield event.chain_result(chain)
        event.stop_event()

    @filter.regex(ARC_RECOMMEND_PATTERN)
    async def arc_recommend(self, event: AstrMessageEvent):
        if not _should_handle_migrated_command(event, self._feature_mode):
            return
        try:
            result = await asyncio.to_thread(
                build_arc_recommendation,
                event.get_message_str().strip(),
            )
        except Exception as exc:
            yield event.plain_result(f"Arc 推荐失败：{exc}")
            event.stop_event()
            return
        if result.image_path is not None:
            yield event.chain_result(
                [Image.fromFileSystem(str(result.image_path)), Plain(f"\n{result.text}")]
            )
        else:
            yield event.plain_result(result.text)
        event.stop_event()

    @filter.regex(ARC_ACTIVITY_PATTERN)
    async def arc_activity(self, event: AstrMessageEvent):
        if not _should_handle_migrated_command(event, self._feature_mode):
            return
        try:
            messages = await asyncio.to_thread(build_arc_activity_messages)
        except Exception as exc:
            yield event.plain_result(f"Arc 活动梯子查询失败：{exc}")
            event.stop_event()
            return
        for message in messages or ["当前没有活动梯子。"]:
            yield event.plain_result(message)
        event.stop_event()

    @filter.regex(ARC_APK_UPDATE_PATTERN)
    async def arc_apk_update(self, event: AstrMessageEvent):
        if not _should_handle_migrated_command(event, self._feature_mode):
            return
        if str(event.get_sender_id()) != get_nonebot2_config_value("bot", "author_qq", "0"):
            yield event.plain_result("只有作者可以使用这个指令。")
            event.stop_event()
            return
        try:
            manager = get_arc_apk_update_manager(self)
            message = await manager.query_and_update()
        except Exception as exc:
            yield event.plain_result(f"Arc 安装包下载查询失败：{exc}")
            event.stop_event()
            return
        yield event.plain_result(message)
        event.stop_event()

    @filter.regex(ARC_GUESS_START_PATTERN)
    async def arc_guess_start(self, event: AstrMessageEvent):
        if not _should_handle_migrated_command(event, self._feature_mode):
            return
        if event.is_private_chat() or not event.get_group_id():
            yield event.plain_result("Arc 猜歌只能在群聊中开始。")
            event.stop_event()
            return
        try:
            result = await asyncio.to_thread(
                start_arc_guess_game,
                int(event.get_group_id()),
                event.get_message_str().strip(),
            )
        except Exception as exc:
            yield event.plain_result(f"Arc 猜歌开始失败：{exc}")
            event.stop_event()
            return
        yield event.plain_result(str(result))
        event.stop_event()

    @filter.regex(ARC_GUESS_ART_START_PATTERN)
    async def arc_guess_art_start(self, event: AstrMessageEvent):
        if not _should_handle_migrated_command(event, self._feature_mode):
            return
        if event.is_private_chat() or not event.get_group_id():
            yield event.plain_result("Arc 猜歌只能在群聊中开始。")
            event.stop_event()
            return
        try:
            result = await asyncio.to_thread(
                start_or_open_arc_art_guess,
                int(event.get_group_id()),
                event.get_message_str().strip(),
            )
        except Exception as exc:
            yield event.plain_result(f"Arc 曲绘猜歌失败：{exc}")
            event.stop_event()
            return
        yield build_arc_guess_event_result(event, result)
        event.stop_event()

    @filter.regex(ARC_GUESS_ART_TILE_PATTERN)
    async def arc_guess_art_tile(self, event: AstrMessageEvent):
        if not _should_handle_migrated_command(event, self._feature_mode):
            return
        if event.is_private_chat() or not event.get_group_id():
            yield event.plain_result("Arc 猜歌只能在群聊中进行。")
            event.stop_event()
            return
        try:
            result = await asyncio.to_thread(
                open_arc_art_guess_tile,
                int(event.get_group_id()),
            )
        except Exception as exc:
            yield event.plain_result(f"Arc 曲绘补图失败：{exc}")
            event.stop_event()
            return
        yield build_arc_guess_event_result(event, result)
        event.stop_event()

    @filter.regex(ARC_GUESS_REVEAL_PATTERN)
    async def arc_guess_reveal(self, event: AstrMessageEvent):
        if not _should_handle_migrated_command(event, self._feature_mode):
            return
        if event.is_private_chat() or not event.get_group_id():
            yield event.plain_result("Arc 猜歌只能在群聊中进行。")
            event.stop_event()
            return
        try:
            result = await asyncio.to_thread(reveal_arc_guess, int(event.get_group_id()))
        except Exception as exc:
            yield event.plain_result(f"Arc 猜歌揭晓失败：{exc}")
            event.stop_event()
            return
        yield build_arc_guess_event_result(event, result)
        event.stop_event()

    @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
    async def arc_guess_session_answer(self, event: AstrMessageEvent):
        if not (allow_passive_events(self._feature_mode) or _is_direct_or_private(event)):
            return
        if event.get_sender_id() == event.get_self_id():
            return
        text = event.get_message_str().strip()
        if not text or not event.get_group_id():
            return
        try:
            result = await asyncio.to_thread(
                handle_arc_guess_session_text,
                int(event.get_group_id()),
                text,
                get_player_name(event),
            )
        except Exception as exc:
            logger.warning("[QQBotFeatures] Arc guess session handling failed: %s", exc)
            return
        if result is None:
            return
        yield build_arc_guess_event_result(event, result)
        event.stop_event()

    @filter.regex(KUN_PATTERN)
    async def kun_command(self, event: AstrMessageEvent):
        if not _should_handle_migrated_command(event, self._feature_mode):
            return
        response = await asyncio.to_thread(handle_kun_command, event)
        if response is None:
            return
        yield event.plain_result(response)
        event.stop_event()

    @filter.regex(SAKURA_PATTERN)
    async def sakura_command(self, event: AstrMessageEvent):
        if not _should_handle_migrated_command(event, self._feature_mode):
            return
        response = await asyncio.to_thread(handle_sakura_command, event)
        if response is None:
            return
        yield event.plain_result(response)
        event.stop_event()

    @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
    async def reread(self, event: AstrMessageEvent):
        if not allow_passive_events(self._feature_mode):
            return
        text = event.get_message_str().strip()
        if should_skip_reread(event, text):
            return
        message_id = str(getattr(event.message_obj, "message_id", "") or "")
        if not self._reread_state.observe(event.get_group_id(), text, message_id=message_id):
            return
        yield event.plain_result(text)

    @filter.platform_adapter_type("aiocqhttp")
    @filter.event_message_type(EventMessageType.ALL)
    async def onebot_social_events(self, event: AstrMessageEvent):
        raw = _raw_event_dict(event)
        if not raw:
            return
        post_type = str(raw.get("post_type") or "")
        if post_type == "notice":
            if not allow_passive_events(self._feature_mode):
                return
            async for result in self._handle_onebot_notice(event, raw):
                yield result
            return
        if post_type == "request":
            self._log_onebot_request(raw)

    async def _handle_onebot_notice(self, event: AstrMessageEvent, raw: dict):
        notice_type = str(raw.get("notice_type") or "")
        sub_type = str(raw.get("sub_type") or "")
        if notice_type == "group_increase":
            user_id = str(raw.get("user_id") or "")
            self_id = str(raw.get("self_id") or event.get_self_id())
            if not event.get_group_id() or not user_id:
                return
            if user_id == self_id:
                yield event.plain_result("棉花糖已经加入群聊啦，主人喵！")
            else:
                yield event.chain_result([_at(user_id), Plain(" 欢迎大佬喵！群地位+1")])
            return
        if notice_type == "notify" and sub_type == "poke":
            async for result in self._handle_poke_notice(event, raw):
                yield result

    async def _handle_poke_notice(self, event: AstrMessageEvent, raw: dict):
        self_id = str(raw.get("self_id") or event.get_self_id())
        user_id = str(raw.get("user_id") or "")
        target_id = str(raw.get("target_id") or "")
        if not should_follow_poke_notice(self_id=self_id, user_id=user_id, target_id=target_id):
            return
        roll = random.randint(0, 99)
        if roll > 25:
            return
        if target_id == self_id:
            yield event.plain_result("谁让你戳我的？我戳！")
            if roll <= 5:
                await asyncio.sleep(1.0)
                yield event.chain_result([Plain("我再戳！"), Poke(id=user_id)])
                if roll <= 1:
                    await asyncio.sleep(1.0)
                    yield event.chain_result([Plain("我还戳！"), Poke(id=user_id)])
            return
        yield event.chain_result([Poke(id=target_id)])

    def _log_onebot_request(self, raw: dict) -> None:
        request_type = str(raw.get("request_type") or "")
        sub_type = str(raw.get("sub_type") or "")
        user_id = str(raw.get("user_id") or "")
        group_id = str(raw.get("group_id") or "")
        if request_type == "friend":
            logger.info("[QQBotFeatures] friend request observed: user_id=%s", user_id)
            return
        if request_type == "group" and sub_type == "invite":
            logger.info(
                "[QQBotFeatures] group invite request observed: group_id=%s user_id=%s",
                group_id,
                user_id,
            )


def _is_direct_or_private(event: AstrMessageEvent) -> bool:
    return event.is_private_chat() or bool(getattr(event, "is_at_or_wake_command", False))


def _should_handle_migrated_command(event: AstrMessageEvent, feature_mode: str) -> bool:
    if _is_direct_or_private(event):
        return True
    if feature_mode != FEATURE_MODE_FULL:
        return False
    return str(event.get_self_id() or "") == read_command_owner_qq()


def read_command_owner_qq() -> str:
    return str(os.environ.get(COMMAND_OWNER_ENV) or DEFAULT_COMMAND_OWNER_QQ).strip()


def _raw_event_dict(event: AstrMessageEvent) -> dict:
    raw = getattr(event.message_obj, "raw_message", None)
    if isinstance(raw, dict):
        return raw
    try:
        return dict(raw)
    except Exception:
        return {}


def _at(user_id: str):
    return At(qq=user_id)


def find_feature(key: str) -> FeatureSpec | None:
    normalized = key.strip().lower()
    if not normalized:
        return None
    for feature in FEATURES:
        names = (feature.name, *feature.aliases)
        normalized_names = [name.lower() for name in names]
        if normalized in normalized_names:
            return feature
        if any(normalized in name or name in normalized for name in normalized_names):
            return feature
    return None


def build_menu_text(feature_mode: str = FEATURE_MODE_DUAL) -> str:
    lines = ["NoneBot2 已迁移功能清单：", build_feature_mode_text(feature_mode)]
    for feature in FEATURES:
        lines.append(f"- {feature.name}：{feature.status}")
    lines.append("发送 菜单模块名 查看具体命令，例如 菜单Factorio。")
    return "\n".join(lines)


def build_feature_menu_text(feature: FeatureSpec) -> str:
    lines = [f"{feature.name}：{feature.status}"]
    lines.extend(feature.lines)
    return "\n".join(lines)


def read_feature_mode(config=None) -> str:
    source = FEATURE_MODE_ENV
    raw = os.environ.get(FEATURE_MODE_ENV, "").strip().lower()
    if not raw and config is not None:
        raw = str(config.get("feature_mode", "") or "").strip().lower()
        source = "plugin_config.feature_mode"
    if not raw:
        return FEATURE_MODE_DUAL
    if raw in FEATURE_MODES:
        if raw == FEATURE_MODE_FULL and is_nonebot2_port_open():
            logger.warning(
                "[QQBotFeatures] requested full mode but NoneBot2 is reachable at %s:%s, fallback to %s",
                NONEBOT2_HOST,
                NONEBOT2_PORT,
                FEATURE_MODE_DUAL,
            )
            return FEATURE_MODE_DUAL
        return raw
    logger.warning(
        "[QQBotFeatures] invalid %s=%r, fallback to %s",
        source,
        raw,
        FEATURE_MODE_DUAL,
    )
    return FEATURE_MODE_DUAL


def allow_passive_events(feature_mode: str) -> bool:
    return feature_mode == FEATURE_MODE_FULL


def is_bot_admin_or_self(event: AstrMessageEvent) -> bool:
    sender_id = str(event.get_sender_id())
    return sender_id == str(get_author_qq()) or sender_id == str(event.get_self_id())


def is_nonebot2_plugin_enabled(plugin_id: str) -> bool:
    ensure_nonebot2_services_path()
    from qqbot.services.settings_store import SettingsStore

    return SettingsStore(get_nonebot2_data_root(), get_author_qq()).get_plugin_enabled(plugin_id)


def is_nonebot2_port_open() -> bool:
    request = Request(f"http://{NONEBOT2_HOST}:{NONEBOT2_PORT}/admin/api/status")
    try:
        with build_opener().open(request, timeout=1.0) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and "connected_bot_count" in payload and "onebot_connected" in payload


def build_feature_mode_text(feature_mode: str) -> str:
    if feature_mode == FEATURE_MODE_FULL:
        return "当前模式：full，AstrBot 接管已迁移自动事件。"
    return "当前模式：dual，自动事件由 NoneBot2 负责，AstrBot 只响应明确唤醒/私聊命令。"


def should_skip_reread(event: AstrMessageEvent, text: str) -> bool:
    if not text:
        return True
    if getattr(event, "is_at_or_wake_command", False):
        return True
    if looks_like_command(text):
        return True
    if _raw_event_dict(event).get("post_type") != "message":
        return True
    messages = event.get_messages()
    return bool(messages) and not all(isinstance(segment, Plain) for segment in messages)


def looks_like_command(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith(("/", "!", "！", ".", "。")) or bool(
        re.match(r"^[a-zA-Z]{1,16}\b", stripped)
    )


def normalize_reread_key(text: str) -> str:
    return " ".join(str(text).split()).strip()


def reread_probability(consecutive_count: int) -> float:
    if consecutive_count < 2:
        return 0.0
    return min(0.8, 0.2 + (consecutive_count - 2) * 0.15)


class AstrBotOneBotApi:
    def __init__(self, event: AstrMessageEvent) -> None:
        self._bot = getattr(event, "bot", None)
        self.self_id = str(event.get_self_id() or "")
        if self._bot is None:
            raise RuntimeError("当前事件没有 aiocqhttp bot 实例")

    async def call_api(self, action: str, **kwargs):
        return await self._bot.call_action(action, **kwargs)


async def run_group_file_cleanup(event: AstrMessageEvent) -> dict[str, object]:
    ensure_nonebot2_services_path()
    from qqbot.features.group.file_cleanup_service import (
        ShapezGroupFileCleanupService,
        ShapezGroupFileCleanupStore,
    )

    api = AstrBotOneBotApi(event)
    group_id = int(event.get_group_id())
    service = ShapezGroupFileCleanupService(
        store=ShapezGroupFileCleanupStore(
            get_nonebot2_data_root() / "data" / "shapez_file_cleanup_state.json"
        ),
        group_id=str(group_id),
        timezone_name=get_nonebot2_config_value("bot", "timezone", "Asia/Shanghai"),
    )
    result = await service.scan_and_notify_group(api)
    if result.get("violating_user_count") == 0:
        await api.call_api(
            "send_group_msg",
            group_id=group_id,
            message="当前没有超过一周的外层群文件需要清理。",
        )
    elif result.get("failed_group_message_count"):
        await api.call_api(
            "send_group_msg",
            group_id=group_id,
            message="部分文件清理名单没有发出，对应名单已跳过禁言。",
        )
    return result


def build_arc_recommendation(text: str) -> ArcRecommendationResult:
    ensure_nonebot2_services_path()
    from qqbot.features.arc.alias_service import load_song_titles
    from qqbot.features.arc.constant_service import ArcConstantService
    from qqbot.features.arc.service import ArcService

    ptt = parse_arc_recommend_ptt(text)
    if ptt is None:
        raise ValueError("用法：arctj10.5")
    assets_root = get_arc_assets_root()
    service = ArcService(assets_root)
    constant_service = ArcConstantService(
        get_nonebot2_data_root() / "data" / "arc" / "constants.json"
    )
    song_titles = load_song_titles(assets_root / "官谱" / "songlist")
    constant_service.sync_missing_constants(song_titles)
    constant_cache = constant_service.load_constant_cache()
    chart = service.recommend_chart_by_ptt(ptt, constant_cache)
    return ArcRecommendationResult(
        text=service.build_recommendation_text(ptt, chart),
        image_path=chart.jacket_path,
    )


def build_arc_activity_messages() -> list[str]:
    ensure_nonebot2_services_path()
    from qqbot.features.arc.event_service import ArcEventService

    service = ArcEventService(
        timezone=get_nonebot2_config_value("bot", "timezone", "Asia/Shanghai")
    )
    events = service.fetch_active_events()
    return service.render_event_messages(events)


def start_arc_guess_game(room_id: int, text: str):
    count = parse_arc_guess_start_count(text)
    if count is None:
        raise ValueError("用法：arczm5")
    service = get_arc_guess_service()
    return service.start_game(room_id, count)


def start_or_open_arc_art_guess(room_id: int, text: str):
    service = get_arc_guess_service()
    return service.start_or_open_art_tile(room_id, parse_arc_guess_art_grid_size(text))


def open_arc_art_guess_tile(room_id: int):
    service = get_arc_guess_service()
    return service.start_or_open_art_tile(room_id)


def reveal_arc_guess(room_id: int):
    service = get_arc_guess_service()
    return service.reveal_answers(room_id)


def handle_arc_guess_session_text(room_id: int, text: str, player_name: str):
    service = get_arc_guess_service()
    session = service.get_session(room_id)
    if session is None:
        return None
    if session.mode == "letters":
        letter = parse_arc_open_letter(text)
        if letter is not None:
            return service.open_letter(room_id, letter)
        payload = parse_arc_guess_submission(text)
        if payload is None:
            return None
        question_index, answer = payload
        return service.guess(room_id, question_index, answer, player_name)
    if session.mode == "art":
        answer = parse_arc_guess_art_submission(text)
        if answer is None:
            return None
        if not text.strip().startswith("猜") and not service.is_plausible_answer(answer, session.art_aliases or []):
            return None
        return service.guess_art(room_id, answer, player_name)
    return None


def parse_arc_recommend_ptt(text: str) -> float | None:
    match = re.fullmatch(r"arctj\s*([0-9]+(?:\.[0-9]+)?)", text.strip())
    if match is None:
        return None
    return float(match.group(1))


def parse_arc_guess_start_count(text: str) -> int | None:
    match = re.fullmatch(r"(?:arczm|zm)\s*([1-9][0-9]*)?", text.strip())
    if match is None:
        return None
    if not match.group(1):
        return 10
    return int(match.group(1))


def parse_arc_guess_art_grid_size(text: str) -> int | str | None:
    match = re.fullmatch(r"(?:arcqh|qh)\s*([1-9][0-9]*|max)", text.strip(), re.IGNORECASE)
    if match is None:
        return None
    raw_value = match.group(1).lower()
    if raw_value == "max":
        return "max"
    return int(raw_value)


def parse_arc_open_letter(text: str) -> str | None:
    match = re.fullmatch(r"开\s*(\S)", text.strip())
    if match is None:
        return None
    return match.group(1).lower()


def parse_arc_guess_submission(text: str) -> tuple[int, str] | None:
    match = re.fullmatch(r"(?:猜\s*)?([1-9][0-9]*)\s*(.+)", text.strip())
    if match is None:
        return None
    return int(match.group(1)), match.group(2).strip()


def parse_arc_guess_art_submission(text: str) -> str | None:
    stripped = text.strip()
    if re.fullmatch(r"(?:猜\s*)?[1-9][0-9]*\s*.+", stripped):
        return None
    match = re.fullmatch(r"猜\s*(.+)", stripped)
    if match is not None:
        return match.group(1).strip()
    if stripped.startswith("猜") or is_arc_guess_control_command(stripped):
        return None
    return stripped or None


def is_arc_guess_control_command(text: str) -> bool:
    stripped = text.strip()
    return (
        parse_arc_recommend_ptt(stripped) is not None
        or parse_arc_guess_start_count(stripped) is not None
        or re.fullmatch(ARC_GUESS_ART_START_PATTERN, stripped) is not None
        or re.fullmatch(ARC_GUESS_ART_TILE_PATTERN, stripped) is not None
        or parse_arc_open_letter(stripped) is not None
        or re.fullmatch(ARC_GUESS_REVEAL_PATTERN, stripped) is not None
        or re.fullmatch(ARC_ACTIVITY_PATTERN, stripped) is not None
        or re.fullmatch(ARC_APK_UPDATE_PATTERN, stripped) is not None
    )


def get_arc_apk_update_manager(plugin: QQBotFeaturesPlugin):
    ensure_nonebot2_services_path()
    from qqbot.features.arc.apk_update_service import ArcApkUpdateManager
    from qqbot.features.arc.arcaea_record_apk_downloader import ArcaeaRecordApkDownloader
    from qqbot.features.arc.event_service import _fetch_latest_arc_version

    if plugin._arc_apk_update_manager is None:
        data_root = get_nonebot2_data_root()
        plugin._arc_apk_update_manager = ArcApkUpdateManager(
            state_path=data_root / "data" / "arc" / "background_state.json",
            version_fetcher=_fetch_latest_arc_version,
            downloader=ArcaeaRecordApkDownloader(
                project_root=get_required_nonebot2_config_path(
                    "paths",
                    "arcaea_record_root",
                ),
                target_dir=get_arc_assets_root(),
                maven_command=get_nonebot2_config_value("paths", "arcaea_record_maven", ""),
                java_home=get_nonebot2_config_value("paths", "arcaea_record_java_home", ""),
            ),
            timezone_name=get_nonebot2_config_value("bot", "timezone", "Asia/Shanghai"),
        )
    return plugin._arc_apk_update_manager


def get_arc_guess_service():
    ensure_nonebot2_services_path()
    from qqbot.features.arc.guess_service import ArcGuessService

    data_root = get_nonebot2_data_root()
    return ArcGuessService(
        assets_root=get_arc_assets_root(),
        alias_cache_path=data_root / "data" / "arc" / "guess_aliases.json",
        state_path=data_root / "data" / "arc" / "guess_sessions.json",
    )


def build_arc_guess_event_result(event: AstrMessageEvent, result):
    image_path = getattr(result, "image_path", None)
    text = getattr(result, "text", str(result))
    if image_path is None:
        return event.plain_result(text)
    return event.chain_result([Image.fromFileSystem(str(image_path)), Plain(f"\n{text}")])


def get_arc_assets_root() -> Path:
    raw = get_nonebot2_config_value("paths", "arc_assets_root", "")
    if raw:
        return Path(raw)
    return get_workspace_root() / "data" / "arc"


def get_required_nonebot2_config_path(section: str, key: str) -> Path:
    raw = get_nonebot2_config_value(section, key, "").strip()
    if not raw:
        raise RuntimeError(f"缺少 NoneBot2 配置 {section}.{key}")
    return Path(raw)


def render_shapez_command(command: str, argument: str) -> ShapezRenderResult:
    ensure_nonebot2_services_path()
    from qqbot.features.shapez.service import render_shape_chart, render_shape_code, render_shape_path

    data_root = get_nonebot2_data_root()
    if command in {"path", "path1", "path2"}:
        tree, output, path_text = render_shape_path(data_root, argument)
        return ShapezRenderResult(
            image_path=output,
            text=f"\n短代码：{tree.shortcode}\n{path_text}",
        )
    if command in {"chart", "chart1", "chart2"}:
        shape, output, shape_text = render_shape_chart(data_root, argument)
        return ShapezRenderResult(
            image_path=output,
            text=f"\n短代码：{shape.short_key}\n{shape_text}",
        )
    shape, output = render_shape_code(data_root, argument)
    return ShapezRenderResult(image_path=output, text=f"\n短代码：{shape.short_key}")


def handle_lolicon_admin_command(group_id: int, text: str) -> str:
    ensure_nonebot2_services_path()
    from qqbot.services.settings_store import SettingsStore

    store = SettingsStore(get_nonebot2_data_root(), get_author_qq())
    group_r18, show_image = store.get_lolicon_config(group_id)
    if text == "开群色图":
        store.set_lolicon_config(group_id, True, show_image)
        return "已开启群色图！"
    if text == "关群色图":
        store.set_lolicon_config(group_id, False, show_image)
        return "已关闭群色图！"
    if text == "开图片显示":
        store.set_lolicon_config(group_id, group_r18, True)
        return "已开启图片显示！\n注意，开启此功能极有可能导致无法接收到消息！\n即使开启，r18图片也不会有缩略图显示~"
    if text == "关图片显示":
        store.set_lolicon_config(group_id, group_r18, False)
        return "已关闭图片显示！"
    return "未知美图配置指令。"


def build_lolicon_results(text: str, is_private: bool, group_id: int = 0) -> list[LoliconRenderResult]:
    ensure_nonebot2_services_path()
    from qqbot.features.lolicon.service import (
        LoliconImageStore,
        LoliconMode,
        fetch_lolicon_items,
        parse_lolicon_command,
    )
    from qqbot.services.settings_store import SettingsStore

    command = parse_lolicon_command(text)
    if command is None:
        return []
    show_image = True
    if not is_private:
        group_r18, show_image = SettingsStore(
            get_nonebot2_data_root(),
            get_author_qq(),
        ).get_lolicon_config(group_id)
        if command.mode != LoliconMode.NON_R18 and not group_r18:
            return [
                LoliconRenderResult(
                    prefix="",
                    suffix="本群当前设置为群内只能查看非R18图片！\n请私聊发送指令QwQ",
                )
            ]
    items = fetch_lolicon_items(command.mode, command.num, command.tags)
    if not items:
        return [
            LoliconRenderResult(
                prefix="",
                suffix="没有找到符合你要求的图片呢QAQ\n尝试减少一些tag吧！",
            )
        ]
    store = LoliconImageStore(get_nonebot2_data_root())
    results: list[LoliconRenderResult] = []
    for index, item in enumerate(items, start=1):
        prepared = store.prepare_item(item)
        should_send_image = show_image or not prepared.r18
        image_path = prepared.local_path if should_send_image and prepared.local_path is not None else None
        image_url = prepared.url if should_send_image and image_path is None else ""
        image_text = "" if should_send_image else prepared.url
        results.append(
            LoliconRenderResult(
                prefix=f"图片索引：{index} / {len(items)}\n",
                image_path=image_path,
                image_url=image_url,
                image_text=image_text,
                suffix=(
                    f"\n{prepared.title}(PID {prepared.pid})\nby {prepared.author}(UID {prepared.uid})"
                    f"\nTags: {', '.join(prepared.tags) if prepared.tags else '-'}"
                ),
            )
        )
    return results


def get_author_qq() -> int:
    raw = get_nonebot2_config_value("bot", "author_qq", OWNER_QQ)
    try:
        return int(raw)
    except ValueError:
        return int(OWNER_QQ)


def handle_kun_command(event: AstrMessageEvent) -> str | None:
    ensure_nonebot2_services_path()
    from qqbot.features.kun.service import KunService

    service = KunService(get_nonebot2_data_root() / "data" / "kun" / "users.json")
    at_ids = [int(segment.qq) for segment in event.get_messages() if isinstance(segment, At) and str(segment.qq).isdigit()]
    return service.handle_command(
        event.get_message_str().strip(),
        int(event.get_sender_id()),
        int(read_event_time_seconds(event) * 1000),
        is_group=not event.is_private_chat(),
        at_id=at_ids[0] if at_ids else None,
        is_admin=str(event.get_sender_id()) == OWNER_QQ,
        group_id=int(event.get_group_id() or 0),
        resolve_display_name=resolve_display_name,
    )


def handle_sakura_command(event: AstrMessageEvent) -> str | None:
    ensure_nonebot2_services_path()
    from qqbot.features.sakura.service import SakuraService

    text = event.get_message_str().strip()
    user_id = int(event.get_sender_id())
    service = SakuraService(get_nonebot2_data_root() / "data" / "sakura" / "players.json")
    player = service.get_player(user_id)

    if text == "落樱之都":
        return (
            "-===🌸落樱之都🌸===-\n"
            "个人信息◇人物加点\n"
            "我的背包◇我的任务\n"
            "装备强化◇落樱商城\n"
            "单人副本◇魔塔挑战\n"
            "多人副本◇竞技战斗\n"
            "注册xxx / 改名xxx / 个人信息 / 加点"
        )
    if text == "更新日志":
        return "目前只是做了个框架，需要继续迁移副本、商城、排行等内容。"
    if text == "玩法":
        return "当前已迁移角色注册、改名、个人信息、经验、樱币、加点、恢复等基础玩法。"
    if text.startswith("注册"):
        name = text[2:].strip()
        if not name:
            return "要有名字哦！"
        if player:
            return "已有角色，无法创建！"
        player = service.register_player(user_id, name[:10])
        return f"已创建角色【{player.name}】！"
    if player is None:
        return None
    if text.startswith("改名"):
        return service.rename_player(player, text[2:].strip()[:10])
    if text == "个人信息":
        return service.build_profile_summary(player)
    if match := re.match(r"^加经验([0-9]+)$", text):
        return service.add_exp(player, int(match.group(1)))
    if match := re.match(r"^嘤([0-9]+)$", text):
        return service.add_money(player, int(match.group(1)))
    if text in {"恢复", "回复"}:
        return service.reset_player(player)
    if match := re.match(r"^加([0-9]+)(力量|智力|体质|敏捷|魅力)$", text):
        return service.add_points(player, match.group(2), int(match.group(1)))
    return None


def ensure_nonebot2_services_path() -> None:
    service_root = get_workspace_root() / "nonebot2" / "src"
    service_root_text = str(service_root)
    if service_root_text not in sys.path:
        sys.path.insert(0, service_root_text)


def get_workspace_root() -> Path:
    astrbot_root = os.environ.get("ASTRBOT_ROOT", "").strip()
    if astrbot_root:
        return Path(astrbot_root).resolve().parents[1]
    return Path.cwd().resolve()


def get_nonebot2_data_root() -> Path:
    return get_workspace_root() / "data" / "nonebot2" / "run"


def get_menu_image_cache_root() -> Path:
    astrbot_root = os.environ.get("ASTRBOT_ROOT", "").strip()
    if astrbot_root:
        return Path(astrbot_root).resolve() / "data" / "plugin_data" / "qqbot_menu"
    return get_workspace_root() / "data" / "astrbot" / "data" / "plugin_data" / "qqbot_menu"


def get_nonebot2_config_value(section: str, key: str, default: str = "") -> str:
    config = load_nonebot2_config()
    raw_section = config.get(section, {})
    if not isinstance(raw_section, dict):
        return default
    value = raw_section.get(key, default)
    if isinstance(value, (dict, list)):
        return default
    return str(value)


def load_nonebot2_config() -> dict:
    config_path = get_workspace_root() / "data" / "nonebot2" / "config" / "qqbot.toml"
    if not config_path.is_file():
        return {}
    return tomllib.loads(config_path.read_text(encoding="utf-8"))


def read_event_time_seconds(event: AstrMessageEvent) -> int:
    raw = _raw_event_dict(event)
    value = raw.get("time")
    if isinstance(value, (int, float)) and value > 0:
        return int(value)
    return int(time.time())


def resolve_display_name(user_id: int, group_id: int = 0) -> str:
    return str(user_id)


def get_player_name(event: AstrMessageEvent) -> str:
    name = str(event.get_sender_name() or "").strip()
    if name:
        return name
    return str(event.get_sender_id() or "")


def fetch_factorio_space_age_windows_link() -> FactorioDownloadLink:
    credentials = load_factorio_credentials()
    version = fetch_stable_space_age_version()
    query = urlencode({"username": credentials.username, "token": credentials.token})
    url = f"https://www.factorio.com/get-download/{version}/expansion/win64?{query}"
    request = Request(url, headers={"User-Agent": "qqbot-astrbot-factorio-download-link/1.0"})
    try:
        with build_opener(_NoRedirectHandler()).open(request, timeout=30.0) as response:
            if 200 <= response.status < 300:
                return FactorioDownloadLink(version=version, url=response.url)
            raise FactorioDownloadError(f"Factorio 下载接口返回 HTTP {response.status}")
    except HTTPError as exc:
        if exc.code in {301, 302, 303, 307, 308}:
            location = exc.headers.get("Location", "").strip()
            if location:
                return FactorioDownloadLink(version=version, url=urljoin(url, location))
        if exc.code in {401, 403}:
            raise FactorioDownloadError("Factorio 凭据无效或账号没有 Space Age 下载权限") from exc
        if exc.code == 404:
            raise FactorioDownloadError("Factorio 官网没有提供当前版本的 Space Age Windows 安装包") from exc
        raise FactorioDownloadError(f"Factorio 下载接口返回 HTTP {exc.code}") from exc
    except URLError as exc:
        raise FactorioDownloadError(f"无法连接 Factorio 下载接口：{exc.reason}") from exc
    except TimeoutError as exc:
        raise FactorioDownloadError("连接 Factorio 下载接口超时") from exc


def fetch_stable_space_age_version() -> str:
    request = Request(
        "https://factorio.com/api/latest-releases",
        headers={"User-Agent": "qqbot-astrbot-factorio-download-link/1.0"},
    )
    try:
        with build_opener().open(request, timeout=30.0) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        raise FactorioDownloadError(f"Factorio 版本接口返回 HTTP {exc.code}") from exc
    except URLError as exc:
        raise FactorioDownloadError(f"无法连接 Factorio 版本接口：{exc.reason}") from exc
    except TimeoutError as exc:
        raise FactorioDownloadError("连接 Factorio 版本接口超时") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FactorioDownloadError("Factorio 版本接口返回内容不是 JSON") from exc
    stable = data.get("stable") if isinstance(data, dict) else None
    version = stable.get("expansion") if isinstance(stable, dict) else None
    if not isinstance(version, str) or not version.strip():
        raise FactorioDownloadError("Factorio 版本接口缺少 stable.expansion 版本号")
    return version.strip()


def load_factorio_credentials() -> FactorioCredentials:
    env_file_values = load_workspace_env_values()
    username = (os.environ.get("FACTORIO_USERNAME") or env_file_values.get("FACTORIO_USERNAME", "")).strip()
    token = (os.environ.get("FACTORIO_TOKEN") or env_file_values.get("FACTORIO_TOKEN", "")).strip()
    if not username or not token:
        raise FactorioDownloadError("缺少 FACTORIO_USERNAME 或 FACTORIO_TOKEN")
    return FactorioCredentials(username=username, token=token)


def load_workspace_env_values() -> dict[str, str]:
    astrbot_root = os.environ.get("ASTRBOT_ROOT", "").strip()
    if not astrbot_root:
        return {}
    workspace_root = Path(astrbot_root).resolve().parents[1]
    env_path = workspace_root / "data" / "nonebot2" / "config" / ".env"
    if not env_path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values
