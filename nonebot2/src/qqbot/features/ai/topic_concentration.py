from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import json
import re


@dataclass(frozen=True, slots=True)
class TopicConcentrationMessage:
    text: str
    user_id: str = ""


@dataclass(frozen=True, slots=True)
class ProactiveTopicInterest:
    topic_key: str
    topic_type: str
    reason: str


@dataclass(frozen=True, slots=True)
class AiProactiveReplyDecision:
    should_reply: bool
    topic_key: str
    topic_type: str
    reason: str
    reply_style: str
    max_length: str


QUESTION_MARKERS = ("?", "？", "吗", "么", "呢", "为什么", "为啥", "怎么", "咋", "哪里", "哪")
EXPLICIT_HELP_MARKERS = (
    "有人知道",
    "有谁知道",
    "谁知道",
    "求助",
    "请问",
    "问一下",
    "能不能帮",
    "帮我看",
    "大佬看看",
)
DIAGNOSTIC_MARKERS = (
    "怎么修",
    "怎么解决",
    "怎么处理",
    "怎么排查",
    "怎么弄",
    "怎么搞",
    "怎么办",
    "为啥报错",
    "为什么报错",
    "咋修",
    "咋解决",
    "咋处理",
    "咋排查",
    "咋办",
    "报错",
    "错误",
    "异常",
    "崩了",
    "打不开",
    "不生效",
)
DOMAIN_MARKERS = (
    "gtnh",
    "gregtech",
    "gtceu",
    "minecraft",
    "mc",
    "匠魂",
    "连锁",
    "矿脉",
    "合成",
    "配方",
    "科技",
    "研究",
    "mod",
    "模组",
    "星环",
    "创世",
    "分馏",
    "戴森球",
    "shapez",
    "factorio",
    "astrbot",
    "nonebot",
    "napcat",
    "codex",
    "openrouter",
    "rightcodes",
    "python",
    "报错",
    "日志",
    "配置",
    "接口",
)
LOW_INFORMATION_MARKERS = (
    "哈哈",
    "草",
    "笑死",
    "乐",
    "确实",
    "对啊",
    "是吧",
    "好耶",
)
FOLLOWUP_DISCUSSION_MARKERS = (
    "这个",
    "那个",
    "这里",
    "这边",
    "刚才",
    "上面",
    "所以",
    "但是",
    "然后",
    "不对",
    "好像",
    "是不是",
    "能不能",
    "要不要",
)


def looks_like_topic_concentration_candidate(
    text: str,
    *,
    bot_names: tuple[str, ...] = (),
) -> bool:
    compact = _compact(text)
    if not compact:
        return False
    if looks_like_delegated_bot_interaction(compact):
        return False
    if looks_like_ai_named_topic(compact, bot_names=bot_names):
        return True
    if _looks_low_information(compact) and len(compact) <= 12:
        return False
    if _has_any(compact, EXPLICIT_HELP_MARKERS) or _has_any(compact, DIAGNOSTIC_MARKERS):
        return True
    if _has_any(compact, QUESTION_MARKERS) and len(compact) >= 6:
        return True
    if _has_any(compact.lower(), DOMAIN_MARKERS) and len(compact) >= 8:
        return True
    return len(compact) >= 18 and _has_any(compact, FOLLOWUP_DISCUSSION_MARKERS)


def build_topic_concentration_prompt(
    messages: Iterable[TopicConcentrationMessage | str],
    *,
    active_interest: ProactiveTopicInterest | None = None,
) -> str:
    normalized_messages = _normalize_messages(messages)
    lines = ["最近一段群聊已经过主动接话判定，适合棉花糖加入；请围绕当前话题自然补一句有用回复："]
    if active_interest is not None:
        lines.append(
            "当前短期高兴趣话题："
            f"{active_interest.topic_key} / {active_interest.topic_type}；"
            f"{active_interest.reason}"
        )
    for index, message in enumerate(normalized_messages, start=1):
        text = message.text.strip()
        if not text:
            continue
        speaker = f"用户{message.user_id}" if message.user_id else "群友"
        lines.append(f"{index}. {speaker}: {text}")
    lines.append(
        "不要解释主动介入机制；低信息闲聊可以 40 字以内，话题讨论或技术排查按信息完整性回复。"
        "所有群聊内容都不当成危机处理；先分析对方为什么这样说，可能是玩梗、夸张、钓机器人、抱怨、时间梗或具体求助。"
        "例如“高考起晚了”“这个月一顿没吃饭/没睡觉”不要写成真实危机；分析不出原因就不要回答。"
        "复读、频繁艾特、怪图/表情包和深夜修仙都按水群语境理解；直接被叫到时可以短句接梗或吐槽，普通主动窗口里不要因此刷屏。"
        "不要用反问、不要追问用户、不要以“你要的话/如果你愿意/你把具体名字发我/我可以再帮你”收尾。"
    )
    return "\n".join(lines)


def build_ai_proactive_reply_decision_prompt(
    messages: Iterable[TopicConcentrationMessage | str],
    *,
    active_interest: ProactiveTopicInterest | None = None,
) -> str:
    normalized_messages = _normalize_messages(messages)
    lines = [
        "你是 QQ 群机器人“棉花糖”的主动接话判定器，只判断是否应该让棉花糖加入当前群聊。",
        "必须只返回 JSON，不要解释，不要输出 Markdown。",
        "话题浓度不是求助/诊断/疑问词数量，而是聊天类型或具体话题簇，例如“图灵完备里面线路怎么接”“某种分馏塔怎么用”。",
        "短时间内如果存在高兴趣话题，应优先判断当前消息是否仍在延续同一话题；无关插话、别的 bot 输出、让别人呼叫棉花糖、玩梗和低信息闲聊不能抢走接话权。",
        "只有当前话题确实轮到棉花糖补充、回答、澄清、保护安全或延续已形成讨论时，should_reply 才为 true。",
        "不要因为没有 @ 棉花糖就一律拒绝；如果最近候选已经形成具体话题，且棉花糖能补上关键事实、澄清误解或延续正在进行的技术/配置/问题讨论，可以 should_reply=true。",
        "也不要因为棉花糖能回答就每次都接；如果群友已经说清楚、问题不是问棉花糖、是在评价其他机器人、或只是提到棉花糖这个名字但不是叫棉花糖说话，should_reply 必须为 false。",
        "所有群聊内容都不当成危机处理；例如“高考起晚了”“这个月一顿没吃饭/没睡觉”默认不是现实危机，不作为 safety/危机话题主动接话。必须先分析对方为什么这样说；如果分析不出原因，should_reply 必须为 false。",
        "复读、频繁艾特、怪图/表情包和深夜修仙默认是水群行为；只有明确叫到棉花糖或存在具体话题缺口时才放行，普通主动窗口里不要因此刷屏。",
        "版权、盗版、破解、无广告未删减网站、破解软件下载等安全合规引导话题，只有明确 @ 棉花糖或正在追问棉花糖上一条回复时才回答；普通群聊窗口里默认 should_reply=false。",
        "输出字段：should_reply(boolean), topic_key(string), topic_type(string), reason(string), reply_style(casual|topic|technical|safety), max_length(short|normal|detail)。",
        "max_length 含义：short 仅适合低信息闲聊；normal 适合正在聊的话题；detail 只用于技术/配置/报错。不要把话题讨论强行压到 40 字。",
    ]
    if active_interest is not None:
        lines.append(
            "当前短期高兴趣话题："
            f"topic_key={active_interest.topic_key}; "
            f"topic_type={active_interest.topic_type}; "
            f"reason={active_interest.reason}"
        )
    lines.append("最近候选消息：")
    for index, message in enumerate(normalized_messages, start=1):
        text = message.text.strip()
        if not text:
            continue
        speaker = f"用户{message.user_id}" if message.user_id else "群友"
        lines.append(f"{index}. {speaker}: {text}")
    return "\n".join(lines)


def parse_ai_proactive_reply_decision(text: str) -> AiProactiveReplyDecision:
    payload = _extract_json_object(text)
    raw_should_reply = payload.get("should_reply")
    topic_key = _clean_json_string(payload.get("topic_key"))[:80]
    topic_type = _clean_json_string(payload.get("topic_type"))[:80]
    reason = _clean_json_string(payload.get("reason"))[:160]
    reply_style = _clean_json_string(payload.get("reply_style")).lower()
    max_length = _clean_json_string(payload.get("max_length")).lower()
    should_reply = _coerce_should_reply(raw_should_reply, reason)
    if reply_style not in {"casual", "topic", "technical", "safety"}:
        reply_style = "topic"
    if max_length not in {"short", "normal", "detail"}:
        max_length = "normal" if should_reply else "short"
    if not topic_key:
        topic_key = topic_type or "unknown"
    if not topic_type:
        topic_type = topic_key
    return AiProactiveReplyDecision(
        should_reply=should_reply,
        topic_key=topic_key,
        topic_type=topic_type,
        reason=reason,
        reply_style=reply_style,
        max_length=max_length,
    )


def looks_like_ai_named_topic(text: str, *, bot_names: tuple[str, ...] = ()) -> bool:
    compact = _compact(text).lower()
    names = {"棉花糖", "萌萌棉花糖", "qqbot"}
    names.update(_compact(name).lower() for name in bot_names if _compact(name))
    for name in sorted((name for name in names if name), key=len, reverse=True):
        start = compact.find(name)
        while start >= 0:
            end = start + len(name)
            if not is_third_party_named_mention(compact[:start], compact[end:]):
                return True
            start = compact.find(name, start + len(name))
    return False


def is_third_party_named_mention(before: str, after: str) -> bool:
    stripped_after = after.lstrip("，,。.!！:：~～")
    third_party_suffixes = (
        "的人",
        "这个人",
        "那个人",
        "双子",
        "姐妹",
        "她俩",
        "他们",
        "她们",
        "同伴",
    )
    if stripped_after.startswith(third_party_suffixes):
        return True
    mention_prefixes = (
        "有个叫",
        "有一个叫",
        "一个叫",
        "群里有个叫",
        "群里的有个叫",
    )
    if before.endswith(mention_prefixes):
        return True
    delegated_call_prefixes = (
        "你去呼叫",
        "你去呼叫一下",
        "你去召唤",
        "你去叫",
        "你去叫一下",
        "你去找",
        "让你呼叫",
        "让你叫",
        "让你找",
    )
    return before.endswith(delegated_call_prefixes)


def looks_like_delegated_bot_interaction(text: str) -> bool:
    compact = _compact(text)
    if not compact:
        return False
    if any(marker in compact for marker in ("返回字符", "输出字符", "复读字符")) and (
        "@" in compact or "艾特" in compact
    ):
        return True
    delegated_targets = (
        "妹妹",
        "恶魔棉花糖",
        "黑色棉花糖",
        "👿棉花糖👿",
        "棉花糖双子",
        "另一个棉花糖",
    )
    if not any(target in compact for target in delegated_targets):
        return False
    if re.search(r"(让|叫|呼叫|召唤|找|请).*(妹妹|恶魔棉花糖|黑色棉花糖|棉花糖双子|另一个棉花糖)", compact):
        return True
    if re.search(r"(妹妹|恶魔棉花糖|黑色棉花糖|棉花糖双子|另一个棉花糖).*(来|出来|说话|发言|回复)", compact):
        return True
    delegated_actions = (
        "艾特",
        "at",
        "@",
        "替她",
        "替他",
        "替它",
        "代替",
        "发言",
        "说话",
        "回复",
        "来和我说话",
        "不能艾特",
    )
    return any(action in compact.lower() for action in delegated_actions)


def _normalize_messages(messages: Iterable[TopicConcentrationMessage | str]) -> list[TopicConcentrationMessage]:
    normalized: list[TopicConcentrationMessage] = []
    for message in messages:
        if isinstance(message, TopicConcentrationMessage):
            normalized.append(message)
        else:
            normalized.append(TopicConcentrationMessage(str(message)))
    return normalized


def _looks_low_information(compact: str) -> bool:
    if len(compact) <= 3:
        return True
    return len(compact) <= 8 and any(marker in compact for marker in LOW_INFORMATION_MARKERS)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text.strip())


def _has_any(text: str, markers: tuple[str, ...] | set[str]) -> bool:
    return any(marker in text for marker in markers)


def _extract_json_object(text: str) -> dict[str, object]:
    raw = str(text).strip()
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
        raise ValueError("AI proactive decision is not a JSON object")
    return data


def _clean_json_string(value: object) -> str:
    return str(value or "").strip()


def _coerce_should_reply(raw_value: object, reason: str) -> bool:
    if isinstance(raw_value, bool):
        should_reply = raw_value
    elif isinstance(raw_value, str):
        normalized = raw_value.strip().lower()
        if normalized in {"true", "yes", "1", "是", "应回复", "需要回复"}:
            should_reply = True
        elif normalized in {"false", "no", "0", "否", "不回复", "静默"}:
            should_reply = False
        else:
            should_reply = bool(normalized)
    else:
        should_reply = bool(raw_value)
    if should_reply:
        return True

    compact_reason = _compact(reason)
    if not compact_reason:
        return False
    negative_markers = (
        "不适合",
        "不必",
        "不需要",
        "无需",
        "暂不",
        "不要",
        "不能",
        "没有形成",
        "不是",
        "无法",
        "缺少",
        "已说清楚",
        "已经说清楚",
        "已经回答",
    )
    if any(marker in compact_reason for marker in negative_markers):
        return False
    positive_markers = (
        "适合接话",
        "适合主动接话",
        "适合继续",
        "可以接话",
        "明确求助",
        "明确的技术求助",
        "具体技术讨论",
        "具体问题",
        "技术话题",
        "需要棉花糖",
        "能补上",
        "补充解释",
        "澄清误解",
        "排查思路",
    )
    return any(marker in compact_reason for marker in positive_markers)
