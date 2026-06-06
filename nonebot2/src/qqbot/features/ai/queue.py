from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from qqbot.config import RuntimeSettings
from qqbot.features.ai.command import AiChatTriggerKind
from qqbot.features.ai.message_decision import AiMessageDecision
from qqbot.services.message_normalizer import NormalizedMessage
from qqbot.services.settings_store import SettingsStore

AI_QUEUE_ESTIMATED_SECONDS_PER_REQUEST = 20.0
AI_PROACTIVE_BUFFER_QUIET_SECONDS = 10.0
AI_PROACTIVE_BUFFER_MAX_SECONDS = 30.0


@dataclass(frozen=True)
class AiReplyQueueTicket:
    scope: str
    lock: asyncio.Lock
    queue_position: int
    estimated_wait_seconds: float


@dataclass(frozen=True)
class AiQueuedRequest:
    bot: Any
    event: Any
    settings: RuntimeSettings
    store: SettingsStore
    normalized_message: NormalizedMessage
    prompt: str
    request_started: float
    request_wall_started: float
    event_time: object
    message_id: object
    group_id: object | None
    user_id: str
    trigger_kind: AiChatTriggerKind
    decision: AiMessageDecision
    quote_first_reply: bool = True


@dataclass(frozen=True)
class AiQueuedBatch:
    scope: str
    items: tuple[AiQueuedRequest, ...]

    @property
    def first(self) -> AiQueuedRequest:
        return self.items[0]


@dataclass(frozen=True)
class AiProactiveBufferItem:
    bot: Any
    event: Any
    settings: RuntimeSettings
    store: SettingsStore
    normalized_message: NormalizedMessage
    prompt: str
    request_started: float
    request_wall_started: float
    event_time: object
    message_id: object
    group_id: object
    user_id: str


class AiProactiveBufferManager:
    def __init__(
        self,
        *,
        quiet_seconds: float = AI_PROACTIVE_BUFFER_QUIET_SECONDS,
        max_seconds: float = AI_PROACTIVE_BUFFER_MAX_SECONDS,
        batch_builder: Callable[[AiProactiveBufferItem], AiQueuedRequest] | None = None,
        silence_checker: Callable[[tuple[AiProactiveBufferItem, ...]], bool] | None = None,
        silence_logger: Callable[[str, tuple[AiProactiveBufferItem, ...]], None] | None = None,
        batch_processor: Callable[[AiQueuedBatch, float], Awaitable[None]] | None = None,
    ) -> None:
        self.quiet_seconds = max(0.0, float(quiet_seconds))
        self.max_seconds = max(self.quiet_seconds, float(max_seconds))
        self.batch_builder = batch_builder
        self.silence_checker = silence_checker
        self.silence_logger = silence_logger
        self.batch_processor = batch_processor
        self._buffers: dict[str, list[AiProactiveBufferItem]] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def add(self, scope: str, item: AiProactiveBufferItem) -> None:
        self._buffers.setdefault(scope, []).append(item)
        task = self._tasks.get(scope)
        if task is None or task.done():
            self._tasks[scope] = asyncio.create_task(self._flush_after(scope, self.quiet_seconds))
            return
        first = self._buffers[scope][0]
        age = time.perf_counter() - first.request_started
        if age >= self.max_seconds:
            task.cancel()
            self._tasks[scope] = asyncio.create_task(self.flush(scope))

    def pop(self, scope: str) -> AiQueuedBatch | None:
        items = self._buffers.pop(scope, [])
        self._tasks.pop(scope, None)
        if not items:
            return None
        item_tuple = tuple(items)
        if self.silence_checker is not None and self.silence_checker(item_tuple):
            if self.silence_logger is not None:
                self.silence_logger(scope, item_tuple)
            return None
        if self.batch_builder is None:
            raise RuntimeError("AiProactiveBufferManager.batch_builder is not configured")
        requests = tuple(self.batch_builder(item) for item in item_tuple)
        return AiQueuedBatch(scope=scope, items=requests)

    def discard(self, scope: str) -> int:
        items = self._buffers.pop(scope, [])
        task = self._tasks.pop(scope, None)
        if task is not None and not task.done():
            task.cancel()
        return len(items)

    async def flush(self, scope: str) -> None:
        if self.batch_processor is None:
            raise RuntimeError("AiProactiveBufferManager.batch_processor is not configured")
        lock = self._locks.setdefault(scope, asyncio.Lock())
        async with lock:
            batch = self.pop(scope)
            if batch is None:
                return
            await self.batch_processor(batch, batch.first.request_started)

    async def _flush_after(self, scope: str, delay_seconds: float) -> None:
        try:
            await asyncio.sleep(delay_seconds)
            await self.flush(scope)
        except asyncio.CancelledError:
            raise
        finally:
            if self._tasks.get(scope) is asyncio.current_task():
                self._tasks.pop(scope, None)


class AiReplyQueueManager:
    def __init__(
        self,
        *,
        estimated_seconds_per_request: float = AI_QUEUE_ESTIMATED_SECONDS_PER_REQUEST,
    ) -> None:
        self.estimated_seconds_per_request = estimated_seconds_per_request
        self._locks: dict[str, asyncio.Lock] = {}
        self._queued_counts: dict[str, int] = {}
        self._pending_batches: dict[str, list[AiQueuedRequest]] = {}

    def join(self, scope: str) -> AiReplyQueueTicket:
        queued_ahead = self._queued_counts.get(scope, 0)
        self._queued_counts[scope] = queued_ahead + 1
        estimated_wait = queued_ahead * self.estimated_seconds_per_request
        return AiReplyQueueTicket(
            scope=scope,
            lock=self._locks.setdefault(scope, asyncio.Lock()),
            queue_position=queued_ahead,
            estimated_wait_seconds=estimated_wait,
        )

    def leave(self, ticket: AiReplyQueueTicket) -> None:
        remaining = self._queued_counts.get(ticket.scope, 0) - 1
        if remaining > 0:
            self._queued_counts[ticket.scope] = remaining
            return
        self._queued_counts.pop(ticket.scope, None)
        if not ticket.lock.locked():
            self._locks.pop(ticket.scope, None)

    def enqueue_pending(self, scope: str, request: AiQueuedRequest) -> None:
        self._pending_batches.setdefault(scope, []).append(request)

    def pop_pending_batch(self, scope: str) -> AiQueuedBatch | None:
        pending = self._pending_batches.pop(scope, [])
        if not pending:
            return None
        return AiQueuedBatch(scope=scope, items=tuple(pending))

    def has_pending(self, scope: str) -> bool:
        return bool(self._pending_batches.get(scope))
