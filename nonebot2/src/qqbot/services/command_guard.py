from __future__ import annotations

import re

from nonebot.rule import Rule

from qqbot.services.offline_message_gate import is_before_onebot_connect


COMMAND_PATTERNS = [
    r"^(菜单|帮助|指令)$",
    r"^\s*(查看)?(生图)?积分\s*$",
    r"^菜单(?!\d+$)\S+$",
    r"(?i)^(AI模型|当前AI)$",
    r"(?i)^切换AI\s+\S+$",
    r"(?i)^(arctj\s*[0-9]+(\.[0-9]+)?|(arczm|zm)\s*[1-9][0-9]*|arczm|zm|(arcqh|qh)\s*[1-9][0-9]*|arcqh(\s*(bt|补图))?|qh|arcjx|jx|archd|arctz|xz|arcxz)$",
    r"^开\s*\S$",
    r"^(?:猜\s*)?[1-9][0-9]*\s*.+$",
    r"^[开关](群色图|图片显示)$",
    r"^(来点)?([美色涩蛇]图|混合).*",
    r"(?i)^(i|view|chart|chart1|chart2|path|path1|path2|p|puzzle|puzzle1|puzzle2)\s+.+$",
    r"^(通知)?(大家|全员|群友)?(清理|整理)(群)?文件$|^(群)?文件(清理|整理)(通知)?$",
    r"(?i)^.*(?:factorio|异星|太空时代|space\s*age|spaceage).*(?:下载|安装包).*(?:链接|地址)?$",
]


def is_likely_command(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    return any(re.match(pattern, normalized) for pattern in COMMAND_PATTERNS)


def is_direct_command_event(event) -> bool:
    if is_before_onebot_connect(getattr(event, "time", None)):
        return False

    message_type = getattr(event, "message_type", "")
    if message_type != "group" and not hasattr(event, "group_id"):
        return True

    # 群聊显式指令必须先发给机器人，避免普通聊天命中宽泛正则。
    is_tome = getattr(event, "is_tome", None)
    if callable(is_tome) and bool(is_tome()):
        return True
    if bool(getattr(event, "to_me", False)):
        return True
    return _message_contains_bot_at(event)


def _message_contains_bot_at(event) -> bool:
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
        if segment_type == "at":
            if str(data.get("qq", "")).strip() == self_id:
                return True
    return False


def direct_command_rule() -> Rule:
    return Rule(is_direct_command_event)
