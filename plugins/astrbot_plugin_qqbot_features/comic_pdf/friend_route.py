from __future__ import annotations

import asyncio
from dataclasses import dataclass
import time


@dataclass(frozen=True, slots=True)
class ComicFriendRouteDecision:
    """Selected twin worker and whether it can privately deliver files."""

    selected_worker: str
    has_friend: bool


@dataclass(slots=True)
class _RouteWindow:
    """Short-lived capability rendezvous for one dual-platform event."""

    future: asyncio.Future[ComicFriendRouteDecision]
    participants: dict[str, bool]
    preferred_worker: str
    created_at: float


class ComicFriendRouteCoordinator:
    """Choose one friend-capable twin before command claim acquisition."""

    def __init__(self, *, expected_workers: int = 2, wait_seconds: float = 1.5) -> None:
        self.expected_workers = max(1, int(expected_workers))
        self.wait_seconds = max(0.1, float(wait_seconds))
        self._lock = asyncio.Lock()
        self._windows: dict[str, _RouteWindow] = {}

    async def choose(
        self,
        event_key: str,
        *,
        self_id: str,
        is_friend: bool,
        preferred_worker: str = "",
    ) -> ComicFriendRouteDecision:
        """Rendezvous twin events and return one deterministic capable worker."""
        key = str(event_key or "").strip()
        worker = str(self_id or "").strip()
        if not key or not worker:
            return ComicFriendRouteDecision(worker, bool(is_friend))
        async with self._lock:
            self._cleanup_locked()
            window = self._windows.get(key)
            if window is None:
                window = _RouteWindow(
                    future=asyncio.get_running_loop().create_future(),
                    participants={},
                    preferred_worker=str(preferred_worker or "").strip(),
                    created_at=time.monotonic(),
                )
                self._windows[key] = window
            elif preferred_worker and not window.preferred_worker:
                window.preferred_worker = str(preferred_worker).strip()
            window.participants[worker] = bool(is_friend)
            if len(window.participants) >= self.expected_workers and not window.future.done():
                window.future.set_result(self._decide(window))
            future = window.future
        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout=self.wait_seconds)
        except TimeoutError:
            async with self._lock:
                window = self._windows.get(key)
                if window is not None and not window.future.done():
                    window.future.set_result(self._decide(window))
                if window is not None:
                    return window.future.result()
            return ComicFriendRouteDecision(worker, bool(is_friend))

    def _decide(self, window: _RouteWindow) -> ComicFriendRouteDecision:
        capable = sorted(
            worker for worker, is_friend in window.participants.items() if is_friend
        )
        if capable:
            selected = (
                window.preferred_worker
                if window.preferred_worker in capable
                else capable[0]
            )
            return ComicFriendRouteDecision(selected, True)
        participants = sorted(window.participants)
        selected = (
            window.preferred_worker
            if window.preferred_worker in participants
            else (participants[0] if participants else "")
        )
        return ComicFriendRouteDecision(selected, False)

    def _cleanup_locked(self) -> None:
        cutoff = time.monotonic() - max(10.0, self.wait_seconds * 4)
        expired = [
            key for key, window in self._windows.items() if window.created_at < cutoff
        ]
        for key in expired:
            self._windows.pop(key, None)


async def is_onebot_friend(api, user_id: int) -> bool:
    """Return whether the current OneBot account lists the user as a friend."""
    result = await api.call_api("get_friend_list", no_cache=False)
    records = result
    if isinstance(result, dict):
        records = result.get("data", result.get("friends", []))
    if not isinstance(records, list):
        return False
    target = str(int(user_id))
    return any(
        isinstance(record, dict) and str(record.get("user_id") or "") == target
        for record in records
    )
