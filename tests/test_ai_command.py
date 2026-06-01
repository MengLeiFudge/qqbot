from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.ai_command import (
    AiChatTriggerKind,
    build_ai_conversation_key,
    classify_ai_chat_trigger,
    looks_like_ai_meta_conversation,
    looks_like_ai_proactive_trigger,
    looks_like_ai_named_trigger,
    parse_ai_output_mode_command,
    parse_ai_model_command,
    should_handle_ai_chat,
)
from qqbot.services.ai_conversation_store import AiConversationStore


class FakeEvent:
    def __init__(
        self,
        message_type: str,
        user_id: str,
        *,
        group_id: str | None = None,
        to_me: bool = False,
        event_time: int | None = None,
    ) -> None:
        self.message_type = message_type
        self.user_id = user_id
        if event_time is not None:
            self.time = event_time
        if group_id is not None:
            self.group_id = group_id
        self._to_me = to_me

    def get_user_id(self) -> str:
        return self.user_id

    def is_tome(self) -> bool:
        return self._to_me


def test_private_plain_message_enters_ai_chat() -> None:
    assert should_handle_ai_chat(FakeEvent("private", "10001"), "你好") is True
    assert should_handle_ai_chat(FakeEvent("private", "10001"), "/status") is False
    assert should_handle_ai_chat(FakeEvent("private", "10001"), "菜单") is False
    assert should_handle_ai_chat(FakeEvent("private", "10001"), "") is False


def test_group_plain_chat_uses_conservative_proactive_trigger() -> None:
    assert (
        should_handle_ai_chat(
            FakeEvent("group", "10001", group_id="20001", to_me=True),
            "你好",
        )
        is True
    )
    assert (
        should_handle_ai_chat(
            FakeEvent("group", "10001", group_id="20001", to_me=False),
            "你好",
        )
        is False
    )
    assert (
        should_handle_ai_chat(
            FakeEvent("group", "10001", group_id="20001", to_me=False),
            "请问这个怎么修？",
        )
        is True
    )
    assert (
        should_handle_ai_chat(
            FakeEvent("group", "10001", group_id="20001", to_me=True),
            "菜单",
        )
        is False
    )


def test_group_proactive_ai_chat_uses_global_trigger() -> None:
    event = FakeEvent("group", "10001", group_id="20001", to_me=False)

    assert classify_ai_chat_trigger(event, "棉花糖在吗") == AiChatTriggerKind.NAMED
    assert (
        classify_ai_chat_trigger(
            event,
            "请问这个怎么修？",
            bot_names=("萌萌棉花糖♪",),
        )
        == AiChatTriggerKind.PROACTIVE
    )
    assert (
        should_handle_ai_chat(
            event,
            "今天天气不错",
            bot_names=("萌萌棉花糖♪",),
        )
        is False
    )


def test_group_named_trigger_enters_ai_chat() -> None:
    event = FakeEvent("group", "10001", group_id="20001", to_me=False)

    assert classify_ai_chat_trigger(
        event,
        "呼叫棉花糖",
        bot_names=("萌萌棉花糖♪",),
    ) == AiChatTriggerKind.NAMED
    assert should_handle_ai_chat(
        event,
        "棉花糖帮我看下这个",
        bot_names=("萌萌棉花糖♪",),
    ) is True


def test_group_direct_at_without_text_enters_ai_chat() -> None:
    assert (
        should_handle_ai_chat(
            FakeEvent("group", "10001", group_id="20001", to_me=True),
            "",
        )
        is True
    )
    assert (
        should_handle_ai_chat(
            FakeEvent("group", "10001", group_id="20001", to_me=False),
            "",
        )
        is False
    )


def test_group_manager_welcome_message_does_not_enter_ai_chat() -> None:
    assert (
        should_handle_ai_chat(
            FakeEvent("group", "2854196310", group_id="927625724", to_me=True),
            "欢迎 @棉花糖 加入本群，请先阅读群公告。",
        )
        is False
    )

    assert (
        should_handle_ai_chat(
            FakeEvent("group", "2854196310", group_id="927625724", to_me=True),
            "欢迎 @萌萌棉花糖♪ 入群。",
        )
        is False
    )

    assert (
        should_handle_ai_chat(
            FakeEvent("group", "285419631", group_id="927625724", to_me=True),
            "欢迎 @棉花糖 加入本群，请先阅读群公告。",
        )
        is True
    )


def test_group_draw_command_enters_ai_chat_without_direct_at() -> None:
    assert (
        should_handle_ai_chat(
            FakeEvent("group", "10001", group_id="20001", to_me=False),
            "棉花糖生图 卡拉比丘联动原神的宣传图",
        )
        is True
    )
    assert (
        should_handle_ai_chat(
            FakeEvent("group", "10001", group_id="20001", to_me=False),
            "生成卡拉比丘联动原神的宣传图",
        )
        is True
    )


def test_group_draw_model_help_enters_ai_chat_without_direct_at() -> None:
    assert (
        should_handle_ai_chat(
            FakeEvent("group", "10001", group_id="20001", to_me=False),
            "生图模型说明",
        )
        is True
    )
    assert (
        should_handle_ai_chat(
            FakeEvent("group", "10001", group_id="20001", to_me=False),
            "棉花糖生图价格",
        )
        is True
    )


def test_old_group_messages_do_not_enter_ai_chat(monkeypatch) -> None:
    monkeypatch.setattr(
        "qqbot.services.ai_command.is_before_onebot_connect",
        lambda event_time: event_time == 9,
    )

    assert (
        should_handle_ai_chat(
            FakeEvent("group", "10001", group_id="20001", to_me=True, event_time=9),
            "你好",
        )
        is False
    )
    assert (
        should_handle_ai_chat(
            FakeEvent("group", "10001", group_id="20001", to_me=False, event_time=9),
            "棉花糖生图 卡拉比丘联动原神的宣传图",
        )
        is False
    )
    assert should_handle_ai_chat(FakeEvent("private", "10001", event_time=9), "你好") is False
    assert should_handle_ai_chat(FakeEvent("private", "10001", event_time=10), "你好") is True


def test_parse_ai_model_command_lists_or_switches_profile() -> None:
    status_command = parse_ai_model_command("AI模型")
    switch_command = parse_ai_model_command("切换AI xiaomi")

    assert status_command is not None
    assert status_command.action == "status"
    assert status_command.profile is None
    assert switch_command is not None
    assert switch_command.action == "switch"
    assert switch_command.profile == "xiaomi"
    assert parse_ai_model_command("ai xiaomi 你好") is None


def test_parse_ai_output_mode_command_accepts_group_and_private_commands() -> None:
    assert parse_ai_output_mode_command("AI回复模式").action == "status"
    assert parse_ai_output_mode_command("回复模式").action == "status"
    assert parse_ai_output_mode_command("AI语音模式").mode == "voice"
    assert parse_ai_output_mode_command("AI文字模式").mode == "text"
    assert parse_ai_output_mode_command("切换语音").mode == "voice"
    assert parse_ai_output_mode_command("切到语音").mode == "voice"
    assert parse_ai_output_mode_command("语音回复").mode == "voice"
    assert parse_ai_output_mode_command("切换文字").mode == "text"
    assert parse_ai_output_mode_command("切换文本").mode == "text"
    assert parse_ai_output_mode_command("切回文字").mode == "text"
    assert parse_ai_output_mode_command("文字回复").mode == "text"

    group_voice = parse_ai_output_mode_command("本群AI语音模式")
    assert group_voice is not None
    assert group_voice.action == "set"
    assert group_voice.scope == "group"
    assert group_voice.mode == "voice"

    user_text = parse_ai_output_mode_command("我的AI文字模式")
    assert user_text is not None
    assert user_text.action == "set"
    assert user_text.scope == "user"
    assert user_text.mode == "text"

    group_short_voice = parse_ai_output_mode_command("本群切换语音")
    assert group_short_voice is not None
    assert group_short_voice.action == "set"
    assert group_short_voice.scope == "group"
    assert group_short_voice.mode == "voice"

    user_short_text = parse_ai_output_mode_command("我的切换文本")
    assert user_short_text is not None
    assert user_short_text.action == "set"
    assert user_short_text.scope == "user"
    assert user_short_text.mode == "text"

    assert parse_ai_output_mode_command("AI模型") is None


def test_ai_proactive_trigger_matches_bot_name_or_direct_help() -> None:
    assert looks_like_ai_proactive_trigger("萌萌棉花糖在吗", bot_names=("萌萌棉花糖♪",))
    assert looks_like_ai_proactive_trigger("请问这个怎么修？", bot_names=())
    assert not looks_like_ai_proactive_trigger("我只是普通闲聊", bot_names=())


def test_ai_proactive_trigger_ignores_self_review_false_positive_samples() -> None:
    event = FakeEvent("group", "10001", group_id="20001", to_me=False)

    for prompt in (
        "怎么分配啊",
        "怎么儿童节不叫人打游戏",
        "当儿童去了？",
        "群文件好像快要爆了",
        "怎么清理一下",
    ):
        assert looks_like_ai_proactive_trigger(prompt, bot_names=()) is False
        assert classify_ai_chat_trigger(event, prompt) == AiChatTriggerKind.IGNORE

    assert classify_ai_chat_trigger(event, "请问这个怎么修？") == AiChatTriggerKind.PROACTIVE
    assert classify_ai_chat_trigger(event, "一进沙盒组件都没了怎么办") == AiChatTriggerKind.PROACTIVE


def test_ai_proactive_trigger_ignores_third_party_ai_meta_discussion() -> None:
    event = FakeEvent("group", "10001", group_id="20001", to_me=False)

    for prompt in (
        "ai写的",
        "我问为什么报错，说不支持",
        "对啊",
        "那就让ai查呗",
        "让他自己改到支持",
        "实现我也没问",
        "反正我让gpt自己改的",
        "直接给我降级",
        "这些接口肯定都有",
    ):
        assert looks_like_ai_proactive_trigger(prompt, bot_names=()) is False
        assert classify_ai_chat_trigger(event, prompt) == AiChatTriggerKind.IGNORE

    assert classify_ai_chat_trigger(event, "请问 NapCat 合并消息报错怎么修？") == AiChatTriggerKind.PROACTIVE


def test_ai_proactive_trigger_ignores_self_review_evidence_sequence() -> None:
    event = FakeEvent("group", "10001", group_id="437320340", to_me=False)

    prompts = (
        "ai写的",
        "但是报错",
        "我问为什么报错，说不支持",
        "让他自己改到支持",
        "实现我也没问",
        "反正我让gpt自己改的",
        "直接给我降级",
        "这些接口肯定都有",
    )

    assert looks_like_ai_meta_conversation("我问为什么报错，说不支持") is True
    for prompt in prompts:
        assert looks_like_ai_proactive_trigger(prompt, bot_names=()) is False
        assert classify_ai_chat_trigger(event, prompt) == AiChatTriggerKind.IGNORE

    assert classify_ai_chat_trigger(event, "请问 OneBot 卡片消息报错怎么修？") == AiChatTriggerKind.PROACTIVE


def test_ai_named_trigger_requires_calling_bot() -> None:
    assert looks_like_ai_named_trigger("呼叫棉花糖", bot_names=("萌萌棉花糖♪",))
    assert looks_like_ai_named_trigger("棉花糖在吗", bot_names=("萌萌棉花糖♪",))
    assert looks_like_ai_named_trigger("棉花糖帮我看看", bot_names=("萌萌棉花糖♪",))
    assert looks_like_ai_named_trigger("我想听棉花糖啊呀～", bot_names=("萌萌棉花糖♪",))
    assert not looks_like_ai_named_trigger("萌泪酱是棉花糖的主人", bot_names=("萌萌棉花糖♪",))


def test_ai_output_mode_command_does_not_enter_ai_chat() -> None:
    assert (
        should_handle_ai_chat(
            FakeEvent("group", "10001", group_id="20001", to_me=True),
            "本群AI语音模式",
        )
        is False
    )
    assert should_handle_ai_chat(FakeEvent("private", "10001"), "我的AI文字模式") is False
    assert should_handle_ai_chat(FakeEvent("private", "10001"), "切换语音") is False


def test_build_ai_conversation_key_uses_private_or_group_scope(tmp_path: Path) -> None:
    store = AiConversationStore(tmp_path)

    assert build_ai_conversation_key(
        store,
        FakeEvent("private", "605738729"),
        "xiaomi",
        "2026-05-17T04:00",
    ) == (
        "private:605738729:xiaomi:2026-05-17T04:00"
    )
    assert build_ai_conversation_key(
        store,
        FakeEvent("group", "605738729", group_id="516286670", to_me=True),
        "xiaomi",
        "2026-05-17T04:00",
    ) == "group:516286670:xiaomi:2026-05-17T04:00"
