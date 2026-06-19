from __future__ import annotations

from collections import defaultdict, deque
import json
import os
import re
import time

from astrbot.api import logger
from astrbot.api.message_components import At, Plain, Reply
from astrbot.api.platform import MessageType
from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register
from astrbot.builtin_stars.astrbot.group_chat_context import GroupChatContext
from astrbot.core.star.filter.event_message_type import EventMessageType

from .logic import TopicDecision
from .logic import TopicInterest
from .logic import TopicRecordResult
from .logic import TopicWindowMessage
from .logic import build_active_reply_decision_prompt as _build_active_reply_decision_prompt
from .logic import build_batch_active_reply_decision_prompt as _build_batch_active_reply_decision_prompt
from .logic import release_active_reply_inflight as _release_active_reply_inflight
from .logic import active_reply_scope_key as _active_reply_scope_key
from .logic import chat_with_current_provider as _chat_with_current_decision_provider
from .logic import compact_text as _compact
from .logic import is_recent_duplicate_observation as _is_recent_duplicate_observation
from .logic import looks_like_qqbot_fixed_command
from .logic import looks_like_direct_bot_call
from .logic import should_run_batch_decision as _should_run_batch_decision
from .logic import should_skip_unresolved_media_active_reply as _should_skip_unresolved_media_active_reply
from .logic import should_force_active_reply_for_named_call as _should_force_named_call_reply
from .logic import should_consider_active_window as _should_consider_active_window
from .logic import try_acquire_active_reply_inflight as _try_acquire_active_reply_inflight
from .twin_scheduler import complete_claim_response
from .twin_scheduler import decide_llm_worker
from .twin_scheduler import mark_worker_busy
from .twin_scheduler import mark_claim_processing
from .twin_scheduler import pop_pending_delegated_comment
from .twin_scheduler import record_worker_handled
from .twin_scheduler import release_worker
from .twin_scheduler import targeted_twin_ids
try:
    from astrbot_plugin_qqbot_features.request_context import build_current_request_context
    from astrbot_plugin_qqbot_features.request_context import canonical_event_claim_key
    from astrbot_plugin_qqbot_features.reply_style_guard_logic import build_delegated_comment_prompt_text
except ModuleNotFoundError:  # AstrBot runtime imports plugins as data.plugins.<name>.
    from data.plugins.astrbot_plugin_qqbot_features.request_context import build_current_request_context
    from data.plugins.astrbot_plugin_qqbot_features.request_context import canonical_event_claim_key
    from data.plugins.astrbot_plugin_qqbot_features.reply_style_guard_logic import build_delegated_comment_prompt_text


WINDOW_SECONDS = 600.0
MAX_WINDOW_MESSAGES = 80
MAX_ACTIVE_HISTORY_MESSAGES = 80
MAX_ACTIVE_HISTORY_CHARS = 6000
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
_BATCH_DECISION_AT: dict[str, float] = {}
LLM_WORKER_SELECTED_EXTRA = "_qqbot_twin_llm_worker_selected"
LLM_WORKER_CLAIM_KEY_EXTRA = "_qqbot_twin_llm_worker_claim_key"
LLM_WORKER_BOTH_TARGETED_EXTRA = "_qqbot_twin_llm_both_targeted"
DELEGATED_COMMENT_EXTRA = "_qqbot_twin_delegated_comment"


@register(
    "astrbot_plugin_topic_concentration",
    "MengLei",
    "棉花糖普通群聊主动接话门控。",
    "0.3.11",
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

    @filter.event_message_type(EventMessageType.ALL, priority=1000, desc="双棉花糖普通 LLM worker 调度；固定命令不参与负载均衡。")
    async def schedule_direct_llm_worker(self, event):
        comment = pop_pending_delegated_comment(
            group_id=event.get_group_id(),
            commenter_id=event.get_self_id(),
            responder_id=event.get_sender_id(),
        )
        if comment is not None:
            logger.info(
                "[TopicConcentration] delegated comment started: group=%s commenter=%s responder=%s",
                event.get_group_id(),
                comment.commenter_id,
                comment.responder_id,
            )
            event.set_extra(DELEGATED_COMMENT_EXTRA, "1")
            yield event.request_llm(
                prompt=_build_delegated_comment_prompt(comment),
                contexts=[],
            )
            event.stop_event()
            return
        if not _is_llm_schedulable_event(event):
            return
        text = _plain_text(event) or str(event.get_message_str() or "")
        if looks_like_qqbot_fixed_command(text):
            return
        decision = decide_llm_worker(
            self_id=event.get_self_id(),
            at_ids=_at_target_ids(event),
            reply_sender_id=_reply_target_id(event),
            message_key=_llm_message_key(event),
            group_id=event.get_group_id(),
            original_text=text,
            private_chat=event.is_private_chat(),
            allow_multi_target=True,
        )
        if not decision.should_handle:
            event.should_call_llm(True)
            event.stop_event()
            logger.info(
                "[TopicConcentration] skip direct LLM: self=%s selected=%s reason=%s claim=%s group=%s targets=%s balance=%.2f p_angel=%.2f",
                event.get_self_id(),
                decision.worker_id,
                decision.reason,
                decision.claim_key,
                event.get_group_id(),
                ",".join(_at_target_ids(event)),
                decision.balance_before,
                decision.angel_probability,
            )
            return
        event.is_wake = True
        event.is_at_or_wake_command = True
        event.set_extra(LLM_WORKER_SELECTED_EXTRA, decision.worker_id)
        event.set_extra(LLM_WORKER_CLAIM_KEY_EXTRA, decision.claim_key)
        event.set_extra(LLM_WORKER_BOTH_TARGETED_EXTRA, "1" if decision.both_targeted else "")
        if decision.delegated_from:
            event.set_extra("_qqbot_twin_llm_delegated_from", decision.delegated_from)
        logger.info(
            "[TopicConcentration] allow direct LLM: self=%s selected=%s reason=%s delegated_from=%s both_targeted=%s claim=%s group=%s targets=%s balance=%.2f p_angel=%.2f",
            event.get_self_id(),
            decision.worker_id,
            decision.reason,
            decision.delegated_from,
            decision.both_targeted,
            decision.claim_key,
            event.get_group_id(),
            ",".join(_at_target_ids(event)),
            decision.balance_before,
            decision.angel_probability,
        )

    @filter.on_llm_request(desc="标记当前双棉花糖 worker 正在等待普通 LLM 返回。")
    async def mark_direct_llm_worker_busy(self, event, req):
        selected = str(event.get_extra(LLM_WORKER_SELECTED_EXTRA, "") or "")
        if not selected:
            return
        if selected != str(event.get_self_id() or ""):
            event.should_call_llm(True)
            event.stop_event()
            return
        claim_key = str(event.get_extra(LLM_WORKER_CLAIM_KEY_EXTRA, "") or "")
        mark_claim_processing(claim_key, selected)
        mark_worker_busy(selected)
        delegated_from = str(event.get_extra("_qqbot_twin_llm_delegated_from", "") or "")
        logger.info(
            "[TopicConcentration] mark direct LLM worker busy: worker=%s session=%s request_session=%s claim=%s delegated_from=%s",
            selected,
            getattr(event, "unified_msg_origin", ""),
            getattr(req, "session_id", ""),
            claim_key,
            delegated_from,
        )

    @filter.on_llm_response(desc="释放当前双棉花糖普通 LLM worker。")
    async def release_direct_llm_worker(self, event, response):
        if str(event.get_extra(DELEGATED_COMMENT_EXTRA, "") or "").strip():
            logger.info(
                "[TopicConcentration] delegated comment response completed: group=%s self=%s session=%s",
                event.get_group_id(),
                event.get_self_id(),
                getattr(event, "unified_msg_origin", ""),
            )
            return
        selected = str(event.get_extra(LLM_WORKER_SELECTED_EXTRA, "") or "")
        if not selected:
            return
        release_worker(selected)
        claim_key = str(event.get_extra(LLM_WORKER_CLAIM_KEY_EXTRA, "") or "")
        comment = complete_claim_response(
            claim_key,
            selected,
            _response_text(response),
        )
        if not claim_key:
            record_worker_handled(event.get_group_id(), selected)
        logger.info(
            "[TopicConcentration] release direct LLM worker: worker=%s session=%s claim=%s comment_required_for=%s",
            selected,
            getattr(event, "unified_msg_origin", ""),
            claim_key,
            comment.commenter_id if comment is not None else "",
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
            now = time.monotonic()
            worker_decision = decide_llm_worker(
                self_id=event.get_self_id(),
                at_ids=(),
                message_key=f"active:{_llm_message_key(event)}",
                group_id=event.get_group_id(),
                original_text=_plain_text(event),
                now=now,
            )
            if not worker_decision.should_handle:
                logger.info(
                    "[TopicConcentration] skip active reply: "
                    f"group={event.get_group_id()} reason={worker_decision.reason} "
                    f"selected={worker_decision.worker_id} claim={worker_decision.claim_key} "
                    f"balance={worker_decision.balance_before:.2f} p_angel={worker_decision.angel_probability:.2f}"
                )
                return False
            event.set_extra(LLM_WORKER_SELECTED_EXTRA, worker_decision.worker_id)
            event.set_extra(LLM_WORKER_CLAIM_KEY_EXTRA, worker_decision.claim_key)
            record = _record_message(event, scope_key=scope_key)
            if record.duplicate:
                logger.debug(
                    "[TopicConcentration] skip active reply: "
                    f"group={event.get_group_id()} reason=duplicate_dual_platform_event"
                )
                return False
            if not _should_consider_window(record.window, event=event):
                logger.debug(
                    "[TopicConcentration] skip active reply: "
                    f"group={event.get_group_id()} reason=weak_window"
                )
                return False
            if _should_force_named_call_reply(record.window):
                event.is_wake = True
                event.is_at_or_wake_command = True
                logger.info(
                    "[TopicConcentration] allow active reply: "
                    f"group={event.get_group_id()} topic=direct_named_call "
                    f"type=direct_call style=casual max_length=short "
                    f"worker={worker_decision.worker_id} reason=local_named_call"
                )
                return True
            request_context = build_current_request_context(event)
            if _should_skip_unresolved_media_active_reply(
                record.window,
                latest_text=request_context.current_text,
                named_call=request_context.named_call,
            ):
                logger.info(
                    "[TopicConcentration] skip active reply: "
                    f"group={event.get_group_id()} reason=unresolved_media_context"
                )
                return False
            batch_gate = _should_run_batch_decision(
                record.window,
                now=now,
                last_decision_at=_BATCH_DECISION_AT.get(scope_key, 0.0),
            )
            if not batch_gate.should_run:
                logger.info(
                    "[TopicConcentration] skip active reply: "
                    f"group={event.get_group_id()} reason={batch_gate.reason} "
                    f"effective_messages={batch_gate.effective_count}"
                )
                return False
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
                "[TopicConcentration] batch active reply decision started: "
                f"group={event.get_group_id()} scope={scope_key} "
                f"reason={batch_gate.reason} effective_messages={batch_gate.effective_count}"
            )
            try:
                decision = await _decide_with_ai(group_context, event, record.window, scope_key=scope_key)
                _BATCH_DECISION_AT[scope_key] = now
                elapsed = time.monotonic() - started
                if decision is None:
                    logger.info(
                        "[TopicConcentration] skip active reply: "
                        f"group={event.get_group_id()} reason=decision_failed elapsed={elapsed:.2f}s"
                    )
                    return False
                if not decision.should_reply:
                    logger.info(
                        "[TopicConcentration] skip active reply: "
                        f"group={event.get_group_id()} should_reply=false topic={decision.topic_key} "
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
                    f"max_length={decision.max_length} worker={worker_decision.worker_id} "
                    f"elapsed={elapsed:.2f}s reason={decision.reason}"
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
            unresolved_media_context=build_current_request_context(event).unresolved_media_context,
            created_at=now,
        )
    )
    while len(window) > MAX_WINDOW_MESSAGES:
        window.popleft()
    return TopicRecordResult(window=window, duplicate=False)


def _should_consider_window(window: deque[TopicWindowMessage], *, event=None) -> bool:
    request_context = build_current_request_context(event) if event is not None else None
    return _should_consider_active_window(
        window,
        named_call=bool(request_context and request_context.named_call),
        has_reply_source=bool(request_context and request_context.reply_texts),
    )


async def _decide_with_ai(
    group_context: GroupChatContext,
    event,
    window: deque[TopicWindowMessage],
    *,
    scope_key: str,
) -> TopicDecision | None:
    if not any(_compact(message.text) for message in window):
        return None
    prompt = _build_decision_prompt(
        window,
        event=event,
        group_context=group_context,
        active_interest=_get_interest(scope_key),
    )
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
    event=None,
    group_context: GroupChatContext | None = None,
    active_interest: TopicInterest | None,
) -> str:
    request_context = build_current_request_context(event) if event is not None else None
    if request_context is not None and not request_context.named_call and not request_context.reply_texts:
        return _build_batch_active_reply_decision_prompt(
            window,
            history_lines=_active_history_lines(group_context, event),
            active_interest=active_interest,
        )
    latest_text = request_context.current_text if request_context is not None else (window[-1].text if window else "")
    return _build_active_reply_decision_prompt(
        window,
        current_query=request_context.combined_query if request_context is not None else "",
        named_call=bool(request_context and request_context.named_call),
        has_reply_source=bool(request_context and request_context.reply_texts),
        latest_text=latest_text,
        history_lines=_active_history_lines(group_context, event),
        active_interest=active_interest,
    )


def _active_history_lines(group_context: GroupChatContext | None, event) -> list[str]:
    if group_context is None or event is None:
        return []
    records_by_origin = getattr(group_context, "raw_records", {})
    try:
        records = list(records_by_origin.get(event.unified_msg_origin, []))
    except Exception:
        return []
    if not records:
        return []
    selected = records[-MAX_ACTIVE_HISTORY_MESSAGES:]
    lines: list[str] = []
    total_chars = 0
    for record in selected:
        text = str(record or "").strip()
        if not text:
            continue
        total_chars += len(text)
        lines.append(text)
    while lines and total_chars > MAX_ACTIVE_HISTORY_CHARS:
        total_chars -= len(lines.pop(0))
    return lines


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


def _build_delegated_comment_prompt(comment) -> str:
    return build_delegated_comment_prompt_text(
        current_id=comment.commenter_id,
        responder_id=comment.responder_id,
        original_text=comment.original_text,
        response_text=comment.response_text,
    )


def _response_text(response) -> str:
    text = str(getattr(response, "completion_text", "") or "").strip()
    if text:
        return text
    chain = getattr(response, "result_chain", None)
    if not chain:
        return ""
    parts: list[str] = []
    for item in chain:
        value = str(getattr(item, "text", "") or "").strip()
        if value:
            parts.append(value)
    return "\n".join(parts).strip()


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


def _is_llm_schedulable_event(event) -> bool:
    if str(event.get_sender_id() or "") in get_other_bot_ids(event):
        return False
    if event.get_self_id() == event.get_sender_id():
        return False
    if event.is_private_chat():
        return True
    if getattr(event, "is_at_or_wake_command", False):
        return True
    if targeted_twin_ids(_at_target_ids(event)):
        return True
    if looks_like_direct_bot_call(_plain_text(event) or str(event.get_message_str() or "")):
        return True
    return bool(_reply_target_id(event) in targeted_twin_ids(_reply_target_id(event)))


def _at_target_ids(event) -> tuple[str, ...]:
    return tuple(str(segment.qq) for segment in event.get_messages() if isinstance(segment, At))


def _reply_target_id(event) -> str:
    for segment in event.get_messages():
        if isinstance(segment, Reply):
            return str(segment.sender_id or "")
    return ""


def _llm_message_key(event) -> str:
    return canonical_event_claim_key(event, purpose="llm")


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
