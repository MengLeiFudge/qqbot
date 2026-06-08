from __future__ import annotations

from qqbot.features.ai.identity_anchor import (
    build_ai_identity_context_text,
    build_current_sender_context_text,
    filter_current_sender_memory_aliases,
)


def test_current_sender_context_keeps_numeric_nickname_as_display_only() -> None:
    context = build_current_sender_context_text("605738729", "123456")

    assert "显示名=605738729" in context
    assert "真实QQ=123456" in context
    assert "不能当作QQ号或权限身份锚点" in context


def test_identity_context_does_not_promote_numeric_nickname_to_owner() -> None:
    context = build_ai_identity_context_text(
        author_label="萌泪酱(605738729)",
        current_user_id="123456",
        current_identity="普通用户",
    )

    assert "Bot 作者：萌泪酱(605738729)" in context
    assert "当前发言者真实QQ：123456" in context
    assert "当前发言者身份：普通用户" in context
    assert "当前发言者身份：Bot 作者" not in context
    assert "显示名、建议称呼和历史 sender_name" in context


def test_sender_memory_aliases_drop_numeric_and_owner_alias_for_non_owner() -> None:
    aliases = filter_current_sender_memory_aliases(
        ["605738729", "萌泪酱", "普通群友", "123456", "普通群友"],
        user_id="123456",
        forbidden_aliases=("萌泪酱", "605738729"),
    )

    assert aliases == ("普通群友",)
