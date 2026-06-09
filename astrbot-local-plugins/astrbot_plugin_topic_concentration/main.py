from __future__ import annotations

from collections import defaultdict, deque
import json
import os
import re
import time

from astrbot.api import logger
from astrbot.api.message_components import At, Plain, Reply
from astrbot.api.platform import MessageType
from astrbot.api.star import Context, Star, register
from astrbot.builtin_stars.astrbot.group_chat_context import GroupChatContext

from .logic import TopicDecision
from .logic import TopicInterest
from .logic import TopicRecordResult
from .logic import TopicWindowMessage
from .logic import release_active_reply_inflight as _release_active_reply_inflight
from .logic import active_reply_scope_key as _active_reply_scope_key
from .logic import chat_with_current_provider as _chat_with_current_decision_provider
from .logic import compact_text as _compact
from .logic import has_strong_topic_signal as _has_strong_topic_signal
from .logic import is_recent_duplicate_observation as _is_recent_duplicate_observation
from .logic import looks_like_low_information as _looks_like_low_information
from .logic import try_acquire_active_reply_inflight as _try_acquire_active_reply_inflight


WINDOW_SECONDS = 150.0
MAX_WINDOW_MESSAGES = 10
COOLDOWN_SECONDS = 480.0
GROUP_COOLDOWN_SECONDS = 300.0
INTEREST_SECONDS = 360.0
MIN_UNPROMPTED_WINDOW_MESSAGES = 2
BOT_NAMES = ("棉花糖", "萌萌棉花糖", "qqbot")
PROFILE_ENV = "QQBOT_ASTRBOT_PROFILE"
PROFILE_OTHER_BOT_IDS = {
    "angel": {"2629227874"},
    "demon": {"1443944862"},
}
PROFILE_BY_BOT_ID = {
    "1443944862": "angel",
    "2629227874": "demon",
}
_WINDOWS: dict[str, deque[TopicWindowMessage]] = defaultdict(deque)
_COOLDOWNS: dict[tuple[str, str], float] = {}
_GROUP_COOLDOWNS: dict[str, float] = {}
_INTERESTS: dict[str, tuple[TopicInterest, float]] = {}
_ACTIVE_REPLY_INFLIGHT: dict[str, float] = {}


@register(
    "astrbot_plugin_topic_concentration",
    "MengLei",
    "棉花糖普通群聊主动接话门控。",
    "0.3.6",
)
class TopicConcentrationPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self._install_active_reply_gate()
        logger.info(
            "[TopicConcentration] loaded: profile=%s other_bot_ids=%s",
            read_bot_profile(),
            sorted(get_other_bot_ids()),
        )

    def _install_active_reply_gate(self) -> None:
        if getattr(GroupChatContext, "_topic_concentration_installed", False):
            logger.info("[TopicConcentration] active reply gate already installed")
            return

        original_need_active_reply = GroupChatContext.need_active_reply

        async def patched_need_active_reply(group_context: GroupChatContext, event) -> bool:
            cfg = group_context.cfg(event)
            if not cfg["enable_active_reply"]:
                return False
            if event.get_message_type() != MessageType.GROUP_MESSAGE:
                return False
            if event.is_at_or_wake_command:
                return False
            if event.get_self_id() == event.get_sender_id():
                return False
            if str(event.get_sender_id()) in get_other_bot_ids(event):
                logger.debug(
                    "[TopicConcentration] skip active reply: "
                    f"group={event.get_group_id()} reason=other_bot_message"
                )
                return False
            if cfg["ar_whitelist"] and (
                event.unified_msg_origin not in cfg["ar_whitelist"]
                and (event.get_group_id() and event.get_group_id() not in cfg["ar_whitelist"])
            ):
                return False
            if cfg["ar_method"] != "possibility_reply":
                return await original_need_active_reply(group_context, event)

            scope_key = _active_reply_scope_key(event)
            record = _record_message(event, scope_key=scope_key)
            if record.duplicate:
                logger.debug(
                    "[TopicConcentration] skip active reply: "
                    f"group={event.get_group_id()} reason=duplicate_dual_platform_event"
                )
                return False
            if not _should_consider_window(record.window):
                logger.debug(
                    "[TopicConcentration] skip active reply: "
                    f"group={event.get_group_id()} reason=weak_window"
                )
                return False
            now = time.monotonic()
            group_cooldown_until = _GROUP_COOLDOWNS.get(scope_key, 0.0)
            if now < group_cooldown_until:
                logger.info(
                    "[TopicConcentration] group cooldown active reply: "
                    f"group={event.get_group_id()} left={group_cooldown_until - now:.1f}s"
                )
                return False
            if not _try_acquire_active_reply_inflight(_ACTIVE_REPLY_INFLIGHT, scope_key, now=now):
                logger.info(
                    "[TopicConcentration] skip active reply: "
                    f"group={event.get_group_id()} reason=inflight"
                )
                return False
            started = time.monotonic()
            logger.info(
                "[TopicConcentration] active reply decision started: "
                f"group={event.get_group_id()} scope={scope_key}"
            )
            try:
                decision = await _decide_with_ai(group_context, event, record.window, scope_key=scope_key)
                elapsed = time.monotonic() - started
                if decision is None:
                    logger.info(
                        "[TopicConcentration] skip active reply: "
                        f"group={event.get_group_id()} reason=decision_failed elapsed={elapsed:.2f}s"
                    )
                    return False
                if not decision.should_reply:
                    logger.debug(
                        "[TopicConcentration] skip active reply: "
                        f"group={event.get_group_id()} topic={decision.topic_key} "
                        f"type={decision.topic_type} elapsed={elapsed:.2f}s reason={decision.reason}"
                    )
                    return False

                cooldown_key = (scope_key, decision.topic_key)
                cooldown_until = _COOLDOWNS.get(cooldown_key, 0.0)
                if now < cooldown_until:
                    logger.info(
                        "[TopicConcentration] cooldown active reply: "
                        f"group={event.get_group_id()} topic={decision.topic_key} "
                        f"left={cooldown_until - now:.1f}s"
                    )
                    return False

                _COOLDOWNS[cooldown_key] = now + COOLDOWN_SECONDS
                _GROUP_COOLDOWNS[scope_key] = now + GROUP_COOLDOWN_SECONDS
                _set_interest(scope_key, decision)
                logger.info(
                    "[TopicConcentration] allow active reply: "
                    f"group={event.get_group_id()} topic={decision.topic_key} "
                    f"type={decision.topic_type} style={decision.reply_style} "
                    f"max_length={decision.max_length} elapsed={elapsed:.2f}s reason={decision.reason}"
                )
                return True
            finally:
                _release_active_reply_inflight(_ACTIVE_REPLY_INFLIGHT, scope_key)

        GroupChatContext._topic_concentration_original_need_active_reply = original_need_active_reply
        GroupChatContext.need_active_reply = patched_need_active_reply
        GroupChatContext._topic_concentration_installed = True
        logger.info("[TopicConcentration] active reply gate installed")


def _record_message(event, *, scope_key: str | None = None) -> TopicRecordResult:
    scope_key = scope_key or _active_reply_scope_key(event)
    window = _WINDOWS[scope_key]
    now = time.monotonic()
    while window and now - window[0].created_at > WINDOW_SECONDS:
        window.popleft()
    text = _plain_text(event)
    user_id = str(event.get_sender_id())
    if _is_recent_duplicate_observation(window, text=text, user_id=user_id, now=now):
        return TopicRecordResult(window=window, duplicate=True)
    window.append(
        TopicWindowMessage(
            text=text,
            user_id=user_id,
            at_bot=_has_at_bot(event),
            reply_bot=_has_reply_bot(event),
            created_at=now,
        )
    )
    while len(window) > MAX_WINDOW_MESSAGES:
        window.popleft()
    return TopicRecordResult(window=window, duplicate=False)


def _should_consider_window(window: deque[TopicWindowMessage]) -> bool:
    messages = [message for message in window if _compact(message.text)]
    if not messages:
        return False
    latest = messages[-1]
    if _looks_like_low_information(latest.text):
        return False
    if latest.at_bot or latest.reply_bot or _has_strong_topic_signal(latest.text):
        return True
    return len(messages) >= MIN_UNPROMPTED_WINDOW_MESSAGES


async def _decide_with_ai(
    group_context: GroupChatContext,
    event,
    window: deque[TopicWindowMessage],
    *,
    scope_key: str,
) -> TopicDecision | None:
    if not any(_compact(message.text) for message in window):
        return None
    prompt = _build_decision_prompt(window, active_interest=_get_interest(scope_key))
    response = await _chat_with_current_provider(group_context.context, event, prompt, scope_key=scope_key)
    if response is None:
        return None
    try:
        return _parse_decision(response.completion_text)
    except Exception as exc:
        logger.warning(
            "[TopicConcentration] AI decision parse failed: "
            f"error={exc} text={str(getattr(response, 'completion_text', ''))[:240]}"
        )
        return None


async def _chat_with_current_provider(context: Context, event, prompt: str, *, scope_key: str):
    return await _chat_with_current_decision_provider(
        context=context,
        event=event,
        prompt=prompt,
        session_id=f"topic_concentration:{scope_key}",
        logger=logger,
    )


def _build_decision_prompt(
    window: deque[TopicWindowMessage],
    *,
    active_interest: TopicInterest | None,
) -> str:
    lines = [
        "你是 QQ 群机器人“棉花糖”的主动接话判定器，只判断 AstrBot 是否应该加入当前群聊。",
        "必须只返回 JSON，不要解释，不要输出 Markdown。",
        "话题浓度不是求助/诊断/疑问词数量，而是聊天类型或具体话题簇，例如“图灵完备里面线路怎么接”“某种分馏塔怎么用”。",
        "短时间内如果存在高兴趣话题，应优先判断当前消息是否仍在延续同一话题；无关插话、别的 bot 输出、让别人呼叫棉花糖、玩梗和低信息闲聊不能抢走接话权。",
        "只有当前话题确实轮到棉花糖补充、回答、澄清、保护安全或延续已形成讨论时，should_reply 才为 true。",
        "不要因为棉花糖能回答就接话；如果只是可补充、可总结、可表达看法，但群友没有明显缺口，should_reply 必须为 false。",
        "同一话题几分钟内最多适合偶尔说一次；如果刚刚已经由机器人参与过，或群友正在自然推进，should_reply 必须为 false。",
        "如果群友已经说清楚、问题不是问棉花糖、是在评价其他机器人、或只是提到棉花糖这个名字但不是叫棉花糖说话，should_reply 必须为 false。",
        "如果最近消息来自另一个机器人，或是在追问/引用另一个机器人，should_reply 必须为 false；不要接另一个 bot 的回复继续说。",
        "所有群聊内容都不当成危机处理；例如“高考起晚了”“这个月一顿没吃饭/没睡觉”默认不是现实危机，不作为 safety/危机话题主动接话。必须先分析对方为什么这样说；如果分析不出原因，should_reply 必须为 false。",
        "版权、盗版、破解、无广告未删减网站、破解软件下载等安全合规引导话题，只有明确 @ 棉花糖或正在追问棉花糖上一条回复时才回答；普通 active reply 默认 false。",
        "如果最终放行回复，回复时不要反问、不要追问用户、不要以“你要的话/如果你愿意/你把具体名字发我/我可以再帮你”收尾。",
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


def _parse_decision(text: str) -> TopicDecision:
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
    return TopicDecision(
        should_reply=should_reply,
        topic_key=topic_key,
        topic_type=topic_type,
        reason=reason,
        reply_style=reply_style,
        max_length=max_length,
    )


def _get_interest(origin: str) -> TopicInterest | None:
    current = _INTERESTS.get(origin)
    if current is None:
        return None
    interest, expires_at = current
    if time.monotonic() >= expires_at:
        _INTERESTS.pop(origin, None)
        return None
    return interest


def _set_interest(origin: str, decision: TopicDecision) -> None:
    _INTERESTS[origin] = (
        TopicInterest(
            topic_key=decision.topic_key,
            topic_type=decision.topic_type,
            reason=decision.reason,
        ),
        time.monotonic() + INTEREST_SECONDS,
    )


def _plain_text(event) -> str:
    parts: list[str] = []
    for segment in event.get_messages():
        if isinstance(segment, Plain):
            parts.append(segment.text)
    return "".join(parts).strip()


def get_other_bot_ids(event=None) -> set[str]:
    return PROFILE_OTHER_BOT_IDS.get(read_bot_profile(event), PROFILE_OTHER_BOT_IDS["demon"])


def read_bot_profile(event=None) -> str:
    if event is not None:
        profile = PROFILE_BY_BOT_ID.get(str(event.get_self_id() or "").strip())
        if profile:
            return profile
    profile = os.environ.get(PROFILE_ENV, "demon").strip().lower()
    if profile in PROFILE_OTHER_BOT_IDS:
        return profile
    return "demon"


def _has_at_bot(event) -> bool:
    return any(isinstance(segment, At) and str(segment.qq) == str(event.get_self_id()) for segment in event.get_messages())


def _has_reply_bot(event) -> bool:
    return any(
        isinstance(segment, Reply) and str(segment.sender_id) == str(event.get_self_id())
        for segment in event.get_messages()
    )


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
        raise ValueError("active reply decision is not a JSON object")
    return data


def _clean_json_string(value: object) -> str:
    return str(value or "").strip()
