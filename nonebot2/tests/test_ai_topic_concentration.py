from __future__ import annotations

from qqbot.features.ai.topic_concentration import (
    ProactiveTopicInterest,
    TopicConcentrationMessage,
    build_ai_proactive_reply_decision_prompt,
    build_topic_concentration_prompt,
    looks_like_topic_concentration_candidate,
    parse_ai_proactive_reply_decision,
)
from qqbot.features.ai.command import looks_like_ai_named_trigger


def test_short_casual_chat_can_be_candidate_for_ai_decision() -> None:
    assert looks_like_topic_concentration_candidate("怎么儿童节不叫人打游戏")


def test_parse_ai_proactive_reply_decision_json() -> None:
    decision = parse_ai_proactive_reply_decision(
        '{"should_reply": true, "topic_key": "图灵完备线路", "topic_type": "游戏技术讨论", '
        '"reason": "群友正在讨论线路怎么接", "reply_style": "technical", "max_length": "detail"}'
    )

    assert decision.should_reply
    assert decision.topic_key == "图灵完备线路"
    assert decision.topic_type == "游戏技术讨论"
    assert decision.reply_style == "technical"
    assert decision.max_length == "detail"


def test_parse_ai_proactive_reply_decision_fenced_json() -> None:
    decision = parse_ai_proactive_reply_decision(
        """```json
{"should_reply": false, "topic_key": "棉花糖双子", "topic_type": "第三方提及", "reason": "是在让别的 bot 呼叫棉花糖双子", "reply_style": "casual", "max_length": "short"}
```"""
    )

    assert not decision.should_reply
    assert decision.topic_key == "棉花糖双子"
    assert decision.max_length == "short"


def test_ai_decision_prompt_defines_topic_concentration_and_interest() -> None:
    prompt = build_ai_proactive_reply_decision_prompt(
        [
            TopicConcentrationMessage("图灵完备里面线路怎么接？", "1001"),
            TopicConcentrationMessage("某种分馏塔怎么用", "1002"),
        ],
        active_interest=ProactiveTopicInterest(
            topic_key="图灵完备线路",
            topic_type="游戏技术讨论",
            reason="短时间内群友持续问线路连接",
        ),
    )

    assert "不是求助/诊断/疑问词数量" in prompt
    assert "图灵完备里面线路怎么接" in prompt
    assert "某种分馏塔怎么用" in prompt
    assert "当前短期高兴趣话题" in prompt
    assert "无关插话" in prompt


def test_third_party_named_mentions_do_not_trigger() -> None:
    assert not looks_like_ai_named_trigger("你能不能@下群里的有个叫棉花糖的人，让他帮你分析下我这么问你的目的")
    assert not looks_like_ai_named_trigger("你去呼叫一下棉花糖双子，她俩也是猫娘")
    assert not looks_like_topic_concentration_candidate("你去呼叫一下棉花糖双子，她俩也是猫娘")


def test_direct_named_call_still_triggers() -> None:
    assert looks_like_ai_named_trigger("呼叫棉花糖，帮我看下配置")
    assert looks_like_topic_concentration_candidate("棉花糖，这个配置怎么看？")


def test_topic_prompt_keeps_recent_chat_scope() -> None:
    prompt = build_topic_concentration_prompt(
        [
            TopicConcentrationMessage("GTNH 有连锁吗？", "1001"),
            TopicConcentrationMessage("匠魂锤子也挖不了一片", "1002"),
        ],
        active_interest=ProactiveTopicInterest(
            topic_key="GTNH 连锁",
            topic_type="模组机制讨论",
            reason="多人讨论同一个挖掘机制",
        ),
    )

    assert "适合棉花糖加入" in prompt
    assert "当前短期高兴趣话题" in prompt
    assert "用户1001: GTNH 有连锁吗？" in prompt
    assert "不要解释主动介入机制" in prompt
