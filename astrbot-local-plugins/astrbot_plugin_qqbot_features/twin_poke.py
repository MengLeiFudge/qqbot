from __future__ import annotations


TWIN_BOT_QQ_IDS = frozenset({"1443944862", "2629227874"})


def should_follow_poke_notice(*, self_id: str, user_id: str, target_id: str) -> bool:
    if not self_id or not user_id or not target_id:
        return False
    if user_id == self_id:
        return False
    if user_id in TWIN_BOT_QQ_IDS:
        return False
    if target_id == self_id:
        return True
    return target_id not in TWIN_BOT_QQ_IDS
