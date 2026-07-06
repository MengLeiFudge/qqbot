from __future__ import annotations

from dataclasses import dataclass
import os
import time

from astrbot.api import logger
from astrbot.api.event import filter
from astrbot.api.message_components import At, Plain, Reply
from astrbot.api.star import Context, Star, register
from astrbot.core.agent.message import TextPart
from astrbot.core.star.filter.event_message_type import EventMessageType

from .logic import FOLLOWUP_END_MARKER
from .logic import FOLLOWUP_MAX_MESSAGES
from .logic import FOLLOWUP_WINDOW_SECONDS
from .logic import build_call_intent_prompt
from .logic import build_followup_instruction
from .logic import chat_with_current_provider as _chat_with_current_decision_provider
from .logic import classify_cotton_candy_call
from .logic import contains_cotton_candy_marker
from .logic import looks_like_low_information
from .logic import looks_like_qqbot_fixed_command
from .logic import parse_call_intent_response
from .logic import strip_followup_end_marker
from .twin_scheduler import complete_claim_response
from .twin_scheduler import decide_llm_worker
from .twin_scheduler import mark_claim_processing
from .twin_scheduler import mark_worker_busy
from .twin_scheduler import record_worker_handled
from .twin_scheduler import release_worker
from .twin_scheduler import targeted_twin_ids

try:
    from astrbot_plugin_qqbot_features.request_context import canonical_event_claim_key
    from astrbot_plugin_qqbot_features.twin_interaction_logic import collect_target_twin_ids
except ModuleNotFoundError:  # AstrBot runtime imports plugins as data.plugins.<name>.
    from data.plugins.astrbot_plugin_qqbot_features.request_context import canonical_event_claim_key
    from data.plugins.astrbot_plugin_qqbot_features.twin_interaction_logic import collect_target_twin_ids


PROFILE_ENV = "QQBOT_ASTRBOT_PROFILE"
PROFILE_OTHER_BOT_IDS = {
    "angel": {"2629227874"},
    "demon": {"1443944862"},
}
PROFILE_BY_BOT_ID = {
    "1443944862": "angel",
    "2629227874": "demon",
}
LLM_WORKER_SELECTED_EXTRA = "_qqbot_twin_llm_worker_selected"
LLM_WORKER_CLAIM_KEY_EXTRA = "_qqbot_twin_llm_worker_claim_key"
LLM_WORKER_BOTH_TARGETED_EXTRA = "_qqbot_twin_llm_both_targeted"
FOLLOWUP_ACTIVE_EXTRA = "_qqbot_followup_active"
FOLLOWUP_REASON_EXTRA = "_qqbot_followup_reason"


@dataclass(frozen=True, slots=True)
class FollowupState:
    worker_id: str
    expires_at: float
    remaining_messages: int
    reason: str


_FOLLOWUPS: dict[tuple[str, str, str], FollowupState] = {}


@register(
    "astrbot_plugin_topic_concentration",
    "MengLei",
    "棉花糖显式呼叫、follow-up 与双 bot 普通 LLM worker 调度。",
    "0.4.0",
)
class TopicConcentrationPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        logger.info(
            "[TopicConcentration] loaded explicit trigger gate: profile=%s other_bot_ids=%s followup_seconds=%.0f",
            read_bot_profile(),
            sorted(get_other_bot_ids()),
            FOLLOWUP_WINDOW_SECONDS,
        )

    @filter.event_message_type(EventMessageType.ALL, priority=1000, desc="双棉花糖普通 LLM worker 调度；固定命令不参与负载均衡。")
    async def schedule_direct_llm_worker(self, event):
        if not _is_candidate_event(event):
            return
        text = _plain_text(event) or str(event.get_message_str() or "")
        if looks_like_qqbot_fixed_command(text):
            return

        at_ids = _at_target_ids(event)
        reply_target_id = _reply_target_id(event)
        target_ids = collect_target_twin_ids(at_ids, reply_target_id)
        explicit_target = bool(target_ids or event.is_private_chat())
        followup = _read_followup(event)
        reason = "direct"
        effective_at_ids = at_ids
        if followup is not None and not explicit_target:
            reason = "followup"
            effective_at_ids = (followup.worker_id,)
        elif not explicit_target:
            if contains_cotton_candy_marker(text):
                call_reason = await _decide_named_call(self.context, event, text)
                if call_reason is None:
                    event.should_call_llm(True)
                    event.stop_event()
                    return
                reason = call_reason
            elif getattr(event, "is_at_or_wake_command", False):
                reason = "direct_wake"
            else:
                return

        decision = decide_llm_worker(
            self_id=event.get_self_id(),
            at_ids=effective_at_ids,
            reply_sender_id=reply_target_id,
            message_key=_llm_message_key(event, reason=reason),
            group_id=event.get_group_id(),
            original_text=text,
            private_chat=event.is_private_chat(),
            allow_multi_target=True,
            allow_delegation=False,
        )
        if not decision.should_handle:
            event.should_call_llm(True)
            event.stop_event()
            logger.info(
                "[TopicConcentration] skip LLM: self=%s selected=%s reason=%s trigger=%s claim=%s group=%s targets=%s balance=%.2f p_angel=%.2f",
                event.get_self_id(),
                decision.worker_id,
                decision.reason,
                reason,
                decision.claim_key,
                event.get_group_id(),
                ",".join(target_ids),
                decision.balance_before,
                decision.angel_probability,
            )
            return

        event.is_wake = True
        event.is_at_or_wake_command = True
        event.set_extra(LLM_WORKER_SELECTED_EXTRA, decision.worker_id)
        event.set_extra(LLM_WORKER_CLAIM_KEY_EXTRA, decision.claim_key)
        event.set_extra(LLM_WORKER_BOTH_TARGETED_EXTRA, "1" if decision.both_targeted else "")
        event.set_extra(FOLLOWUP_REASON_EXTRA, reason)
        if followup is not None and reason == "followup":
            event.set_extra(FOLLOWUP_ACTIVE_EXTRA, "1")
        logger.info(
            "[TopicConcentration] allow LLM: self=%s selected=%s decision_reason=%s trigger=%s both_targeted=%s claim=%s group=%s targets=%s balance=%.2f p_angel=%.2f",
            event.get_self_id(),
            decision.worker_id,
            decision.reason,
            reason,
            decision.both_targeted,
            decision.claim_key,
            event.get_group_id(),
            ",".join(target_ids),
            decision.balance_before,
            decision.angel_probability,
        )

    @filter.on_llm_request(desc="标记当前双棉花糖 worker 正在等待普通 LLM 返回，并注入 follow-up 结束标记规则。")
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
        if str(event.get_extra(FOLLOWUP_ACTIVE_EXTRA, "") or "").strip():
            req.extra_user_content_parts.append(TextPart(text=build_followup_instruction()).mark_as_temp())
        logger.info(
            "[TopicConcentration] mark LLM worker busy: worker=%s session=%s request_session=%s claim=%s followup=%s marker=%s",
            selected,
            getattr(event, "unified_msg_origin", ""),
            getattr(req, "session_id", ""),
            claim_key,
            bool(str(event.get_extra(FOLLOWUP_ACTIVE_EXTRA, "") or "").strip()),
            FOLLOWUP_END_MARKER,
        )

    @filter.on_llm_response(desc="释放当前双棉花糖普通 LLM worker，并刷新或结束 follow-up 窗口。")
    async def release_direct_llm_worker(self, event, response):
        selected = str(event.get_extra(LLM_WORKER_SELECTED_EXTRA, "") or "")
        if not selected:
            return
        release_worker(selected)
        raw_text = _response_text(response)
        cleaned, ended = strip_followup_end_marker(raw_text)
        claim_key = str(event.get_extra(LLM_WORKER_CLAIM_KEY_EXTRA, "") or "")
        complete_claim_response(claim_key, selected, cleaned)
        if not claim_key:
            record_worker_handled(event.get_group_id(), selected)
        _update_followup_after_response(event, selected, ended=ended)
        logger.info(
            "[TopicConcentration] release LLM worker: worker=%s session=%s claim=%s followup_ended=%s",
            selected,
            getattr(event, "unified_msg_origin", ""),
            claim_key,
            ended,
        )


async def _decide_named_call(context: Context, event, text: str) -> str | None:
    if not contains_cotton_candy_marker(text):
        return None
    local = classify_cotton_candy_call(text)
    if local == "call":
        return "named_call_local"
    if local == "non_call":
        logger.info(
            "[TopicConcentration] skip named call locally: group=%s text=%s",
            event.get_group_id(),
            _log_text(text),
        )
        return None
    response = await _chat_with_current_decision_provider(
        context=context,
        event=event,
        prompt=build_call_intent_prompt(text),
        session_id=f"topic_call_intent:{event.unified_msg_origin}",
        logger=logger,
    )
    if response is None:
        return None
    decision = parse_call_intent_response(getattr(response, "completion_text", "") or "")
    if decision is None:
        logger.info(
            "[TopicConcentration] skip named call: decision_parse_failed group=%s text=%s",
            event.get_group_id(),
            _log_text(text),
        )
        return None
    if not decision.should_reply:
        logger.info(
            "[TopicConcentration] skip named call by AI: group=%s reason=%s text=%s",
            event.get_group_id(),
            decision.reason,
            _log_text(text),
        )
        return None
    logger.info(
        "[TopicConcentration] allow named call by AI: group=%s reason=%s text=%s",
        event.get_group_id(),
        decision.reason,
        _log_text(text),
    )
    return "named_call_ai"


def _read_followup(event) -> FollowupState | None:
    if event.is_private_chat():
        return None
    if looks_like_low_information(_plain_text(event) or str(event.get_message_str() or "")):
        return None
    group_key = _group_key(event)
    user_id = str(event.get_sender_id() or "").strip()
    self_id = str(event.get_self_id() or "").strip()
    if not group_key or not user_id or not self_id:
        return None
    key = (group_key, user_id, self_id)
    state = _FOLLOWUPS.get(key)
    now = time.monotonic()
    if state is None or state.expires_at <= now or state.remaining_messages <= 0:
        _FOLLOWUPS.pop(key, None)
        return None
    return state


def _update_followup_after_response(event, worker_id: str, *, ended: bool) -> None:
    if event.is_private_chat():
        return
    group_key = _group_key(event)
    user_id = str(event.get_sender_id() or "").strip()
    worker = str(worker_id or "").strip()
    if not group_key or not user_id or not worker:
        return
    key = (group_key, user_id, worker)
    reason = str(event.get_extra(FOLLOWUP_REASON_EXTRA, "") or "").strip()
    if ended:
        _FOLLOWUPS.pop(key, None)
        return
    if reason not in {"direct", "direct_wake", "named_call_local", "named_call_ai", "followup"}:
        return
    previous = _FOLLOWUPS.get(key)
    remaining = FOLLOWUP_MAX_MESSAGES
    if reason == "followup" and previous is not None:
        remaining = max(0, previous.remaining_messages - 1)
    if remaining <= 0:
        _FOLLOWUPS.pop(key, None)
        return
    _FOLLOWUPS[key] = FollowupState(
        worker_id=worker,
        expires_at=time.monotonic() + FOLLOWUP_WINDOW_SECONDS,
        remaining_messages=remaining,
        reason=reason,
    )


def _is_candidate_event(event) -> bool:
    sender_id = str(event.get_sender_id() or "")
    if sender_id in get_other_bot_ids(event):
        return False
    if str(event.get_self_id() or "") == sender_id:
        return False
    if event.is_private_chat():
        return True
    if getattr(event, "is_at_or_wake_command", False):
        return True
    if targeted_twin_ids(_at_target_ids(event)):
        return True
    reply_target_id = _reply_target_id(event)
    if targeted_twin_ids((reply_target_id,)):
        return True
    if _read_followup(event) is not None:
        return True
    return contains_cotton_candy_marker(_plain_text(event) or str(event.get_message_str() or ""))


def _plain_text(event) -> str:
    parts: list[str] = []
    for segment in event.get_messages():
        if isinstance(segment, Plain):
            parts.append(segment.text)
    return "".join(parts).strip()


def _at_target_ids(event) -> tuple[str, ...]:
    return tuple(str(segment.qq) for segment in event.get_messages() if isinstance(segment, At))


def _reply_target_id(event) -> str:
    for segment in event.get_messages():
        if isinstance(segment, Reply):
            return str(segment.sender_id or "")
    return ""


def _llm_message_key(event, *, reason: str) -> str:
    return canonical_event_claim_key(event, purpose=f"llm:{reason}")


def _group_key(event) -> str:
    group_id = str(event.get_group_id() or "").strip()
    if group_id:
        return f"group:{group_id}"
    return str(getattr(event, "unified_msg_origin", "") or "").strip()


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


def _log_text(text: str) -> str:
    return " ".join(str(text or "").split())[:80]
