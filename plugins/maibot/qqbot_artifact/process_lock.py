from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from qqbot_common.process_lock import InterProcessLock


@asynccontextmanager
async def interprocess_lock(path: Path, *, timeout_seconds: float) -> AsyncIterator[None]:
    async with InterProcessLock(path, timeout_seconds=timeout_seconds):
        yield
