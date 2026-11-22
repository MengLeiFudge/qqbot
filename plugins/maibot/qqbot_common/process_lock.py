from __future__ import annotations

import asyncio
from errno import EACCES, EAGAIN, EDEADLK
from pathlib import Path
from time import monotonic, sleep
from typing import BinaryIO

try:
    import fcntl
except ImportError:
    fcntl = None
    import msvcrt


class InterProcessLock:
    def __init__(self, path: Path, *, timeout_seconds: float = 15.0) -> None:
        self.path = Path(path)
        self.timeout_seconds = timeout_seconds
        self._handle: BinaryIO | None = None

    def _open(self) -> BinaryIO:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return self.path.open("a+b")

    @staticmethod
    def _try_lock(handle: BinaryIO) -> bool:
        try:
            if fcntl is None:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if isinstance(exc, BlockingIOError) or (fcntl is None and exc.errno in (EACCES, EAGAIN, EDEADLK)):
                return False
            raise
        return True

    def __enter__(self) -> InterProcessLock:
        deadline = monotonic() + self.timeout_seconds
        self._handle = self._open()
        try:
            while not self._try_lock(self._handle):
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"等待共享状态锁超时: {self.path}")
                sleep(min(0.05, remaining))
            return self
        except BaseException:
            self._close()
            raise

    async def __aenter__(self) -> InterProcessLock:
        deadline = monotonic() + self.timeout_seconds
        self._handle = self._open()
        try:
            while not self._try_lock(self._handle):
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"等待共享状态锁超时: {self.path}")
                await asyncio.sleep(min(0.05, remaining))
            return self
        except BaseException:
            self._close()
            raise

    def _close(self) -> None:
        if self._handle is not None:
            handle, self._handle = self._handle, None
            handle.close()

    def __exit__(self, *_exc) -> None:
        self._close()

    async def __aexit__(self, *_exc) -> None:
        self._close()
