from __future__ import annotations

import asyncio
import threading
import time

import nonebot
import pytest

nonebot.init()

from qqbot.plugins.lifecycle import run_memory_maintenance_loop, run_shapez_file_cleanup_loop


class BlockingMemoryMaintenanceService:
    def __init__(self, started: asyncio.Event, release: threading.Event) -> None:
        self.started = started
        self.release = release
        self.store = self

    def list_group_ids(self) -> list[int]:
        return [10001]

    def summarize_group_topics(self, group_id: int, *, limit: int) -> None:
        self.started_loop.call_soon_threadsafe(self.started.set)
        while not self.release.is_set():
            time.sleep(0.01)

    def index_recent_messages(self, group_id: int, *, limit: int) -> None:
        return None


def test_memory_maintenance_loop_does_not_block_event_loop(monkeypatch) -> None:
    async def run() -> None:
        started = asyncio.Event()
        release = threading.Event()
        service = BlockingMemoryMaintenanceService(started, release)
        service.started_loop = asyncio.get_running_loop()
        monkeypatch.setattr(
            "qqbot.plugins.lifecycle.build_openai_embedding_client",
            lambda: None,
        )
        monkeypatch.setattr(
            "qqbot.plugins.lifecycle.MemoryVectorStore",
            lambda path: None,
        )
        monkeypatch.setattr(
            "qqbot.plugins.lifecycle.ChatMemoryStore",
            lambda data_root: service,
        )
        monkeypatch.setattr(
            "qqbot.plugins.lifecycle.MemoryMaintenanceService",
            lambda *args, **kwargs: service,
        )
        monkeypatch.setattr(
            "qqbot.plugins.lifecycle.seed_domain_knowledge_once",
            lambda: None,
        )

        task = asyncio.create_task(run_memory_maintenance_loop())
        await asyncio.wait_for(started.wait(), timeout=1)

        # 如果维护批处理仍在事件循环线程里同步执行，这个 sleep 无法及时恢复。
        await asyncio.wait_for(asyncio.sleep(0), timeout=1)

        release.set()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())


def test_shapez_file_cleanup_loop_runs_daily_scan(monkeypatch) -> None:
    class FakeShapezCleanupService:
        def __init__(self) -> None:
            self.calls = 0

        async def run_daily_scan(self, bot):
            self.calls += 1
            started.set()
            return {"ran": True}

    async def run() -> None:
        service = FakeShapezCleanupService()
        monkeypatch.setattr(
            "qqbot.plugins.lifecycle.ShapezGroupFileCleanupService",
            lambda *args, **kwargs: service,
        )
        monkeypatch.setattr(
            "qqbot.plugins.lifecycle.ShapezGroupFileCleanupStore",
            lambda path: object(),
        )

        async def fake_sleep(_seconds):
            await release.wait()

        monkeypatch.setattr("qqbot.plugins.lifecycle.asyncio.sleep", fake_sleep)

        task = asyncio.create_task(run_shapez_file_cleanup_loop(object()))
        await asyncio.wait_for(started.wait(), timeout=1)

        assert service.calls == 1

        release.set()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    started = asyncio.Event()
    release = asyncio.Event()
    asyncio.run(run())
