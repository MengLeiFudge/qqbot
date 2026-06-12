from __future__ import annotations

import time
from dataclasses import dataclass

from .twin_poke import TWIN_BOT_QQ_IDS
try:
    from astrbot_plugin_topic_concentration.twin_scheduler import decide_llm_worker
    from astrbot_plugin_topic_concentration.twin_scheduler import record_worker_handled
except ModuleNotFoundError:  # AstrBot runtime imports plugins as data.plugins.<name>.
    from data.plugins.astrbot_plugin_topic_concentration.twin_scheduler import decide_llm_worker
    from data.plugins.astrbot_plugin_topic_concentration.twin_scheduler import record_worker_handled


COMMAND_CLAIM_TTL_SECONDS = 600.0
_COMMAND_CLAIMS: dict[str, float] = {}


@dataclass(frozen=True, slots=True)
class CommandRouteDecision:
    should_handle: bool
    reason: str = ""
    selected_worker: str = ""
    claim_key: str = ""


def is_twin_bot_sender_id(sender_id: object) -> bool:
    return str(sender_id or "") in TWIN_BOT_QQ_IDS


def should_handle_migrated_command_ids(
    *,
    sender_id: object,
    self_id: object,
    is_direct_or_private: bool,
    feature_mode: str,
    full_mode: str,
    command_owner_qq: str,
) -> bool:
    if is_twin_bot_sender_id(sender_id):
        return False
    if feature_mode != full_mode and not is_direct_or_private:
        return False
    return normalize_id(self_id) == normalize_id(command_owner_qq)


def decide_migrated_command_route(
    *,
    sender_id: object,
    self_id: object,
    at_ids: object,
    group_id: object = "",
    message_key: str = "",
    text: object = "",
    is_private: bool,
    is_direct_or_private: bool,
    feature_mode: str,
    full_mode: str,
    command_owner_qq: str,
    rng=None,
) -> CommandRouteDecision:
    if is_twin_bot_sender_id(sender_id):
        return CommandRouteDecision(False, "sender_is_twin_bot")
    self_key = normalize_id(self_id)
    targeted_twins = targeted_twin_bot_ids(at_ids)
    if targeted_twins:
        route = decide_llm_worker(
            self_id=self_id,
            at_ids=targeted_twins,
            message_key=message_key,
            group_id=group_id,
            original_text=text,
            rng=rng,
        )
        if route.worker_id and self_key == route.worker_id:
            return CommandRouteDecision(True, "explicit_target" if len(targeted_twins) == 1 else "multi_target_selected", route.worker_id, route.claim_key)
        if route.worker_id:
            return CommandRouteDecision(False, "other_twin_targeted" if len(targeted_twins) == 1 else "multi_target_other_selected", route.worker_id, route.claim_key)
        if self_key in targeted_twins:
            return CommandRouteDecision(True, "explicit_target")
        return CommandRouteDecision(False, "other_twin_targeted")
    if is_private:
        return CommandRouteDecision(True, "private")
    if is_direct_or_private:
        route = decide_llm_worker(
            self_id=self_id,
            message_key=message_key,
            group_id=group_id,
            original_text=text,
            rng=rng,
        )
        if route.worker_id and self_key == route.worker_id:
            return CommandRouteDecision(True, "direct_weighted_selected", route.worker_id, route.claim_key)
        return CommandRouteDecision(False, "direct_weighted_other_selected", route.worker_id, route.claim_key)
    if feature_mode != full_mode:
        return CommandRouteDecision(False, "not_full_mode")
    route = decide_llm_worker(
        self_id=self_id,
        message_key=message_key,
        group_id=group_id,
        original_text=text,
        rng=rng,
    )
    if route.worker_id and self_key == route.worker_id:
        return CommandRouteDecision(True, "weighted_default", route.worker_id, route.claim_key)
    return CommandRouteDecision(False, "weighted_other_default", route.worker_id, route.claim_key)


def targeted_twin_bot_ids(at_ids: object) -> set[str]:
    targets: set[str] = set()
    if isinstance(at_ids, str):
        values = at_ids.replace("，", ",").split(",")
    else:
        try:
            values = list(at_ids or [])
        except TypeError:
            values = [at_ids]
    for value in values:
        normalized = normalize_id(value)
        if normalized in TWIN_BOT_QQ_IDS:
            targets.add(normalized)
    return targets


def normalize_id(value: object) -> str:
    return str(value or "").strip()


def try_claim_command(
    claim_key: str,
    *,
    now: float | None = None,
    ttl_seconds: float = COMMAND_CLAIM_TTL_SECONDS,
) -> bool:
    key = str(claim_key or "").strip()
    if not key:
        return True
    current = time.monotonic() if now is None else now
    cleanup_expired_claims(now=current)
    expires_at = _COMMAND_CLAIMS.get(key, 0.0)
    if expires_at > current:
        return False
    _COMMAND_CLAIMS[key] = current + max(1.0, ttl_seconds)
    return True


def record_command_handled(group_id: object, worker_id: object) -> float:
    return record_worker_handled(group_id, worker_id)


def cleanup_expired_claims(*, now: float | None = None) -> None:
    current = time.monotonic() if now is None else now
    expired = [key for key, expires_at in _COMMAND_CLAIMS.items() if expires_at <= current]
    for key in expired:
        _COMMAND_CLAIMS.pop(key, None)


def clear_command_claims() -> None:
    _COMMAND_CLAIMS.clear()
