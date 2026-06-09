from __future__ import annotations

from qqbot.plugins.ai import build_ai_prompt
from qqbot.plugins.ai import build_local_quick_ai_reply
from qqbot.services.message_normalizer import NormalizedMessage


def test_build_ai_prompt_keeps_at_segments_when_text_exists() -> None:
    prompt = build_ai_prompt(
        NormalizedMessage(
            text="返回字符“”",
            outline="返回字符“” [@2629227874]",
            at_user_ids=("2629227874",),
        )
    )

    assert prompt == "返回字符“”\n本消息包含 QQ @: 2629227874"


def test_build_ai_prompt_keeps_pure_direct_at_quick_prompt() -> None:
    prompt = build_ai_prompt(
        NormalizedMessage(
            text="",
            outline="[@1443944862]",
            at_user_ids=("1443944862",),
        )
    )

    assert prompt == "找我什么事情？"


def test_local_quick_reply_does_not_intercept_regular_chat_text() -> None:
    assert build_local_quick_ai_reply(NormalizedMessage(text="在吗", outline="在吗"), "在吗") == ""
    assert build_local_quick_ai_reply(NormalizedMessage(text="棉花糖", outline="棉花糖"), "棉花糖") == ""
