from __future__ import annotations

from dataclasses import dataclass
import json
import re


FOLLOWUP_WINDOW_SECONDS = 180.0
FOLLOWUP_MAX_MESSAGES = 6
FOLLOWUP_END_MARKER = "[[QQBOT_FOLLOWUP_END]]"
DUAL_PLATFORM_DUPLICATE_WINDOW_SECONDS = 3.0
FIXED_COMMAND_PREFIX_RE = re.compile(
    r"^(?:棉花糖|棉花)\s*生图|^(?:查|查询|查看|看)(?:一下)?(?:我(?:的)?|当前)?(?:生图)?积分"
    r"|^(?:生图模型|生图价格|draw\s*models|draw\s*help|balance|points?)$"
    r"|^用量$"
    r"|^(?:菜单|帮助|指令)(?:\s*\S+)?$|^(?:通知)?(?:大家|全员|群友)?(?:清理|整理)(?:群)?文件$|^(?:群)?文件(?:清理|整理)(?:通知)?$"
    r"|^[开关](?:群色图|图片显示)$|^(?:来点)?(?:[美色涩蛇]图|混合).*$"
    r"|^arctj\s*[0-9]+(?:\.[0-9]+)?$|^arc(?:hd|tz)$|^(?:xz|arcxz)$|^(?:arczm|zm)(?:\s*[1-9][0-9]*)?$"
    r"|^(?:arcqh|qh)(?:\s*(?:[1-9][0-9]*|max))?$|^arcqh\s*(?:bt|补图)$|^(?:arcjx|jx)$"
    r"|^(?:i|view|chart|chart1|chart2|path|path1|path2|p|puzzle|puzzle1|puzzle2) .*$"
    r"|^(?:养鲲|摸鲲|抓鲲|捕鲲|属性|道具|背包|商城|签到|boss|Boss|查看boss|查看Boss|挑战|落樱之都|更新日志|玩法|个人信息|恢复|回复).*$",
    re.IGNORECASE,
)
BOT_NAME_MARKERS = ("棉花糖", "天使棉花糖", "恶魔棉花糖", "萌萌棉花糖", "qqbot")
CALL_ACTION_MARKERS = (
    "帮",
    "帮我",
    "给我",
    "替我",
    "查",
    "查一下",
    "查询",
    "看",
    "看一下",
    "看看",
    "解释",
    "说明",
    "回答",
    "说",
    "说说",
    "评价",
    "点评",
    "分析",
    "生成",
    "画",
    "生图",
    "识别",
    "认",
    "找",
    "推荐",
    "总结",
    "翻译",
    "改写",
    "在吗",
    "在嘛",
    "在不在",
    "出来",
    "说句话",
    "救",
    "救救",
)
STRONG_NON_CALL_MARKERS = (
    "很好吃",
    "好吃",
    "真好吃",
    "挺好吃",
    "不好吃",
    "甜",
    "太甜",
    "糖果",
    "软糖",
    "甜点",
    "零食",
    "棉花糖味",
    "草莓棉花糖",
    "巧克力棉花糖",
    "烤棉花糖",
    "棉花糖机器",
    "棉花糖机",
    "棉花糖工厂",
    "棉花糖皮肤",
    "棉花糖成熟",
    "买棉花糖",
    "卖棉花糖",
)


@dataclass(frozen=True, slots=True)
class CallIntentDecision:
    should_reply: bool
    reason: str = ""


def contains_cotton_candy_marker(text: str) -> bool:
    return "棉花糖" in str(text or "") or "qqbot" in str(text or "").lower()


def classify_cotton_candy_call(text: str) -> str:
    """Return call, non_call, or ambiguous for plain text that mentions 棉花糖."""
    raw = str(text or "").strip()
    if not raw:
        return "non_call"
    if looks_like_qqbot_fixed_command(raw):
        return "non_call"
    compact = _compact_call_text(raw)
    if not compact:
        return "non_call"
    normalized_markers = tuple(_compact_call_text(marker) for marker in BOT_NAME_MARKERS)
    if compact in normalized_markers:
        return "call"
    for marker in normalized_markers:
        if compact in {
            f"呼叫{marker}",
            f"叫一下{marker}",
            f"喊一下{marker}",
            f"{marker}在吗",
            f"{marker}在嘛",
            f"{marker}在不在",
            f"{marker}出来",
            f"{marker}说句话",
            f"{marker}回答一下",
            f"{marker}看一下",
        }:
            return "call"
    if _looks_like_strong_non_call(compact):
        return "non_call"
    if _starts_with_bot_name_and_action(compact, normalized_markers):
        return "call"
    if _prefix_calls_bot(compact, normalized_markers):
        return "call"
    if not contains_cotton_candy_marker(raw):
        return "non_call"
    return "ambiguous"


def looks_like_direct_bot_call(text: str) -> bool:
    return classify_cotton_candy_call(text) == "call"


def build_call_intent_prompt(text: str, *, history_lines: list[str] | None = None) -> str:
    lines = [
        "你是 QQ 群机器人“棉花糖”的呼叫判定器，只判断用户这条消息是不是在叫机器人处理当前请求。",
        "必须只返回 JSON，不要解释，不要输出 Markdown。",
        "输出字段：should_reply(boolean), reason(string)。",
        "should_reply=true 只表示应该让其中一只棉花糖进入普通 LLM 回复链路；不要执行固定命令、扣积分、写文件、上传、下载或群管动作。",
        "如果用户只是把“棉花糖”当食物、物件、外号、梗、商品、机器、皮肤或普通名词，should_reply=false。",
        "如果用户在叫棉花糖帮忙、回答、解释、生成、识图、评价、在吗、出来、说句话，should_reply=true。",
        "如果上下文不够，但这句话明显是在喊机器人接话，should_reply=true；如果只是能聊但没有呼叫意图，should_reply=false。",
        "正例：棉花糖，帮我生成一张图片 => true",
        "正例：棉花糖这个图片是哪个角色 => true",
        "反例：棉花糖很好吃 => false",
        "反例：草莓棉花糖在哪买 => false",
    ]
    if history_lines:
        lines.append("最近上下文节选，仅辅助判断是否在叫机器人：")
        lines.extend(line for line in history_lines if line)
    lines.append("用户消息：")
    lines.append(str(text or "").strip())
    return "\n".join(lines)


def parse_call_intent_response(text: str) -> CallIntentDecision | None:
    try:
        payload = _extract_json_object(text)
    except Exception:
        return None
    return CallIntentDecision(
        should_reply=bool(payload.get("should_reply")),
        reason=str(payload.get("reason") or "").strip()[:160],
    )


def build_followup_instruction() -> str:
    return (
        "这条消息来自同群同用户上一轮呼叫后的 3 分钟 follow-up 窗口；用户不需要再次 @。"
        "请接上文直接回复，不要解释内部窗口。"
        f"如果你判断本轮对话已经自然结束，请在回复末尾附加 {FOLLOWUP_END_MARKER}；"
        "不要向用户解释这个标记。"
    )


def strip_followup_end_marker(text: str) -> tuple[str, bool]:
    raw = str(text or "")
    if FOLLOWUP_END_MARKER not in raw:
        return raw, False
    cleaned = raw.replace(FOLLOWUP_END_MARKER, "")
    cleaned = re.sub(r"\s+\n", "\n", cleaned).strip()
    return cleaned, True


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
        logger.info("[TopicConcentration] no provider for call intent decision")
        return None

    try:
        response = await provider.text_chat(
            prompt=prompt,
            session_id=session_id or f"topic_concentration:{event.unified_msg_origin}",
            persist=False,
        )
    except Exception as exc:
        logger.warning(
            "[TopicConcentration] call intent provider failed: provider=%s error=%s",
            provider_id,
            exc,
        )
        return None
    logger.debug("[TopicConcentration] call intent provider succeeded: provider=%s", provider_id)
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


def compact_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "").strip())


def normalize_observed_text(text: str) -> str:
    return " ".join(str(text or "").split()).strip()


def has_strong_topic_signal(text: str) -> bool:
    compact = compact_text(text).lower()
    if not compact or looks_like_low_information(text):
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


def looks_like_short_presence_probe(text: str) -> bool:
    core = _compact_call_text(text)
    return core in {"在吗", "在嘛", "在不在", "还在吗", "人呢"}


def looks_like_qqbot_fixed_command(text: str) -> bool:
    return FIXED_COMMAND_PREFIX_RE.search(str(text or "").strip()) is not None


def is_recent_duplicate_observation(
    window,
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
        created_at = float(getattr(message, "created_at", 0.0) or 0.0)
        if now - created_at > duplicate_window_seconds:
            return False
        if str(getattr(message, "user_id", "") or "") == user_id and normalize_observed_text(
            getattr(message, "text", "")
        ) == normalized:
            return True
    return False


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


def _starts_with_bot_name_and_action(compact: str, markers: tuple[str, ...]) -> bool:
    for marker in markers:
        if not compact.startswith(marker):
            continue
        rest = compact[len(marker) :]
        if not rest:
            return True
        if rest.startswith(("，", ",", "。", ".", "：", ":", "？", "?")):
            return True
        if rest.endswith(("吗", "嘛", "？", "?")) and len(rest) <= 12:
            return True
        compact_actions = tuple(_compact_call_text(action) for action in CALL_ACTION_MARKERS)
        if any(rest.startswith(action) for action in compact_actions):
            return True
        if any(len(action) >= 2 and action in rest[:12] for action in compact_actions):
            return True
    return False


def _prefix_calls_bot(compact: str, markers: tuple[str, ...]) -> bool:
    prefixes = ("呼叫", "叫一下", "喊一下", "召唤")
    return any(compact.startswith(f"{prefix}{marker}") for prefix in prefixes for marker in markers)


def _looks_like_strong_non_call(compact: str) -> bool:
    if any(_compact_call_text(marker) in compact for marker in STRONG_NON_CALL_MARKERS):
        return True
    if "棉花糖" not in compact:
        return False
    if re.search(r"(?:吃|买|卖|烤|做|制作|生产|机器|皮肤|工厂|味|口味)", compact):
        return not any(_compact_call_text(action) in compact for action in CALL_ACTION_MARKERS)
    return False


def _compact_call_text(text: str) -> str:
    compact = compact_text(text).lower()
    return re.sub(r"[?!？！，,。.~～…、:：；;\s]+", "", compact)


def _extract_json_object(text: str) -> dict[str, object]:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
        raw = re.sub(r"```$", "", raw).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", raw)
        if match is None:
            raise
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("call intent decision is not a JSON object")
    return data
