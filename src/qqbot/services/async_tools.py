from __future__ import annotations

import asyncio
from typing import Any, Callable


async def run_blocking(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    return await asyncio.to_thread(func, *args, **kwargs)
