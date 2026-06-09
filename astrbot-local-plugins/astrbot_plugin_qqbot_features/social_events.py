from __future__ import annotations

from .twin_poke import TWIN_BOT_QQ_IDS


def format_self_join_private_notice(group_name: str | None, group_id: str | int) -> str:
    normalized_name = str(group_name or "").strip() or "未知群聊"
    normalized_group_id = str(group_id or "").strip() or "未知群号"
    return f"棉花糖已经加入群聊{normalized_name}（{normalized_group_id}）了喵！"


def should_send_member_welcome(
    *,
    user_id: str,
    self_id: str,
    command_owner_id: str,
    twin_bot_ids: frozenset[str] = TWIN_BOT_QQ_IDS,
) -> bool:
    if not user_id or user_id == self_id:
        return False
    if user_id in twin_bot_ids:
        return False
    return self_id == command_owner_id
