from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import os
from pathlib import Path
import random
import re
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import HTTPRedirectHandler, Request, build_opener

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.event import filter
from astrbot.api.message_components import Plain, Poke
from astrbot.api.star import Context, Star, register
from astrbot.core.star.filter.event_message_type import EventMessageType


FACTORIO_DOWNLOAD_PATTERN = (
    r"(?i)^.*(?:factorio|异星|太空时代|space\s*age|spaceage).*(?:下载|安装包).*(?:链接|地址)?$"
)
MENU_PATTERN = r"^(?:菜单|帮助|指令)$"
FEATURE_MENU_PATTERN = r"^菜单(?!\d+$)\S+$"
REREAD_COOLDOWN_SECONDS = 120.0
FEATURE_MODE_ENV = "QQBOT_ASTRBOT_FEATURE_MODE"
FEATURE_MODE_DUAL = "dual"
FEATURE_MODE_FULL = "full"
FEATURE_MODES = {FEATURE_MODE_DUAL, FEATURE_MODE_FULL}
NONEBOT2_HOST = "127.0.0.1"
NONEBOT2_PORT = 8080


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
        status="二期适配",
        lines=(
            "通知清理文件：依赖 OneBot 群文件枚举和禁言 API，未在本插件默认启用",
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
        status="二期适配",
        lines=("依赖图片缓存、R18 群配置和 Lolicon 元数据数据库，暂未迁移到 bot2",),
    ),
    FeatureSpec(
        name="养鲲",
        aliases=("鲲",),
        status="二期适配",
        lines=("依赖 bot1 的养鲲存档和完整命令状态机，暂未迁移到 bot2",),
    ),
    FeatureSpec(
        name="落樱之都",
        aliases=("樱花", "落樱"),
        status="二期适配",
        lines=("依赖 bot1 的落樱存档，暂未迁移到 bot2",),
    ),
    FeatureSpec(
        name="Arc",
        aliases=("Arc查询", "Arc狼人杀", "Arc吃鸡", "arcaea"),
        status="二期适配",
        lines=(
            "arctj / zm / arcqh / jx / archd / xz 等命令依赖 Arc 服务和资源，暂未迁移到 bot2",
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
        status="二期适配",
        lines=("i/view/chart/path 渲染依赖 shapez 资源和图片渲染服务，暂未迁移到 bot2",),
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
    "0.2.0",
)
class QQBotFeaturesPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self._feature_mode = read_feature_mode(config)
        self._reread_state = RereadRepeatState()
        logger.info(
            "[QQBotFeatures] migrated feature plugin loaded, mode=%s",
            self._feature_mode,
        )

    @filter.regex(MENU_PATTERN)
    async def menu(self, event: AstrMessageEvent):
        if not _is_direct_or_private(event):
            return
        yield event.plain_result(build_menu_text(self._feature_mode))
        event.stop_event()

    @filter.regex(FEATURE_MENU_PATTERN)
    async def feature_menu(self, event: AstrMessageEvent):
        if not _is_direct_or_private(event):
            return
        key = event.get_message_str().strip().removeprefix("菜单")
        feature = find_feature(key)
        if feature is None:
            yield event.plain_result("没有这个模块哦！")
            event.stop_event()
            return
        yield event.plain_result(build_feature_menu_text(feature))
        event.stop_event()

    @filter.regex(FACTORIO_DOWNLOAD_PATTERN)
    async def factorio_download(self, event: AstrMessageEvent):
        if not _is_direct_or_private(event):
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
        if not self_id or not user_id or not target_id:
            return
        if user_id == self_id:
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


def _raw_event_dict(event: AstrMessageEvent) -> dict:
    raw = getattr(event.message_obj, "raw_message", None)
    if isinstance(raw, dict):
        return raw
    try:
        return dict(raw)
    except Exception:
        return {}


def _at(user_id: str):
    from astrbot.api.message_components import At

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


def is_nonebot2_port_open() -> bool:
    try:
        with socket.create_connection((NONEBOT2_HOST, NONEBOT2_PORT), timeout=1.0):
            return True
    except OSError:
        return False


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
