from __future__ import annotations

import time


_ONEBOT_CONNECTED_AT: float | None = None


def mark_onebot_connected(now: float | int | None = None) -> float:
    """记录 OneBot 连接时间水位，用于区分离线补推消息。"""
    global _ONEBOT_CONNECTED_AT
    timestamp = time.time() if now is None else float(now)
    _ONEBOT_CONNECTED_AT = timestamp
    return _ONEBOT_CONNECTED_AT


def clear_onebot_connect_watermark() -> None:
    global _ONEBOT_CONNECTED_AT
    _ONEBOT_CONNECTED_AT = None


def get_onebot_connect_watermark() -> float | None:
    return _ONEBOT_CONNECTED_AT


def is_before_onebot_connect(event_time: object) -> bool:
    if _ONEBOT_CONNECTED_AT is None:
        return False
    try:
        timestamp = float(event_time)
    except (TypeError, ValueError):
        return False
    return timestamp < _ONEBOT_CONNECTED_AT


def is_within_onebot_connect_grace(
    event_time: object,
    *,
    grace_seconds: float = 5.0,
) -> bool:
    if _ONEBOT_CONNECTED_AT is None:
        return False
    try:
        timestamp = float(event_time)
    except (TypeError, ValueError):
        return False
    return _ONEBOT_CONNECTED_AT <= timestamp < _ONEBOT_CONNECTED_AT + grace_seconds
