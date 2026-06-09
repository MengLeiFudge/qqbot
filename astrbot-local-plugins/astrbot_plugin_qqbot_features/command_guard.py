from __future__ import annotations

from .twin_poke import TWIN_BOT_QQ_IDS


def is_twin_bot_sender_id(sender_id: object) -> bool:
    return str(sender_id or "") in TWIN_BOT_QQ_IDS


def should_handle_migrated_command_ids(
    *,
    sender_id: object,
    self_id: object,
    is_direct_or_private: bool,
    feature_mode: str,
    full_mode: str,
    command_owner_qq: str,
) -> bool:
    if is_twin_bot_sender_id(sender_id):
        return False
    if is_direct_or_private:
        return True
    if feature_mode != full_mode:
        return False
    return str(self_id or "") == str(command_owner_qq or "")
