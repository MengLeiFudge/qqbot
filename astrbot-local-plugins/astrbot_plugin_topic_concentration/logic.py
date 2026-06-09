from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import re


DUAL_PLATFORM_DUPLICATE_WINDOW_SECONDS = 3.0
ACTIVE_REPLY_INFLIGHT_LEASE_SECONDS = 600.0
FIXED_COMMAND_PREFIX_RE = re.compile(
    r"^(?:棉花糖|棉花)\s*生图|^(?:查|查询|查看|看)(?:一下)?(?:我(?:的)?|当前)?(?:生图)?积分"
    r"|^(?:生图模型|生图价格|draw\s*models|draw\s*help|balance|points?)$"
    r"|^(?:菜单|帮助|指令)(?:\s*\S+)?$|^(?:通知)?(?:大家|全员|群友)?(?:清理|整理)(?:群)?文件$|^(?:群)?文件(?:清理|整理)(?:通知)?$"
    r"|^(?:棉花(?:记录|导出(?:md|MD)?)(?:\s*[0-9]{1,3})?|(?:记录|导出).*(?:对话|聊天记录|群聊记录).*(?:md|MD|markdown|Markdown|\.md|文件|当前目录).*)$"
    r"|^[开关](?:群色图|图片显示)$|^(?:来点)?(?:[美色涩蛇]图|混合).*$"
    r"|^arctj\s*[0-9]+(?:\.[0-9]+)?$|^arc(?:hd|tz)$|^(?:xz|arcxz)$|^(?:arczm|zm)(?:\s*[1-9][0-9]*)?$"
    r"|^(?:arcqh|qh)(?:\s*(?:[1-9][0-9]*|max))?$|^arcqh\s*(?:bt|补图)$|^(?:arcjx|jx)$"
    r"|^(?:i|view|chart|chart1|chart2|path|path1|path2|p|puzzle|puzzle1|puzzle2) .*$"
    r"|^(?:养鲲|摸鲲|抓鲲|捕鲲|属性|道具|背包|商城|签到|boss|Boss|查看boss|查看Boss|挑战|落樱之都|更新日志|玩法|个人信息|恢复|回复).*$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class TopicWindowMessage:
    text: str
    user_id: str
    at_bot: bool
    reply_bot: bool
    created_at: float


@dataclass(frozen=True, slots=True)
class TopicRecordResult:
    window: deque[TopicWindowMessage]
    duplicate: bool


@dataclass(frozen=True, slots=True)
class TopicInterest:
    topic_key: str
    topic_type: str
    reason: str


@dataclass(frozen=True, slots=True)
class TopicDecision:
    should_reply: bool
    topic_key: str
    topic_type: str
    reason: str
    reply_style: str
    max_length: str


async def chat_with_current_provider(
    *,
    context,
    event,
    prompt: str,
    session_id: str | None = None,
    logger,
):
    provider = read_current_provider(context, event, logger)
    provider_id = read_provider_id(provider)
    if provider is None:
        logger.info("[TopicConcentration] no provider for active reply decision")
        return None

    try:
        response = await provider.text_chat(
            prompt=prompt,
            session_id=session_id or f"topic_concentration:{event.unified_msg_origin}",
            persist=False,
        )
    except Exception as exc:
        logger.warning(
            "[TopicConcentration] AI decision provider failed: provider=%s error=%s",
            provider_id,
            exc,
        )
        return None
    logger.debug("[TopicConcentration] AI decision provider succeeded: provider=%s", provider_id)
    return response


def read_current_provider(context, event, logger):
    try:
        return context.get_using_provider(event.unified_msg_origin)
    except Exception as exc:
        logger.warning("[TopicConcentration] failed to read current provider: %s", exc)
        return None


def read_provider_id(provider) -> str:
    if provider is None:
        return ""
    provider_config = getattr(provider, "provider_config", None)
    if not isinstance(provider_config, dict):
        return ""
    return str(provider_config.get("id") or "").strip()


def read_config_value(config, key: str, default):
    if config is None:
        return default
    if isinstance(config, dict):
        return config.get(key, default)
    getter = getattr(config, "get", None)
    if callable(getter):
        try:
            return getter(key, default)
        except TypeError:
            pass
    try:
        return config[key]
    except Exception:
        return default


def active_reply_scope_key(event) -> str:
    group_id = str(event.get_group_id() or "").strip()
    if group_id:
        return f"group:{group_id}"
    return str(getattr(event, "unified_msg_origin", "") or "")


def try_acquire_active_reply_inflight(
    inflight: dict[str, float],
    scope_key: str,
    *,
    now: float,
    lease_seconds: float = ACTIVE_REPLY_INFLIGHT_LEASE_SECONDS,
) -> bool:
    existing = inflight.get(scope_key)
    if existing is not None and now - existing < lease_seconds:
        return False
    inflight[scope_key] = now
    return True


def release_active_reply_inflight(inflight: dict[str, float], scope_key: str) -> None:
    inflight.pop(scope_key, None)


def is_recent_duplicate_observation(
    window: deque[TopicWindowMessage],
    *,
    text: str,
    user_id: str,
    now: float,
    duplicate_window_seconds: float = DUAL_PLATFORM_DUPLICATE_WINDOW_SECONDS,
) -> bool:
    normalized = normalize_observed_text(text)
    if not normalized or not user_id:
        return False
    for message in reversed(window):
        if now - message.created_at > duplicate_window_seconds:
            return False
        if message.user_id == user_id and normalize_observed_text(message.text) == normalized:
            return True
    return False


def compact_text(text: str) -> str:
    return re.sub(r"\s+", "", text.strip())


def normalize_observed_text(text: str) -> str:
    return " ".join(str(text or "").split()).strip()


def has_strong_topic_signal(text: str) -> bool:
    compact = compact_text(text).lower()
    if not compact:
        return False
    strong_markers = (
        "?",
        "？",
        "请问",
        "求助",
        "有人知道",
        "谁知道",
        "怎么",
        "咋",
        "为啥",
        "为什么",
        "报错",
        "错误",
        "异常",
        "配置",
        "代码",
        "接口",
        "日志",
        "打不开",
        "不生效",
        "mod",
        "模组",
        "星环",
        "factorio",
        "shapez",
        "astrbot",
        "nonebot",
        "napcat",
    )
    if looks_like_low_information(text):
        return False
    return any(marker in compact for marker in strong_markers)


def looks_like_low_information(text: str) -> bool:
    compact = compact_text(text).lower()
    if not compact:
        return True
    core = re.sub(r"[?!？！，,。.~～…、]+", "", compact)
    if not core:
        return True
    low_interjections = {
        "咪",
        "咪咪",
        "喵",
        "喵喵",
        "啊",
        "啊啊",
        "嗯",
        "嗯嗯",
        "哦",
        "噢",
        "额",
        "呃",
        "诶",
        "欸",
        "哈",
        "哈哈",
    }
    if len(core) <= 4 and core in low_interjections:
        return True
    low_markers = ("哈哈", "草", "笑死", "乐", "确实", "对啊", "是吧", "好耶", "离谱")
    return len(compact) <= 12 and any(marker in compact for marker in low_markers)


def looks_like_qqbot_fixed_command(text: str) -> bool:
    return FIXED_COMMAND_PREFIX_RE.search(str(text or "").strip()) is not None
