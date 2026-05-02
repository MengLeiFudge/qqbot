from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True, slots=True)
class GroupControlCommand:
    action: str
    target_id: int | None = None
    duration_seconds: int | None = None


def parse_group_control_command(
    text: str,
    at_targets: list[int],
) -> GroupControlCommand | None:
    normalized = text.strip()
    if match := re.match(r"(?i)^((禁|禁言)?([1-9][0-9]*)([smh]?))", normalized):
        value = int(match.group(3))
        unit = match.group(4).lower()
        multiplier = {"": 1, "s": 1, "m": 60, "h": 3600}[unit]
        if at_targets:
            return GroupControlCommand(
                action="ban_member",
                target_id=at_targets[0],
                duration_seconds=value * multiplier,
            )
    if normalized.startswith("解") and at_targets:
        return GroupControlCommand(
            action="unban_member",
            target_id=at_targets[0],
        )
    if re.match(r"^(群禁|群禁言)$", normalized):
        return GroupControlCommand(action="ban_group")
    if re.match(r"^(解禁|群解禁)$", normalized):
        return GroupControlCommand(action="unban_group")
    if re.match(r"^(踢|踢出)", normalized) and at_targets:
        return GroupControlCommand(
            action="kick_member",
            target_id=at_targets[0],
        )
    return None
