from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass


TWIN_WORKER_IDS = ("1443944862", "2629227874")
WORKER_BUSY_LEASE_SECONDS = 600.0
MESSAGE_CLAIM_LEASE_SECONDS = 60.0
GROUP_BALANCE_LIMIT = 8.0
GROUP_BALANCE_STEP = 1.0
MIN_ANGEL_PROBABILITY = 0.2
MAX_ANGEL_PROBABILITY = 0.8

_WORKER_BUSY_STATES: dict[str, "WorkerBusyState"] = {}
_MESSAGE_CLAIMS: dict[str, "MessageClaim"] = {}
_GROUP_BALANCE: dict[str, float] = {}
_PENDING_COMMENTS: dict[tuple[str, str, str], "DelegatedComment"] = {}


@dataclass(frozen=True, slots=True)
class WorkerScheduleDecision:
    should_handle: bool
    worker_id: str = ""
    reason: str = ""
    delegated_from: str = ""
    claim_key: str = ""
    both_targeted: bool = False
    group_key: str = ""
    balance_before: float = 0.0
    angel_probability: float = 0.5


@dataclass(frozen=True, slots=True)
class WorkerBusyState:
    active_requests: int
    expires_at: float


@dataclass(frozen=True, slots=True)
class MessageClaim:
    worker_id: str
    expires_at: float
    delegated_from: str = ""
    state: str = "selected"
    group_key: str = ""
    original_text: str = ""


@dataclass(frozen=True, slots=True)
class DelegatedComment:
    group_key: str
    commenter_id: str
    responder_id: str
    original_text: str
    response_text: str
    expires_at: float


def decide_llm_worker(
    *,
    self_id: object,
    at_ids: object = (),
    reply_sender_id: object = "",
    message_key: str = "",
    group_id: object = "",
    original_text: object = "",
    private_chat: bool = False,
    allow_multi_target: bool = False,
    allow_delegation: bool = False,
    force_targeted: bool = False,
    force_untargeted: bool = False,
    now: float | None = None,
    worker_ids: tuple[str, ...] = TWIN_WORKER_IDS,
    rng: random.Random | None = None,
) -> WorkerScheduleDecision:
    current = time.monotonic() if now is None else now
    cleanup_scheduler_state(now=current)
    self_key = normalize_id(self_id)
    group_key = normalize_group_key(group_id)
    if self_key not in worker_ids:
        return WorkerScheduleDecision(True, self_key, "non_twin_worker", group_key=group_key)
    if private_chat:
        return WorkerScheduleDecision(True, self_key, "private_chat_current_worker", group_key=group_key)

    claim_key = normalize_claim_key(message_key)
    targeted = targeted_twin_ids(at_ids, worker_ids=worker_ids)
    reply_target = normalize_id(reply_sender_id)
    if not targeted and reply_target in worker_ids:
        targeted = {reply_target}
    both_targeted = len(targeted) > 1
    balance_before = read_group_balance(group_key)
    angel_probability = calculate_angel_probability(balance_before)

    if allow_multi_target and both_targeted:
        should = self_key in targeted
        multi_claim_key = f"{claim_key}:worker:{self_key}" if claim_key and should else claim_key
        return WorkerScheduleDecision(
            should,
            self_key if should else "",
            "both_targets_current_worker" if should else "both_targets_not_current_worker",
            claim_key=multi_claim_key,
            both_targeted=True,
            group_key=group_key,
            balance_before=balance_before,
            angel_probability=angel_probability,
        )

    if claim_key:
        existing = _MESSAGE_CLAIMS.get(claim_key)
        if existing is not None and existing.expires_at > current:
            claimed_worker = existing.worker_id
            return WorkerScheduleDecision(
                self_key == claimed_worker,
                claimed_worker,
                "message_claim_owner" if self_key == claimed_worker else "message_claimed_by_other_worker",
                existing.delegated_from if self_key == claimed_worker else "",
                claim_key=claim_key,
                both_targeted=both_targeted,
                group_key=existing.group_key or group_key,
                balance_before=balance_before,
                angel_probability=angel_probability,
            )

    if force_targeted and len(targeted) == 1:
        selected = next(iter(targeted))
    elif force_untargeted and not targeted:
        selected = choose_idle_worker(list(worker_ids), group_key=group_key, rng=rng)
    else:
        selected = select_worker(
            target_ids=targeted,
            now=current,
            group_key=group_key,
            worker_ids=worker_ids,
            allow_delegation=allow_delegation,
            rng=rng,
        )
    if selected is None:
        if targeted and not allow_delegation:
            return WorkerScheduleDecision(
                False,
                sorted(targeted)[0],
                "target_busy_no_delegation",
                claim_key=claim_key,
                both_targeted=both_targeted,
                group_key=group_key,
                balance_before=balance_before,
                angel_probability=angel_probability,
            )
        return WorkerScheduleDecision(False, "", "no_available_worker")

    delegated_from = ""
    reason = "selected_worker"
    if targeted:
        if selected in targeted:
            reason = "target_forced" if force_targeted else "target_available"
        else:
            reason = "target_busy_delegated"
            delegated_from = ",".join(sorted(targeted))
    elif force_untargeted:
        reason = "untargeted_forced"
    if claim_key:
        _MESSAGE_CLAIMS[claim_key] = MessageClaim(
            worker_id=selected,
            expires_at=current + MESSAGE_CLAIM_LEASE_SECONDS,
            delegated_from=delegated_from,
            group_key=group_key,
            original_text=str(original_text or "").strip(),
        )
    return WorkerScheduleDecision(
        self_key == selected,
        selected,
        reason if self_key == selected else "other_worker_selected",
        delegated_from if self_key == selected else "",
        claim_key=claim_key,
        both_targeted=both_targeted,
        group_key=group_key,
        balance_before=balance_before,
        angel_probability=angel_probability,
    )


def select_worker(
    *,
    target_ids: set[str] | None = None,
    now: float | None = None,
    group_key: str = "",
    worker_ids: tuple[str, ...] = TWIN_WORKER_IDS,
    allow_delegation: bool = False,
    rng: random.Random | None = None,
) -> str | None:
    current = time.monotonic() if now is None else now
    targets = {normalize_id(value) for value in (target_ids or set()) if normalize_id(value) in worker_ids}
    idle_workers = [worker_id for worker_id in worker_ids if not is_worker_busy(worker_id, now=current)]
    if targets:
        targeted_idle = [worker_id for worker_id in worker_ids if worker_id in targets and worker_id in idle_workers]
        if targeted_idle:
            if len(targets) > 1:
                return choose_idle_worker(targeted_idle, group_key=group_key, rng=rng)
            return targeted_idle[0]
        if not allow_delegation:
            return None
        delegated = [worker_id for worker_id in idle_workers if worker_id not in targets]
        if delegated:
            return delegated[0]
        return sorted(targets)[0]
    if idle_workers:
        return choose_idle_worker(idle_workers, group_key=group_key, rng=rng)
    return None


def choose_idle_worker(
    worker_ids: list[str],
    *,
    group_key: str = "",
    rng: random.Random | None = None,
) -> str:
    if len(worker_ids) == 1:
        return worker_ids[0]
    if set(worker_ids) >= set(TWIN_WORKER_IDS):
        probability = calculate_angel_probability(read_group_balance(group_key))
        chooser = rng or random.SystemRandom()
        return "1443944862" if chooser.random() < probability else "2629227874"
    chooser = rng or random.SystemRandom()
    return chooser.choice(worker_ids)


def mark_worker_busy(
    worker_id: object,
    *,
    now: float | None = None,
    lease_seconds: float = WORKER_BUSY_LEASE_SECONDS,
) -> None:
    key = normalize_id(worker_id)
    if not key:
        return
    current = time.monotonic() if now is None else now
    previous = _WORKER_BUSY_STATES.get(key)
    active_requests = 1
    if previous is not None and previous.expires_at > current:
        active_requests = previous.active_requests + 1
    _WORKER_BUSY_STATES[key] = WorkerBusyState(
        active_requests=active_requests,
        expires_at=current + max(1.0, lease_seconds),
    )


def release_worker(worker_id: object) -> None:
    key = normalize_id(worker_id)
    state = _WORKER_BUSY_STATES.get(key)
    if state is None or state.active_requests <= 1:
        _WORKER_BUSY_STATES.pop(key, None)
        return
    _WORKER_BUSY_STATES[key] = WorkerBusyState(
        active_requests=state.active_requests - 1,
        expires_at=state.expires_at,
    )


def mark_claim_processing(claim_key: object, worker_id: object, *, now: float | None = None) -> None:
    key = normalize_claim_key(claim_key)
    if not key:
        return
    claim = _MESSAGE_CLAIMS.get(key)
    if claim is None or claim.worker_id != normalize_id(worker_id):
        return
    current = time.monotonic() if now is None else now
    _MESSAGE_CLAIMS[key] = MessageClaim(
        worker_id=claim.worker_id,
        expires_at=max(claim.expires_at, current + MESSAGE_CLAIM_LEASE_SECONDS),
        delegated_from=claim.delegated_from,
        state="processing_started",
        group_key=claim.group_key,
        original_text=claim.original_text,
    )


def complete_claim_response(
    claim_key: object,
    worker_id: object,
    response_text: object,
    *,
    now: float | None = None,
) -> DelegatedComment | None:
    key = normalize_claim_key(claim_key)
    if not key:
        return None
    claim = _MESSAGE_CLAIMS.get(key)
    if claim is None or claim.worker_id != normalize_id(worker_id):
        return None
    record_worker_handled(claim.group_key, claim.worker_id)
    if not claim.delegated_from:
        return None
    current = time.monotonic() if now is None else now
    comment = DelegatedComment(
        group_key=claim.group_key,
        commenter_id=claim.delegated_from.split(",", 1)[0],
        responder_id=claim.worker_id,
        original_text=claim.original_text,
        response_text=str(response_text or "").strip(),
        expires_at=current + MESSAGE_CLAIM_LEASE_SECONDS,
    )
    _PENDING_COMMENTS[(comment.group_key, comment.commenter_id, comment.responder_id)] = comment
    _MESSAGE_CLAIMS[key] = MessageClaim(
        worker_id=claim.worker_id,
        expires_at=max(claim.expires_at, current + MESSAGE_CLAIM_LEASE_SECONDS),
        delegated_from=claim.delegated_from,
        state="response_completed",
        group_key=claim.group_key,
        original_text=claim.original_text,
    )
    return comment


def pop_pending_delegated_comment(
    *,
    group_id: object,
    commenter_id: object,
    responder_id: object,
    now: float | None = None,
) -> DelegatedComment | None:
    current = time.monotonic() if now is None else now
    cleanup_scheduler_state(now=current)
    key = (normalize_group_key(group_id), normalize_id(commenter_id), normalize_id(responder_id))
    comment = _PENDING_COMMENTS.get(key)
    if comment is None or comment.expires_at <= current:
        _PENDING_COMMENTS.pop(key, None)
        return None
    return _PENDING_COMMENTS.pop(key)


def is_worker_busy(worker_id: object, *, now: float | None = None) -> bool:
    current = time.monotonic() if now is None else now
    state = _WORKER_BUSY_STATES.get(normalize_id(worker_id))
    return bool(state and state.active_requests > 0 and state.expires_at > current)


def cleanup_scheduler_state(*, now: float | None = None) -> None:
    current = time.monotonic() if now is None else now
    for worker_id, state in list(_WORKER_BUSY_STATES.items()):
        if state.expires_at <= current:
            _WORKER_BUSY_STATES.pop(worker_id, None)
    for claim_key, claim in list(_MESSAGE_CLAIMS.items()):
        if claim.expires_at <= current:
            _MESSAGE_CLAIMS.pop(claim_key, None)
    for key, comment in list(_PENDING_COMMENTS.items()):
        if comment.expires_at <= current:
            _PENDING_COMMENTS.pop(key, None)


def clear_scheduler_state() -> None:
    _WORKER_BUSY_STATES.clear()
    _MESSAGE_CLAIMS.clear()
    _GROUP_BALANCE.clear()
    _PENDING_COMMENTS.clear()


def read_group_balance(group_id: object) -> float:
    return _GROUP_BALANCE.get(normalize_group_key(group_id), 0.0)


def set_group_balance(group_id: object, value: float) -> None:
    _GROUP_BALANCE[normalize_group_key(group_id)] = clamp_balance(value)


def record_worker_handled(group_id: object, worker_id: object, *, step: float = GROUP_BALANCE_STEP) -> float:
    group_key = normalize_group_key(group_id)
    current = read_group_balance(group_key)
    worker = normalize_id(worker_id)
    if worker == "1443944862":
        current -= abs(step)
    elif worker == "2629227874":
        current += abs(step)
    set_group_balance(group_key, current)
    return read_group_balance(group_key)


def calculate_angel_probability(balance: float) -> float:
    raw = 0.5 + (clamp_balance(balance) / (GROUP_BALANCE_LIMIT * 2.0))
    return max(MIN_ANGEL_PROBABILITY, min(MAX_ANGEL_PROBABILITY, raw))


def clamp_balance(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return max(-GROUP_BALANCE_LIMIT, min(GROUP_BALANCE_LIMIT, number))


def targeted_twin_ids(at_ids: object, *, worker_ids: tuple[str, ...] = TWIN_WORKER_IDS) -> set[str]:
    targets: set[str] = set()
    for value in iter_values(at_ids):
        normalized = normalize_id(value)
        if normalized in worker_ids:
            targets.add(normalized)
    return targets


def normalize_id(value: object) -> str:
    return str(value or "").strip()


def normalize_claim_key(value: object) -> str:
    text = normalize_id(value)
    return re.sub(r"\s+", "", text)[:200]


def normalize_group_key(value: object) -> str:
    text = normalize_id(value)
    if not text:
        return ""
    if text.startswith("group:"):
        return text
    return f"group:{text}"


def iter_values(value: object):
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(part for part in value.replace("，", ",").split(",") if part)
    try:
        return tuple(value)  # type: ignore[arg-type]
    except TypeError:
        return (value,)
