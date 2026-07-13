from __future__ import annotations

import os

from astrbot.api import logger
from astrbot.api.event import filter
from astrbot.api.message_components import At, Plain, Poke, Reply
from astrbot.api.star import Context, Star, register
from astrbot.core.agent.message import TextPart
from astrbot.core.star.filter.event_message_type import EventMessageType

from .logic import ACTIVATION_WINDOW_SECONDS
from .logic import DEACTIVATE_MARKER
from .logic import SKIP_REPLY_MARKER
from .logic import activate_group_chat
from .logic import build_call_intent_prompt
from .logic import build_group_activation_instruction
from .logic import chat_with_current_provider as _chat_with_current_decision_provider
from .logic import classify_cotton_candy_call
from .logic import clear_group_activations
from .logic import contains_cotton_candy_marker
from .logic import deactivate_group_chat
from .logic import looks_like_qqbot_fixed_command
from .logic import parse_call_intent_response
from .logic import parse_reply_control
from .logic import read_group_activation
from .logic import renew_group_chat_after_reply
from .logic import retry_explicit_visible_reply
from .logic import rewrite_last_assistant_history
from .logic import should_activate_from_poke
from .logic import should_normalize_empty_mention
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
LLM_ROUTE_EXTRA = "_qqbot_group_activation_route"
ACTIVATION_RENEWALS_EXTRA = "_qqbot_group_activation_renewals"
ACTIVATION_GENERATION_EXTRA = "_qqbot_group_activation_generation"
ACTIVATION_REQUEST_EXTRA = "_qqbot_group_activation_provider_request"
RETRY_VISIBLE_TEXT_EXTRA = "_qqbot_group_activation_retry_visible_text"
PENDING_STATE_ACTION_EXTRA = "_qqbot_group_activation_pending_action"
EMPTY_MENTION_CALL_EXTRA = "_qqbot_empty_mention_call"
ROUTE_PRIVATE = "private"
ROUTE_EXPLICIT = "explicit"
ROUTE_CANDIDATE = "candidate"
ACTION_RENEW_EXPLICIT = "renew_explicit"
ACTION_RENEW_CANDIDATE = "renew_candidate"
ACTION_DEACTIVATE = "deactivate"
POKE_CALL_TEXT = "用户拍了拍你"
EMPTY_MENTION_CALL_TEXT = "用户只@了你，没有附带其他内容"


@register(
    "astrbot_plugin_topic_concentration",
    "MengLei",
    "棉花糖群聊激活状态、显式呼叫与双 bot 普通 LLM worker 调度。",
    "0.5.1",
)
class TopicConcentrationPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        clear_group_activations()
        logger.info(
            "[TopicConcentration] loaded group activation gate: profile=%s other_bot_ids=%s activation_seconds=%.0f markers=%s,%s",
            read_bot_profile(),
            sorted(get_other_bot_ids()),
            ACTIVATION_WINDOW_SECONDS,
            SKIP_REPLY_MARKER,
            DEACTIVATE_MARKER,
        )

    @filter.event_message_type(EventMessageType.ALL, priority=1000, desc="群聊激活状态与双棉花糖普通 LLM worker 调度；固定命令不参与。")
    async def schedule_direct_llm_worker(self, event):
        poke_target_id = _current_poke_target_id(event)
        if not _is_candidate_event(event, poke_target_id=poke_target_id):
            return
        at_ids = _at_target_ids(event)
        self_id = str(event.get_self_id() or "").strip()
        empty_mention = not event.is_private_chat() and should_normalize_empty_mention(
            self_id=self_id,
            at_target_ids=at_ids,
            has_other_content=_has_other_message_content(event),
        )
        if poke_target_id:
            event.message_str = POKE_CALL_TEXT
        elif empty_mention:
            event.message_str = EMPTY_MENTION_CALL_TEXT
            event.set_extra(EMPTY_MENTION_CALL_EXTRA, "1")
        text = _plain_text(event) or str(event.get_message_str() or "")
        if looks_like_qqbot_fixed_command(text):
            return

        reply_target_id = _reply_target_id(event)
        target_ids = collect_target_twin_ids(at_ids, reply_target_id)
        route = ""
        reason = ""
        effective_at_ids = at_ids
        activation_state = None

        if event.is_private_chat():
            route = ROUTE_PRIVATE
            reason = "private"
        elif poke_target_id:
            route = ROUTE_EXPLICIT
            reason = "poke"
            effective_at_ids = (self_id,)
            target_ids = (self_id,)
        elif empty_mention:
            route = ROUTE_EXPLICIT
            reason = "empty_mention"
            effective_at_ids = (self_id,)
            target_ids = (self_id,)
        elif target_ids:
            route = ROUTE_EXPLICIT
            reason = "direct"
        elif getattr(event, "is_at_or_wake_command", False):
            route = ROUTE_EXPLICIT
            reason = "direct_wake"
        else:
            activation_state = read_group_activation(event.get_group_id(), self_id)
            if contains_cotton_candy_marker(text):
                call_reason = await _decide_named_call(self.context, event, text)
                if call_reason is not None:
                    route = ROUTE_EXPLICIT
                    reason = call_reason
                elif activation_state is None:
                    event.should_call_llm(True)
                    event.stop_event()
                    return
            if not route and activation_state is not None:
                route = ROUTE_CANDIDATE
                reason = "active_candidate"
                effective_at_ids = (self_id,)
            if not route:
                return

        decision = decide_llm_worker(
            self_id=self_id,
            at_ids=effective_at_ids,
            reply_sender_id=reply_target_id,
            message_key=_llm_message_key(
                event,
                reason=reason,
                worker_scope=self_id if route == ROUTE_CANDIDATE else "",
            ),
            group_id=event.get_group_id(),
            original_text=text,
            private_chat=route == ROUTE_PRIVATE,
            allow_multi_target=True,
            allow_delegation=False,
            force_targeted=route == ROUTE_EXPLICIT and bool(target_ids),
            force_untargeted=route == ROUTE_EXPLICIT and not target_ids,
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

        if route == ROUTE_EXPLICIT:
            activation_state = activate_group_chat(event.get_group_id(), decision.worker_id)

        event.is_wake = True
        event.is_at_or_wake_command = True
        event.set_extra(LLM_WORKER_SELECTED_EXTRA, decision.worker_id)
        event.set_extra(LLM_WORKER_CLAIM_KEY_EXTRA, decision.claim_key)
        event.set_extra(LLM_WORKER_BOTH_TARGETED_EXTRA, "1" if decision.both_targeted else "")
        event.set_extra(LLM_ROUTE_EXTRA, route)
        event.set_extra(
            ACTIVATION_RENEWALS_EXTRA,
            activation_state.ordinary_reply_renewals if activation_state is not None else 0,
        )
        event.set_extra(
            ACTIVATION_GENERATION_EXTRA,
            activation_state.generation if activation_state is not None else 0,
        )
        logger.info(
            "[TopicConcentration] allow LLM: self=%s selected=%s route=%s decision_reason=%s trigger=%s renewals=%s both_targeted=%s claim=%s group=%s targets=%s balance=%.2f p_angel=%.2f",
            self_id,
            decision.worker_id,
            route,
            decision.reason,
            reason,
            activation_state.ordinary_reply_renewals if activation_state is not None else 0,
            decision.both_targeted,
            decision.claim_key,
            event.get_group_id(),
            ",".join(target_ids),
            decision.balance_before,
            decision.angel_probability,
        )

    @filter.on_llm_request(desc="标记当前 worker 正在等待普通 LLM 返回，并注入群聊激活控制协议。")
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
        route = str(event.get_extra(LLM_ROUTE_EXTRA, "") or "")
        if route in {ROUTE_EXPLICIT, ROUTE_CANDIDATE}:
            renewals = int(event.get_extra(ACTIVATION_RENEWALS_EXTRA, 0) or 0)
            req.extra_user_content_parts.append(
                TextPart(
                    text=build_group_activation_instruction(
                        explicit=route == ROUTE_EXPLICIT,
                        ordinary_reply_renewals=renewals,
                        empty_mention=bool(event.get_extra(EMPTY_MENTION_CALL_EXTRA, "")),
                    )
                ).mark_as_temp()
            )
        if route == ROUTE_EXPLICIT:
            event.set_extra(ACTIVATION_REQUEST_EXTRA, req)
        logger.info(
            "[TopicConcentration] mark LLM worker busy: worker=%s session=%s request_session=%s claim=%s route=%s renewals=%s markers=%s,%s",
            selected,
            getattr(event, "unified_msg_origin", ""),
            getattr(req, "session_id", ""),
            claim_key,
            route,
            int(event.get_extra(ACTIVATION_RENEWALS_EXTRA, 0) or 0),
            SKIP_REPLY_MARKER,
            DEACTIVATE_MARKER,
        )

    @filter.on_llm_response(
        priority=1000,
        desc="释放当前 worker，优先消费候选跳过/反激活标记并登记发送后的状态动作。",
    )
    async def release_direct_llm_worker(self, event, response):
        selected = str(event.get_extra(LLM_WORKER_SELECTED_EXTRA, "") or "")
        if not selected:
            return
        release_worker(selected)
        route = str(event.get_extra(LLM_ROUTE_EXTRA, "") or "")
        raw_text = _response_text(response)
        control = parse_reply_control(raw_text) if route in {ROUTE_EXPLICIT, ROUTE_CANDIDATE} else None
        if route == ROUTE_EXPLICIT and control is not None and not control.cleaned_text:
            retry_response = await retry_explicit_visible_reply(
                context=self.context,
                event=event,
                request=event.get_extra(ACTIVATION_REQUEST_EXTRA),
                logger=logger,
            )
            retry_text = _response_text(retry_response)
            retry_control = parse_reply_control(retry_text) if retry_text else None
            if retry_control is not None and retry_control.cleaned_text and response is not None:
                response.completion_text = retry_text
                event.set_extra(RETRY_VISIBLE_TEXT_EXTRA, retry_control.cleaned_text)
                raw_text = retry_text
                control = retry_control
            else:
                if response is not None:
                    _apply_reply_control(response, "", suppress=True)
                control = parse_reply_control("")
                logger.error(
                    "[TopicConcentration] explicit visible reply retry still invalid: worker=%s group=%s",
                    selected,
                    event.get_group_id(),
                )
        suppress_reply = bool(control and control.skip_reply and route == ROUTE_CANDIDATE)
        if control is not None and (control.skip_reply or control.deactivate):
            _apply_reply_control(response, control.cleaned_text, suppress=suppress_reply or not control.cleaned_text)

        claim_key = str(event.get_extra(LLM_WORKER_CLAIM_KEY_EXTRA, "") or "")
        cleaned_text = _response_text(response)
        visible_reply = bool(cleaned_text)

        if suppress_reply:
            if control and control.deactivate:
                deactivate_group_chat(
                    event.get_group_id(),
                    selected,
                    expected_generation=int(event.get_extra(ACTIVATION_GENERATION_EXTRA, 0) or 0),
                )
            logger.info(
                "[TopicConcentration] model skipped candidate reply: worker=%s group=%s renewals=%s deactivate=%s",
                selected,
                event.get_group_id(),
                int(event.get_extra(ACTIVATION_RENEWALS_EXTRA, 0) or 0),
                bool(control and control.deactivate),
            )
            return

        if visible_reply:
            complete_claim_response(claim_key, selected, cleaned_text)
            if not claim_key:
                record_worker_handled(event.get_group_id(), selected)

        if control and control.deactivate:
            if visible_reply:
                event.set_extra(PENDING_STATE_ACTION_EXTRA, ACTION_DEACTIVATE)
            else:
                deactivate_group_chat(
                    event.get_group_id(),
                    selected,
                    expected_generation=int(event.get_extra(ACTIVATION_GENERATION_EXTRA, 0) or 0),
                )
        elif visible_reply and route == ROUTE_EXPLICIT:
            event.set_extra(PENDING_STATE_ACTION_EXTRA, ACTION_RENEW_EXPLICIT)
        elif visible_reply and route == ROUTE_CANDIDATE:
            event.set_extra(PENDING_STATE_ACTION_EXTRA, ACTION_RENEW_CANDIDATE)

        if control and control.skip_reply and route == ROUTE_EXPLICIT:
            logger.warning(
                "[TopicConcentration] explicit reply contained forbidden skip marker: worker=%s group=%s has_visible_text=%s",
                selected,
                event.get_group_id(),
                visible_reply,
            )
        logger.info(
            "[TopicConcentration] release LLM worker: worker=%s session=%s claim=%s route=%s visible=%s skip=%s deactivate=%s pending=%s",
            selected,
            getattr(event, "unified_msg_origin", ""),
            claim_key,
            route,
            visible_reply,
            bool(control and control.skip_reply),
            bool(control and control.deactivate),
            event.get_extra(PENDING_STATE_ACTION_EXTRA, ""),
        )

    @filter.on_agent_done(desc="从即将持久化的 assistant 历史中移除群聊激活内部控制标记。")
    async def strip_activation_markers_from_history(self, event, run_context, response):
        if str(event.get_extra(LLM_ROUTE_EXTRA, "") or "") not in {ROUTE_EXPLICIT, ROUTE_CANDIDATE}:
            return
        rewrite_last_assistant_history(
            getattr(run_context, "messages", None),
            replacement_text=str(event.get_extra(RETRY_VISIBLE_TEXT_EXTRA, "") or ""),
        )

    @filter.after_message_sent(desc="普通 LLM 消息发送后刷新或关闭当前群当前 bot 的激活状态。")
    async def update_activation_after_message_sent(self, event):
        action = str(event.get_extra(PENDING_STATE_ACTION_EXTRA, "") or "")
        selected = str(event.get_extra(LLM_WORKER_SELECTED_EXTRA, "") or "")
        if not action or not selected or event.is_private_chat():
            return
        group_id = event.get_group_id()
        generation = int(event.get_extra(ACTIVATION_GENERATION_EXTRA, 0) or 0)
        if action == ACTION_DEACTIVATE:
            applied = deactivate_group_chat(
                group_id,
                selected,
                expected_generation=generation,
            )
            state = None
        elif action == ACTION_RENEW_EXPLICIT:
            state = renew_group_chat_after_reply(
                group_id,
                selected,
                explicit=True,
                expected_generation=generation,
            )
            applied = state is not None
        elif action == ACTION_RENEW_CANDIDATE:
            state = renew_group_chat_after_reply(
                group_id,
                selected,
                explicit=False,
                expected_generation=generation,
            )
            applied = state is not None
        else:
            return
        event.set_extra(PENDING_STATE_ACTION_EXTRA, "")
        logger.info(
            "[TopicConcentration] applied group activation state: action=%s group=%s worker=%s generation=%s applied=%s renewals=%s",
            action,
            group_id,
            selected,
            generation,
            applied,
            state.ordinary_reply_renewals if state is not None else 0,
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


def _is_candidate_event(event, *, poke_target_id: str = "") -> bool:
    sender_id = str(event.get_sender_id() or "")
    if sender_id in PROFILE_BY_BOT_ID:
        return False
    if str(event.get_self_id() or "") == sender_id:
        return False
    post_type = _event_post_type(event)
    if post_type and post_type != "message":
        return bool(poke_target_id)
    if event.is_private_chat():
        return True
    if getattr(event, "is_at_or_wake_command", False):
        return True
    if targeted_twin_ids(_at_target_ids(event)):
        return True
    reply_target_id = _reply_target_id(event)
    if targeted_twin_ids((reply_target_id,)):
        return True
    if read_group_activation(event.get_group_id(), event.get_self_id()) is not None:
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


def _has_other_message_content(event) -> bool:
    for segment in event.get_messages():
        if isinstance(segment, At):
            continue
        if isinstance(segment, Plain) and not str(segment.text or "").strip():
            continue
        return True
    return False


def _reply_target_id(event) -> str:
    for segment in event.get_messages():
        if isinstance(segment, Reply):
            return str(segment.sender_id or "")
    return ""


def _llm_message_key(event, *, reason: str, worker_scope: str = "") -> str:
    purpose = f"llm:{reason}"
    if worker_scope:
        purpose += f":worker:{worker_scope}"
    return canonical_event_claim_key(event, purpose=purpose)


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


def _current_poke_target_id(event) -> str:
    self_id = str(event.get_self_id() or "").strip()
    sender_id = str(event.get_sender_id() or "").strip()
    for segment in event.get_messages():
        if not isinstance(segment, Poke):
            continue
        target_reader = getattr(segment, "target_id", None)
        target_id = str(target_reader() if callable(target_reader) else getattr(segment, "id", "") or "").strip()
        if should_activate_from_poke(
            self_id=self_id,
            user_id=sender_id,
            target_id=target_id,
            bot_ids=tuple(PROFILE_BY_BOT_ID),
        ):
            return target_id
    return ""


def _event_post_type(event) -> str:
    raw = getattr(getattr(event, "message_obj", None), "raw_message", None)
    getter = getattr(raw, "get", None)
    if not callable(getter):
        return ""
    try:
        return str(getter("post_type") or "").strip()
    except Exception:
        return ""


def _apply_reply_control(response, cleaned_text: str, *, suppress: bool) -> None:
    if response is None:
        return
    if suppress:
        response.result_chain = None
        response.completion_text = ""
        response.reasoning_content = None
        response.reasoning_signature = None
        return
    response.completion_text = cleaned_text


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
