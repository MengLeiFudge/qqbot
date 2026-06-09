from __future__ import annotations

import time
from dataclasses import dataclass

from .twin_poke import TWIN_BOT_QQ_IDS


COMMAND_CLAIM_TTL_SECONDS = 600.0
_COMMAND_CLAIMS: dict[str, float] = {}


@dataclass(frozen=True, slots=True)
class CommandRouteDecision:
    should_handle: bool
    reason: str = ""


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
    return decide_migrated_command_route(
        sender_id=sender_id,
        self_id=self_id,
        at_ids=(),
        is_private=False,
        is_direct_or_private=is_direct_or_private,
        feature_mode=feature_mode,
        full_mode=full_mode,
        command_owner_qq=command_owner_qq,
    ).should_handle


def decide_migrated_command_route(
    *,
    sender_id: object,
    self_id: object,
    at_ids: object,
    is_private: bool,
    is_direct_or_private: bool,
    feature_mode: str,
    full_mode: str,
    command_owner_qq: str,
) -> CommandRouteDecision:
    if is_twin_bot_sender_id(sender_id):
        return CommandRouteDecision(False, "sender_is_twin_bot")
    self_key = normalize_id(self_id)
    targeted_twins = targeted_twin_bot_ids(at_ids)
    if targeted_twins:
        if self_key in targeted_twins:
            return CommandRouteDecision(True, "explicit_target")
        return CommandRouteDecision(False, "other_twin_targeted")
    if is_private:
        return CommandRouteDecision(True, "private")
    if is_direct_or_private:
        if self_key == normalize_id(command_owner_qq):
            return CommandRouteDecision(True, "direct_owner")
        return CommandRouteDecision(False, "direct_non_owner_without_explicit_target")
    if feature_mode != full_mode:
        return CommandRouteDecision(False, "not_full_mode")
    if self_key == normalize_id(command_owner_qq):
        return CommandRouteDecision(True, "owner_default")
    return CommandRouteDecision(False, "non_owner_default")


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


def cleanup_expired_claims(*, now: float | None = None) -> None:
    current = time.monotonic() if now is None else now
    expired = [key for key, expires_at in _COMMAND_CLAIMS.items() if expires_at <= current]
    for key in expired:
        _COMMAND_CLAIMS.pop(key, None)


def clear_command_claims() -> None:
    _COMMAND_CLAIMS.clear()
