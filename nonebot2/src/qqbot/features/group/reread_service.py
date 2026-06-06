from __future__ import annotations

from dataclasses import dataclass
import random
import time

from nonebot.adapters.onebot.v11 import Message

REREAD_COOLDOWN_SECONDS = 120.0


@dataclass(frozen=True, slots=True)
class RereadObservation:
    key: str
    consecutive_count: int
    is_duplicate: bool
    should_repeat: bool


class RereadRepeatState:
    def __init__(
        self,
        *,
        rng: random.Random | None = None,
        clock=time.monotonic,
        cooldown_seconds: float = REREAD_COOLDOWN_SECONDS,
    ) -> None:
        self._groups: dict[str, dict[str, object]] = {}
        self._rng = rng or random.Random()
        self._clock = clock
        self._cooldown_seconds = max(0.0, float(cooldown_seconds))

    def observe(
        self,
        group_id: int | str,
        text: str,
        *,
        message_id: int | str | None = None,
    ) -> RereadObservation:
        normalized = normalize_reread_key(text)
        if not normalized:
            return RereadObservation("", 0, False, False)

        group_key = str(group_id)
        state = self._groups.setdefault(
            group_key,
            {
                "last_key": "",
                "consecutive_count": 0,
                "repeated_current_run": False,
                "cooldown_key": "",
                "cooldown_until": 0.0,
                "last_message_id": "",
                "last_observation": None,
            },
        )
        message_key = str(message_id or "")
        if message_key and state.get("last_message_id") == message_key:
            previous_observation = state.get("last_observation")
            if isinstance(previous_observation, RereadObservation):
                return previous_observation

        previous_key = str(state.get("last_key") or "")
        if previous_key != normalized:
            consecutive_count = 1
            state["last_key"] = normalized
            state["consecutive_count"] = consecutive_count
            state["repeated_current_run"] = False
        else:
            consecutive_count = int(state.get("consecutive_count") or 0) + 1
            state["consecutive_count"] = consecutive_count

        is_duplicate = consecutive_count >= 2
        should_repeat = False
        now = float(self._clock())
        in_cooldown = (
            str(state.get("cooldown_key") or "") == normalized
            and now < float(state.get("cooldown_until") or 0.0)
        )
        if (
            is_duplicate
            and not bool(state.get("repeated_current_run"))
            and not in_cooldown
            and self._rng.random() < reread_probability(consecutive_count)
        ):
            should_repeat = True
            state["repeated_current_run"] = True
            state["cooldown_key"] = normalized
            state["cooldown_until"] = now + self._cooldown_seconds

        observation = RereadObservation(normalized, consecutive_count, is_duplicate, should_repeat)
        state["last_message_id"] = message_key
        state["last_observation"] = observation
        return observation

    def should_repeat(self, group_id: int | str, text: str) -> bool:
        return self.observe(group_id, text).should_repeat


DEFAULT_REREAD_STATE = RereadRepeatState()


def reread_probability(consecutive_count: int) -> float:
    if consecutive_count < 2:
        return 0.0
    return min(0.8, 0.2 + (consecutive_count - 2) * 0.15)


def clamp_reread_percent(percent: float) -> float:
    return min(50, max(percent, 0.01)) / 100


def format_reread_chance(chance: float) -> str:
    return f"{chance:.3%}"


def should_skip_reread_message(message: Message) -> bool:
    return not is_plain_text_message(message)


def is_plain_text_message(message: Message) -> bool:
    return bool(message) and all(segment.type == "text" for segment in message)


def normalize_reread_key(text: str) -> str:
    return " ".join(str(text).split()).strip()


def render_reread_message(message: Message) -> Message:
    if all(segment.type == "text" for segment in message):
        return Message(message.extract_plain_text())
    return message
