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
def looks_like_topic_concentration_candidate(
    text: str,
    *,
    bot_names: tuple[str, ...] = (),
) -> bool:
    compact = _compact(text)
    if not compact:
        return False
    if looks_like_ai_named_topic(compact, bot_names=bot_names):
        return True
    if _looks_low_information(compact) and len(compact) <= 12:
        return False
    if _has_any(compact, EXPLICIT_HELP_MARKERS) or _has_any(compact, DIAGNOSTIC_MARKERS):
        return True
    if _has_any(compact, QUESTION_MARKERS) and len(compact) >= 6:
        return True
    return _has_any(compact.lower(), DOMAIN_MARKERS) and len(compact) >= 8


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
    lines.append("不要解释主动介入机制；低信息闲聊可以 40 字以内，话题讨论或技术排查按信息完整性回复。")
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
        "如果群友已经说清楚、问题不是问棉花糖、是在评价其他机器人、或只是提到棉花糖这个名字但不是叫棉花糖说话，should_reply 必须为 false。",
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
    should_reply = bool(payload.get("should_reply"))
    topic_key = _clean_json_string(payload.get("topic_key"))[:80]
    topic_type = _clean_json_string(payload.get("topic_type"))[:80]
    reason = _clean_json_string(payload.get("reason"))[:160]
    reply_style = _clean_json_string(payload.get("reply_style")).lower()
    max_length = _clean_json_string(payload.get("max_length")).lower()
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
