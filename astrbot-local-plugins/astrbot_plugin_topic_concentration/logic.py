from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import re


DUAL_PLATFORM_DUPLICATE_WINDOW_SECONDS = 3.0
ACTIVE_REPLY_INFLIGHT_LEASE_SECONDS = 600.0
FOLLOWUP_CALL_WINDOW_SECONDS = 45.0
FIXED_COMMAND_PREFIX_RE = re.compile(
    r"^(?:棉花糖|棉花)\s*生图|^(?:查|查询|查看|看)(?:一下)?(?:我(?:的)?|当前)?(?:生图)?积分"
    r"|^(?:生图模型|生图价格|draw\s*models|draw\s*help|balance|points?)$"
    r"|^用量$"
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
    unresolved_media_context: bool = False


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


def should_consider_active_window(
    window: deque[TopicWindowMessage],
    *,
    named_call: bool = False,
    has_reply_source: bool = False,
) -> bool:
    messages = [message for message in window if compact_text(message.text)]
    if not messages:
        return False
    latest = messages[-1]
    if named_call:
        return True
    if looks_like_low_information(latest.text):
        return has_reply_source
    if latest.at_bot or latest.reply_bot or has_strong_topic_signal(latest.text):
        return True
    return len(messages) >= 2


def should_skip_unresolved_media_active_reply(
    window: deque[TopicWindowMessage],
    *,
    latest_text: str = "",
    named_call: bool = False,
) -> bool:
    if named_call:
        return False
    messages = [message for message in window if compact_text(message.text) or message.unresolved_media_context]
    if not messages:
        return False
    latest = latest_text or messages[-1].text
    if not _depends_on_unresolved_media(latest):
        return False
    latest_index = len(messages) - 1
    for index in range(latest_index, max(-1, latest_index - 4), -1):
        if messages[index].unresolved_media_context:
            return True
    return False


def should_force_active_reply_for_named_call(window: deque[TopicWindowMessage]) -> bool:
    messages = [message for message in window if compact_text(message.text)]
    if not messages:
        return False
    latest = messages[-1]
    if looks_like_direct_bot_call(latest.text):
        return True
    if not looks_like_short_presence_probe(latest.text):
        return False
    for previous in reversed(messages[:-1]):
        if latest.created_at - previous.created_at > FOLLOWUP_CALL_WINDOW_SECONDS:
            return False
        if previous.user_id != latest.user_id:
            continue
        return looks_like_direct_bot_call(previous.text)
    return False


def looks_like_direct_bot_call(text: str) -> bool:
    raw = str(text or "").strip()
    if looks_like_qqbot_fixed_command(raw):
        return False
    core = _compact_call_text(raw)
    if not core:
        return False
    names = ("棉花糖", "天使棉花糖", "恶魔棉花糖", "萌萌棉花糖", "qqbot")
    if core in names:
        return True
    for name in names:
        if core.startswith(name) and len(core) > len(name):
            return True
    prefixes = ("呼叫", "叫一下", "喊一下")
    for name in names:
        if core in {f"{prefix}{name}" for prefix in prefixes}:
            return True
        if core in {
            f"{name}在吗",
            f"{name}在嘛",
            f"{name}在不在",
            f"{name}出来",
            f"{name}说句话",
            f"{name}回答一下",
            f"{name}看一下",
        }:
            return True
    return False


def looks_like_short_presence_probe(text: str) -> bool:
    core = _compact_call_text(text)
    return core in {"在吗", "在嘛", "在不在", "还在吗", "人呢"}


def build_active_reply_decision_prompt(
    window: deque[TopicWindowMessage],
    *,
    current_query: str = "",
    named_call: bool = False,
    has_reply_source: bool = False,
    latest_text: str = "",
    history_lines: list[str] | None = None,
    active_interest: TopicInterest | None = None,
) -> str:
    latest = latest_text or (window[-1].text if window else "")
    lines = [
        "你是 QQ 群机器人“棉花糖”的主动接话判定器，只判断 AstrBot 是否应该加入当前群聊。",
        "必须只返回 JSON，不要解释，不要输出 Markdown。",
        "插件只提供上下文、接话意愿信号、话题候选和知识提示；是否应该接话必须由你根据群聊语境判断。",
        "话题浓度不是求助/诊断/疑问词数量，而是聊天类型或具体话题簇，例如“图灵完备里面线路怎么接”“某种分馏塔怎么用”。",
        "短时间内如果存在高兴趣话题，应优先判断当前消息是否仍在延续同一话题；无关插话、别的 bot 输出、让别人呼叫棉花糖、玩梗和低信息闲聊不能抢走接话权。",
        "只有当前话题确实轮到棉花糖补充、回答、澄清、保护安全或延续已形成讨论时，should_reply 才为 true。",
        "不要因为棉花糖能回答就接话；如果只是可补充、可总结、可表达看法，但群友没有明显缺口，should_reply 必须为 false。",
        "同一话题几分钟内最多适合偶尔说一次；如果刚刚已经由机器人参与过，或群友正在自然推进，should_reply 必须为 false。",
        "如果群友已经说清楚、问题不是问棉花糖、是在评价其他机器人、或只是提到棉花糖这个名字但不是叫棉花糖说话，should_reply 必须为 false。",
        "如果当前消息明确呼叫棉花糖，例如“呼叫棉花糖”“棉花糖回答一下”“棉花糖在吗”，接话意愿很高；但仍要结合被引用消息和群聊上下文自然回应，缺少可回应内容时可以 false。",
        "如果当前话题依赖图片、视频、表情、卡片或转发内容，但上下文里只有“[图片]”这类占位而没有文字描述，你看不到真实内容，不能猜图中物品、升级、价格、界面或报错；普通 active reply 应该 false。",
        "如果最近消息来自另一个机器人，或是在追问/引用另一个机器人，should_reply 必须为 false；不要接另一个 bot 的回复继续说。",
        "所有群聊内容都不当成危机处理；例如“高考起晚了”“这个月一顿没吃饭/没睡觉”默认不是现实危机，不作为 safety/危机话题主动接话。必须先分析对方为什么这样说；如果分析不出原因，should_reply 必须为 false。",
        "复读、频繁艾特、怪图/表情包和深夜修仙默认是水群行为；只有明确叫到棉花糖或存在具体话题缺口时才放行，普通 active reply 不要因此刷屏。",
        "群友说“我们在说你”“太 AI 了”“没看懂还硬接”时，通常是在评价棉花糖乱接话；不要继续长篇解释别人，应倾向 false，或只允许非常短的自我收住。",
        "版权、盗版、破解、无广告未删减网站、破解软件下载等安全合规引导话题，只有明确 @ 棉花糖或正在追问棉花糖上一条回复时才回答；普通 active reply 默认 false。",
        "如果最终放行回复，回复时不要反问、不要追问用户、不要以“你要的话/如果你愿意/你把具体名字发我/我可以再帮你”收尾。",
        "输出字段：should_reply(boolean), topic_key(string), topic_type(string), reason(string), reply_style(casual|topic|technical|safety), max_length(short|normal|detail)。",
        "max_length 含义：short 仅适合低信息闲聊；normal 适合正在聊的话题；detail 只用于技术/配置/报错。不要把话题讨论强行压到 40 字。",
        "插件信号：",
        f"named_call={named_call}",
        f"has_reply_source={has_reply_source}",
        f"unresolved_media_context={any(message.unresolved_media_context for message in window)}",
        f"latest_low_information={looks_like_low_information(latest)}",
        f"latest_strong_topic_signal={has_strong_topic_signal(latest)}",
    ]
    if active_interest is not None:
        lines.append(
            "当前短期高兴趣话题："
            f"topic_key={active_interest.topic_key}; "
            f"topic_type={active_interest.topic_type}; "
            f"reason={active_interest.reason}"
        )
    if current_query:
        lines.append("当前请求原文：")
        lines.append(current_query)
    if history_lines:
        lines.append("AstrBot 群聊上下文节选：")
        lines.extend(history_lines)
    lines.append("最近群聊窗口：")
    for index, message in enumerate(window, start=1):
        text = message.text.strip()
        if not text:
            continue
        flags: list[str] = []
        if message.at_bot:
            flags.append("at_bot")
        if message.reply_bot:
            flags.append("reply_bot")
        flag_text = f" [{' '.join(flags)}]" if flags else ""
        lines.append(f"{index}. 用户{message.user_id}{flag_text}: {text}")
    return "\n".join(lines)


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


def _depends_on_unresolved_media(text: str) -> bool:
    compact = compact_text(text).lower()
    if not compact:
        return False
    if any(marker in compact for marker in ("这个", "那个", "这图", "图里", "图上", "图片", "截图", "界面", "看图")):
        return True
    if len(compact) <= 12 and any(marker in compact for marker in ("升级", "模板", "匠魂", "百分之百", "不碎", "啥了", "什么", "哪里", "哪儿")):
        return True
    return False


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


def _compact_call_text(text: str) -> str:
    compact = compact_text(text).lower()
    return re.sub(r"[?!？！，,。.~～…、:：；;\s]+", "", compact)
