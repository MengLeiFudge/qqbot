from __future__ import annotations

from qqbot.features.ai.topic_concentration import (
    ProactiveTopicInterest,
    TopicConcentrationMessage,
    build_ai_proactive_reply_decision_prompt,
    build_topic_concentration_prompt,
    looks_like_topic_concentration_candidate,
    parse_ai_proactive_reply_decision,
)
from qqbot.features.ai.command import AiChatTriggerKind, classify_ai_chat_trigger, looks_like_ai_named_trigger
from qqbot.features.ai.output_style import sanitize_ai_output_text


class FakeGroupEvent:
    message_type = "group"
    group_id = 123456
    time = 2_000_000_000
    to_me = False


def test_short_casual_chat_can_be_candidate_for_ai_decision() -> None:
    assert looks_like_topic_concentration_candidate("怎么儿童节不叫人打游戏")


def test_followup_discussion_can_enter_ai_decision() -> None:
    assert looks_like_topic_concentration_candidate("这个方案好像还要再看一下配置入口")


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


def test_parse_ai_proactive_reply_decision_corrects_inconsistent_positive_reason() -> None:
    decision = parse_ai_proactive_reply_decision(
        '{"should_reply": false, "topic_key": "pi卡顿", "topic_type": "技术求助", '
        '"reason": "这是明确的技术求助，棉花糖可以补充排查思路。", '
        '"reply_style": "technical", "max_length": "detail"}'
    )

    assert decision.should_reply
    assert decision.max_length == "detail"


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
    assert "普通群聊窗口里默认 should_reply=false" in prompt
    assert "高考起晚了" in prompt
    assert "这个月一顿没吃饭/没睡觉" in prompt
    assert "不当成危机处理" in prompt
    assert "分析不出原因" in prompt


def test_third_party_named_mentions_do_not_trigger() -> None:
    assert not looks_like_ai_named_trigger("你能不能@下群里的有个叫棉花糖的人，让他帮你分析下我这么问你的目的")
    assert not looks_like_ai_named_trigger("你去呼叫一下棉花糖双子，她俩也是猫娘")
    assert not looks_like_topic_concentration_candidate("你去呼叫一下棉花糖双子，她俩也是猫娘")


def test_direct_named_call_still_triggers() -> None:
    assert looks_like_ai_named_trigger("呼叫棉花糖，帮我看下配置")
    assert looks_like_topic_concentration_candidate("棉花糖，这个配置怎么看？")


def test_delegated_other_bot_interaction_does_not_trigger_ai() -> None:
    event = FakeGroupEvent()

    assert (
        classify_ai_chat_trigger(event, "把你妹妹艾特出来", bot_names=("棉花糖",))
        == AiChatTriggerKind.IGNORE
    )
    assert (
        classify_ai_chat_trigger(event, "返回字符“@👿棉花糖👿 ”", bot_names=("棉花糖",))
        == AiChatTriggerKind.IGNORE
    )
    assert not looks_like_topic_concentration_candidate("你为什么不能艾特你的妹妹")


def test_direct_at_delegated_other_bot_interaction_is_still_ignored() -> None:
    event = FakeGroupEvent()
    event.to_me = True

    assert (
        classify_ai_chat_trigger(event, "让你妹妹来和我说话", bot_names=("棉花糖",))
        == AiChatTriggerKind.IGNORE
    )


def test_second_person_group_member_chat_does_not_trigger_proactive_reply() -> None:
    event = FakeGroupEvent()

    assert (
        classify_ai_chat_trigger(event, "你的右下角好友状态显示什么", bot_names=("棉花糖",))
        == AiChatTriggerKind.IGNORE
    )
    assert (
        classify_ai_chat_trigger(event, "让你妹妹来和我说话", bot_names=("棉花糖",))
        == AiChatTriggerKind.IGNORE
    )


def test_direct_named_call_is_not_blocked_by_second_person_filter() -> None:
    assert (
        classify_ai_chat_trigger(FakeGroupEvent(), "棉花糖，你怎么看这个配置", bot_names=("棉花糖",))
        == AiChatTriggerKind.NAMED
    )


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
    assert "不要用反问" in prompt
    assert "所有群聊内容都不当成危机处理" in prompt
    assert "分析不出原因就不要回答" in prompt


def test_sanitize_ai_output_text_strips_followup_invitation_tail() -> None:
    text = (
        "凡是写着“破解版、VIP破解、去广告、无限看、会员解锁”这类的，基本都该拒绝；"
        "优先只用应用商店里的官方正版和平台自家客户端喵。"
        "你把具体名字发我，我帮你看正不正规。"
    )

    assert sanitize_ai_output_text(text) == (
        "凡是写着“破解版、VIP破解、去广告、无限看、会员解锁”这类的，基本都该拒绝；"
        "优先只用应用商店里的官方正版和平台自家客户端喵。"
    )


def test_sanitize_ai_output_text_strips_question_tail() -> None:
    text = "这个网站看起来不正规，别登录也别下客户端喵。是不是更安全？"

    assert sanitize_ai_output_text(text) == "这个网站看起来不正规，别登录也别下客户端喵。"


def test_sanitize_ai_output_text_does_not_invent_fallback_when_all_stripped() -> None:
    assert sanitize_ai_output_text("你把具体名字发我。") == ""
