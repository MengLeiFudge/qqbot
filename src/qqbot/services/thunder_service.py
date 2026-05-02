from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True, slots=True)
class ThunderCommand:
    action: str
    probability: float | None = None
    min_seconds: int | None = None
    max_seconds: int | None = None


def clamp_thunder_percent(percent: float) -> float:
    return min(50, max(percent, 0.01)) / 100


def normalize_thunder_range(min_seconds: int, max_seconds: int) -> tuple[int, int]:
    left = min(30, max(min_seconds, 1))
    right = min(30, max(max_seconds, 1))
    return (left, right) if left <= right else (right, left)


def parse_thunder_command(text: str) -> ThunderCommand | None:
    if match := re.match(r"^设置(随机)?禁言概率 *([0-9]+(\.[0-9]+)?)%?$", text):
        return ThunderCommand(
            action="set_probability",
            probability=clamp_thunder_percent(float(match.group(2))),
        )
    if match := re.match(r"^设置(随机)?禁言时间 *([0-9]+) +([0-9]+)$", text):
        min_seconds, max_seconds = normalize_thunder_range(
            int(match.group(2)),
            int(match.group(3)),
        )
        return ThunderCommand(
            action="set_range",
            min_seconds=min_seconds,
            max_seconds=max_seconds,
        )
    return None
