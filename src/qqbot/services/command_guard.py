from __future__ import annotations

import re

from nonebot.rule import Rule


COMMAND_PATTERNS = [
    r"^(菜单|帮助|指令)$",
    r"^菜单(?!\d+$)\S+$",
    r"(?i)^(AI模型|当前AI)$",
    r"(?i)^切换AI\s+\S+$",
    r"^设置复读(概率)? *[0-9]+(\.[0-9]+)?%?$",
    r"^设置(随机)?禁言(概率|时间).*$",
    r"(?i)^(/?donate|捐献|支持)$",
    r"(?i)^(arctj\s*[0-9]+(\.[0-9]+)?|(arczm|zm)\s*[1-9][0-9]*|arczm|zm|(arcqh|qh)\s*[1-9][0-9]*|arcqh(\s*(bt|补图))?|qh|arcjx|jx|archd|arctz|xz|arcxz)$",
    r"^开\s*\S$",
    r"^(?:猜\s*)?[1-9][0-9]*\s*.+$",
    r"^[开关](群色图|图片显示)$",
    r"^(来点)?([美色涩蛇]图|混合).*",
    r"(?i)^((禁|禁言)?[1-9][0-9]*[smh]?|解|解禁|群禁|群禁言|群解禁|踢|踢出)(\s|$)",
]


def is_likely_command(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    return any(re.match(pattern, normalized) for pattern in COMMAND_PATTERNS)


def is_direct_command_event(event) -> bool:
    message_type = getattr(event, "message_type", "")
    if message_type != "group" and not hasattr(event, "group_id"):
        return True

    # 群聊显式指令必须先发给机器人，避免普通聊天命中宽泛正则。
    is_tome = getattr(event, "is_tome", None)
    if callable(is_tome) and bool(is_tome()):
        return True
    if bool(getattr(event, "to_me", False)):
        return True
    return _message_starts_with_bot_at(event)


def _message_starts_with_bot_at(event) -> bool:
    self_id = str(getattr(event, "self_id", "") or "").strip()
    if not self_id:
        return False

    get_message = getattr(event, "get_message", None)
    message = get_message() if callable(get_message) else getattr(event, "message", None)
    if message is None:
        message = getattr(event, "original_message", None)
    if message is None:
        return False

    for segment in message:
        segment_type = getattr(segment, "type", "")
        data = getattr(segment, "data", {}) or {}
        if segment_type == "text":
            if str(data.get("text", "")).strip():
                return False
            continue
        if segment_type == "at":
            return str(data.get("qq", "")).strip() == self_id
        return False
    return False


def direct_command_rule() -> Rule:
    return Rule(is_direct_command_event)
