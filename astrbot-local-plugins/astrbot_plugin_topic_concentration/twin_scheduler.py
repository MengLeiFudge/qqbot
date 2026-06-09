from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass


TWIN_WORKER_IDS = ("1443944862", "2629227874")
WORKER_BUSY_LEASE_SECONDS = 600.0
MESSAGE_CLAIM_LEASE_SECONDS = 60.0

_BUSY_UNTIL: dict[str, float] = {}
_MESSAGE_CLAIMS: dict[str, tuple[str, float]] = {}
_ROUND_ROBIN_INDEX = 0


@dataclass(frozen=True, slots=True)
class WorkerScheduleDecision:
    should_handle: bool
    worker_id: str = ""
    reason: str = ""
    delegated_from: str = ""


def decide_llm_worker(
    *,
    self_id: object,
    at_ids: object = (),
    reply_sender_id: object = "",
    message_key: str = "",
    now: float | None = None,
    worker_ids: tuple[str, ...] = TWIN_WORKER_IDS,
    rng: random.Random | None = None,
) -> WorkerScheduleDecision:
    current = time.monotonic() if now is None else now
    cleanup_scheduler_state(now=current)
    self_key = normalize_id(self_id)
    if self_key not in worker_ids:
        return WorkerScheduleDecision(True, self_key, "non_twin_worker")

    claim_key = normalize_claim_key(message_key)
    if claim_key:
        existing = _MESSAGE_CLAIMS.get(claim_key)
        if existing is not None and existing[1] > current:
            claimed_worker = existing[0]
            return WorkerScheduleDecision(
                self_key == claimed_worker,
                claimed_worker,
                "message_claim_owner" if self_key == claimed_worker else "message_claimed_by_other_worker",
            )

    targeted = targeted_twin_ids(at_ids, worker_ids=worker_ids)
    reply_target = normalize_id(reply_sender_id)
    if not targeted and reply_target in worker_ids:
        targeted = {reply_target}

    selected = select_worker(
        target_ids=targeted,
        now=current,
        worker_ids=worker_ids,
        rng=rng,
    )
    if selected is None:
        return WorkerScheduleDecision(False, "", "no_available_worker")
    if claim_key:
        _MESSAGE_CLAIMS[claim_key] = (selected, current + MESSAGE_CLAIM_LEASE_SECONDS)

    delegated_from = ""
    reason = "selected_worker"
    if targeted:
        if selected in targeted:
            reason = "target_available"
        else:
            reason = "target_busy_delegated"
            delegated_from = ",".join(sorted(targeted))
    return WorkerScheduleDecision(
        self_key == selected,
        selected,
        reason if self_key == selected else "other_worker_selected",
        delegated_from if self_key == selected else "",
    )


def select_worker(
    *,
    target_ids: set[str] | None = None,
    now: float | None = None,
    worker_ids: tuple[str, ...] = TWIN_WORKER_IDS,
    rng: random.Random | None = None,
) -> str | None:
    current = time.monotonic() if now is None else now
    targets = {normalize_id(value) for value in (target_ids or set()) if normalize_id(value) in worker_ids}
    idle_workers = [worker_id for worker_id in worker_ids if not is_worker_busy(worker_id, now=current)]
    if targets:
        for worker_id in worker_ids:
            if worker_id in targets and worker_id in idle_workers:
                return worker_id
        delegated = [worker_id for worker_id in idle_workers if worker_id not in targets]
        if delegated:
            return delegated[0]
        return sorted(targets)[0]
    if idle_workers:
        return choose_idle_worker(idle_workers, rng=rng)
    return None


def choose_idle_worker(worker_ids: list[str], *, rng: random.Random | None = None) -> str:
    global _ROUND_ROBIN_INDEX
    if len(worker_ids) == 1:
        return worker_ids[0]
    if rng is not None:
        return rng.choice(worker_ids)
    worker = worker_ids[_ROUND_ROBIN_INDEX % len(worker_ids)]
    _ROUND_ROBIN_INDEX += 1
    return worker


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
    _BUSY_UNTIL[key] = current + max(1.0, lease_seconds)


def release_worker(worker_id: object) -> None:
    _BUSY_UNTIL.pop(normalize_id(worker_id), None)


def is_worker_busy(worker_id: object, *, now: float | None = None) -> bool:
    current = time.monotonic() if now is None else now
    return _BUSY_UNTIL.get(normalize_id(worker_id), 0.0) > current


def cleanup_scheduler_state(*, now: float | None = None) -> None:
    current = time.monotonic() if now is None else now
    for worker_id, expires_at in list(_BUSY_UNTIL.items()):
        if expires_at <= current:
            _BUSY_UNTIL.pop(worker_id, None)
    for claim_key, (_, expires_at) in list(_MESSAGE_CLAIMS.items()):
        if expires_at <= current:
            _MESSAGE_CLAIMS.pop(claim_key, None)


def clear_scheduler_state() -> None:
    global _ROUND_ROBIN_INDEX
    _BUSY_UNTIL.clear()
    _MESSAGE_CLAIMS.clear()
    _ROUND_ROBIN_INDEX = 0


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


def iter_values(value: object):
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(part for part in value.replace("，", ",").split(",") if part)
    try:
        return tuple(value)  # type: ignore[arg-type]
    except TypeError:
        return (value,)
