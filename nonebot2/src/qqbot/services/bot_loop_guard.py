from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable
import re
import time


GuardDecision = str


class BotLoopGuard:
    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.time,
        blacklist_seconds: float = 600.0,
    ) -> None:
        self.clock = clock
        self.blacklist_seconds = blacklist_seconds
        self._recent: dict[tuple[str, str], deque[tuple[float, str]]] = defaultdict(deque)
        self._blacklist_until: dict[tuple[str, str], float] = {}

    def record_trigger(
        self,
        group_id: int | str,
        user_id: int | str,
        prompt: str,
    ) -> GuardDecision:
        key = (str(group_id), str(user_id))
        now = self.clock()
        if self._blacklist_until.get(key, 0.0) > now:
            return "blocked"
        if key in self._blacklist_until:
            self._blacklist_until.pop(key, None)

        normalized = normalize_prompt(prompt)
        recent = self._recent[key]
        recent.append((now, normalized))
        while recent and now - recent[0][0] > 60:
            recent.popleft()

        if self._is_suspicious(recent, now, normalized):
            self._blacklist_until[key] = now + self.blacklist_seconds
            return "warn"
        return "allow"

    def _is_suspicious(
        self,
        recent: deque[tuple[float, str]],
        now: float,
        normalized: str,
    ) -> bool:
        recent_20s = [text for ts, text in recent if now - ts <= 20]
        if len(recent_20s) >= 5:
            return True
        if normalized and sum(1 for _ts, text in recent if text == normalized) >= 3:
            return True
        fixed_count = sum(1 for _ts, text in recent if is_fixed_format_reply(text))
        return fixed_count >= 4


def normalize_prompt(prompt: str) -> str:
    return re.sub(r"\s+", "", prompt).strip().lower()


def is_fixed_format_reply(text: str) -> bool:
    normalized = normalize_prompt(text)
    if normalized in {"收到", "好的", "好", "ok", "okay", "在的", "你好", "您好"}:
        return True
    return normalized in {"有什么事", "找我什么事", "找我什么事情", "请问有什么事"}
