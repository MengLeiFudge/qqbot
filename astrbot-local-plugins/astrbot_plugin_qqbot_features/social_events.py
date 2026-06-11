from __future__ import annotations

from .twin_poke import TWIN_BOT_QQ_IDS


ANGEL_BOT_QQ = "1443944862"
DEMON_BOT_QQ = "2629227874"
GROUP_MEMBER_WELCOME_SUFFIXES = ("--", "-1", "=群地位-1", "+=-1")


def format_self_join_private_notice(group_name: str | None, group_id: str | int) -> str:
    normalized_name = str(group_name or "").strip() or "未知群聊"
    normalized_group_id = str(group_id or "").strip() or "未知群号"
    return f"棉花糖已经加入群聊{normalized_name}（{normalized_group_id}）了喵！"


def should_send_member_welcome(
    *,
    user_id: str,
    self_id: str,
    twin_bot_ids: frozenset[str] = TWIN_BOT_QQ_IDS,
) -> bool:
    if not user_id or user_id == self_id:
        return False
    if user_id in twin_bot_ids:
        return False
    return self_id in twin_bot_ids


def format_group_member_welcome(self_id: str, suffix: str) -> str:
    normalized_self_id = str(self_id or "").strip()
    normalized_suffix = str(suffix or "").strip() or GROUP_MEMBER_WELCOME_SUFFIXES[0]
    if normalized_self_id == DEMON_BOT_QQ:
        return f" 来了个大佬，群地位{normalized_suffix}"
    if normalized_self_id == ANGEL_BOT_QQ:
        return f" 欢迎大佬喵！群地位{normalized_suffix}"
    return f" 欢迎大佬，群地位{normalized_suffix}"
