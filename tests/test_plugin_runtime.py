from pathlib import Path
import sys
import asyncio
import re
from types import SimpleNamespace

from nonebot.adapters.onebot.v11 import Message

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import qqbot.plugins.arc as arc
import qqbot.plugins.basic_management as basic_management
import qqbot.plugins.group_control as group_control
import qqbot.services.group_control_service as group_control_service
import qqbot.plugins.lolicon as lolicon
import qqbot.plugins.reread as reread
import qqbot.plugins.social as social
import qqbot.plugins.thunder as thunder
from qqbot.services.message_delivery import reset_group_message_interval_state


def test_reread_feature_binding_points_to_group_assistant() -> None:
    feature = reread.get_reread_feature()

    assert feature is not None
    assert feature.plugin_id == "group_assistant"
    assert feature.name == "群管助手"


def test_thunder_feature_binding_points_to_group_assistant() -> None:
    feature = thunder.get_thunder_feature()

    assert feature is not None
    assert feature.plugin_id == "group_assistant"
    assert feature.name == "群管助手"


def test_arc_blocking_bridge_uses_run_blocking(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_run_blocking(func, *args, **kwargs):
        captured["func"] = func
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {"status": 0}

    monkeypatch.setattr(arc, "run_blocking", fake_run_blocking)

    def fake_fetch(arc_id: str) -> dict:
        return {"status": 0, "arc_id": arc_id}

    result = asyncio.run(arc.call_arc_service(fake_fetch, "123456789"))

    assert result == {"status": 0}
    assert captured["func"] is fake_fetch
    assert captured["args"] == ("123456789",)
    assert captured["kwargs"] == {}


def test_arc_activity_aliases_share_same_route() -> None:
    assert arc.is_arc_activity_command("archd") is True
    assert arc.is_arc_activity_command("arctz") is True
    assert arc.is_arc_activity_command("act") is False
    assert arc.is_arc_activity_command("arctj 10.5") is False


def test_arc_guess_command_parsers_match_new_shapes() -> None:
    assert arc.parse_arc_recommend_ptt("arctj10.5") == 10.5
    assert arc.parse_arc_recommend_ptt("arctj 10.5") == 10.5
    assert arc.parse_arc_recommend_ptt("arc 10.5") is None
    assert arc.parse_arc_guess_start_count("arczm") == 10
    assert arc.parse_arc_guess_start_count("arczm5") == 5
    assert arc.parse_arc_guess_start_count("arczm 5") == 5
    assert arc.parse_arc_guess_start_count("zm") == 10
    assert arc.parse_arc_guess_start_count("zm5") == 5
    assert arc.parse_arc_guess_start_count("zm 5") == 5
    assert arc.parse_arc_guess_start_count("ag 10") is None
    assert arc.parse_arc_guess_start_count("/arc猜歌 字母 10") is None
    assert arc.is_arc_guess_art_start_command("arcqh") is True
    assert arc.is_arc_guess_art_start_command("qh") is True
    assert arc.parse_arc_guess_art_grid_size("arcqh5") == 5
    assert arc.parse_arc_guess_art_grid_size("arcqh 5") == 5
    assert arc.parse_arc_guess_art_grid_size("qhmax") == "max"
    assert arc.parse_arc_guess_art_grid_size("qh max") == "max"
    assert arc.parse_arc_guess_art_grid_size("arcqh") is None
    assert arc.is_arc_guess_add_art_tile_command("arcqh bt") is True
    assert arc.is_arc_guess_add_art_tile_command("arcqh 补图") is True
    assert arc.is_arc_guess_add_art_tile_command("qh") is True
    assert arc.is_arc_guess_reveal_command("arcjx") is True
    assert arc.is_arc_guess_reveal_command("jx") is True
    assert arc.is_arc_apk_update_command("xz") is True
    assert arc.is_arc_apk_update_command("arcxz") is True
    assert arc.parse_arc_open_letter("开a") == "a"
    assert arc.parse_arc_open_letter("开 a") == "a"
    assert arc.parse_arc_open_letter("开 β") == "β"
    assert arc.parse_arc_open_letter("开*") == "*"
    assert arc.parse_arc_open_letter("开[") == "["
    assert arc.parse_arc_open_letter("ao *") is None
    assert arc.parse_arc_guess_submission("10骨折光") == (10, "骨折光")
    assert arc.parse_arc_guess_submission("10 骨折光") == (10, "骨折光")
    assert arc.parse_arc_guess_submission("10 We're all gonna die") == (10, "We're all gonna die")
    assert arc.parse_arc_guess_submission("猜10骨折光") == (10, "骨折光")
    assert arc.parse_arc_guess_submission("猜10 骨折光") == (10, "骨折光")
    assert arc.parse_arc_guess_submission("猜 10骨折光") == (10, "骨折光")
    assert arc.parse_arc_guess_submission("猜 10 骨折光") == (10, "骨折光")
    assert arc.parse_arc_guess_submission("猜 骨折光") is None
    assert arc.parse_arc_guess_submission("猜骨折光") is None
    assert arc.parse_arc_guess_art_submission("猜 骨折光") == "骨折光"
    assert arc.parse_arc_guess_art_submission("猜骨折光") == "骨折光"
    assert arc.parse_arc_guess_art_submission("骨折光") == "骨折光"
    assert arc.parse_arc_guess_art_submission("quon") == "quon"
    assert arc.parse_arc_guess_art_submission("10骨折光") is None
    assert arc.parse_arc_guess_art_submission("猜10骨折光") is None
    assert arc.parse_arc_guess_art_submission("arcqh") is None
    assert arc.parse_arc_guess_art_submission("jx") is None
    assert arc.parse_arc_guess_art_submission("xz") is None
    assert arc.parse_arc_guess_art_submission("arcxz") is None


def test_arc_guess_start_is_group_only() -> None:
    group_event = SimpleNamespace(group_id=2333)
    private_event = SimpleNamespace(group_id=None)

    assert arc.can_start_arc_guess(group_event) is True
    assert arc.can_start_arc_guess(private_event) is False


def test_arc_guess_text_is_not_group_control_command() -> None:
    assert arc.parse_arc_guess_submission("2eden") == (2, "eden")
    assert group_control_service.parse_group_control_command("2eden", []) is None
    assert re.match(group_control.GROUP_CONTROL_PATTERN, "2eden") is None
    assert re.match(arc.ARC_GUESS_ANSWER_PATTERN, "2eden") is not None


def test_group_file_cleanup_commands_are_group_control_commands() -> None:
    assert group_control.is_group_file_cleanup_command("通知清理文件") is True
    assert group_control.is_group_file_cleanup_command("清理群文件") is True
    assert re.match(group_control.GROUP_CONTROL_PATTERN, "通知清理文件") is not None
    assert group_control.is_group_file_cleanup_command("清理缓存") is False


def test_arc_guess_answer_matchers_require_enabled_active_session(monkeypatch) -> None:
    class FakeGroupEvent:
        group_id = 516286670

        def __init__(self, text: str, event_time: int = 10) -> None:
            self.text = text
            self.time = event_time

        def get_plaintext(self) -> str:
            return self.text

    class FakeService:
        def __init__(self, session) -> None:
            self.session = session

        def get_session(self, _room_id: int):
            return self.session

    async def disabled(_event) -> bool:
        return False

    async def enabled(_event) -> bool:
        return True

    monkeypatch.setattr(arc, "GroupMessageEvent", FakeGroupEvent)
    monkeypatch.setattr(arc, "ensure_arc_enabled", disabled)
    monkeypatch.setattr(arc, "get_arc_guess_service", lambda: FakeService(SimpleNamespace(mode="letters")))

    assert asyncio.run(arc.has_active_arc_letter_session(FakeGroupEvent("814是房租吗"))) is False

    monkeypatch.setattr(arc, "ensure_arc_enabled", enabled)
    monkeypatch.setattr(arc, "is_before_onebot_connect", lambda event_time: event_time == 9)
    assert asyncio.run(arc.has_active_arc_letter_session(FakeGroupEvent("814是房租吗", event_time=9))) is False
    assert asyncio.run(arc.has_active_arc_letter_answer(FakeGroupEvent("10骨折光", event_time=9))) is False
    assert asyncio.run(arc.has_active_arc_art_game(FakeGroupEvent("猜 arcahv", event_time=9))) is False

    monkeypatch.setattr(arc, "is_before_onebot_connect", lambda event_time: False)
    assert asyncio.run(arc.has_active_arc_letter_session(FakeGroupEvent("814是房租吗"))) is True
    assert asyncio.run(arc.has_active_arc_letter_answer(FakeGroupEvent("10 We're all gonna die"))) is True
    assert asyncio.run(arc.has_active_arc_letter_answer(FakeGroupEvent(" 10 We're all gonna die "))) is True

    monkeypatch.setattr(arc, "get_arc_guess_service", lambda: FakeService(None))
    assert asyncio.run(arc.has_active_arc_letter_session(FakeGroupEvent("814是房租吗"))) is False

    monkeypatch.setattr(arc, "get_arc_guess_service", lambda: FakeService(SimpleNamespace(mode="art")))
    assert asyncio.run(arc.has_active_arc_art_game(FakeGroupEvent("猜 arcahv"))) is True
    assert asyncio.run(arc.has_active_arc_letter_session(FakeGroupEvent("814是房租吗"))) is False


def test_feature_menu_matcher_accepts_arc_aliases() -> None:
    pattern = basic_management.FEATURE_MENU_PATTERN

    assert re.match(pattern, "菜单13") is None
    assert re.match(pattern, "菜单arc") is not None
    assert re.match(pattern, "菜单arcaea") is not None
    assert re.match(pattern, "菜单群管助手") is not None


class FakeBot:
    def __init__(self, self_id: str) -> None:
        self.self_id = self_id
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def call_api(self, api: str, **data: object) -> None:
        self.calls.append((api, data))
        if api == "get_group_info":
            return {"group_id": data.get("group_id"), "group_name": "测试群"}


def test_group_file_cleanup_handler_uses_current_group(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class FakeCleanupService:
        def __init__(self, *, store, group_id: str, timezone_name: str) -> None:
            captured["store"] = store
            captured["group_id"] = group_id
            captured["timezone_name"] = timezone_name

        async def scan_and_notify_group(self, bot) -> dict[str, object]:
            captured["bot"] = bot
            return {"violating_user_count": 0}

    monkeypatch.setattr(
        group_control,
        "load_settings",
        lambda: SimpleNamespace(data_root=tmp_path, timezone="Asia/Shanghai"),
    )
    monkeypatch.setattr(group_control, "ShapezGroupFileCleanupService", FakeCleanupService)
    bot = FakeBot(self_id="114514")

    result = asyncio.run(group_control.handle_group_file_cleanup_command(bot, 2333))

    assert result == {"violating_user_count": 0}
    assert captured["group_id"] == "2333"
    assert captured["timezone_name"] == "Asia/Shanghai"
    assert captured["bot"] is bot
    assert bot.calls == [
        ("send_group_msg", {"group_id": 2333, "message": "当前没有超过一周的外层群文件需要清理。"})
    ]


class FakeRereadEvent:
    group_id = 2333
    time = 10
    self_id = "114514"

    def __init__(self, text: str = "我的城堡还没倒，我还能战！") -> None:
        self.text = text

    def get_user_id(self) -> str:
        return "744306344"

    def get_plaintext(self) -> str:
        return self.text

    def get_message(self) -> Message:
        return Message(self.text)


class FakeRereadStore:
    def get_group_feature_state(self, group_id: int, feature) -> bool:
        return True

    def is_bot_admin_or_self(self, qq: int, self_id: object) -> bool:
        return True


class FakeSocialStore:
    def get_group_feature_state(self, group_id: int, feature) -> bool:
        return True

    def is_bot_admin_or_self(self, qq: int, self_id: object) -> bool:
        return int(qq) == 605738729 or str(qq) == str(self_id)


def test_reread_repeats_second_duplicate_once(monkeypatch) -> None:
    sent_messages: list[object] = []

    async def fake_send(message: object) -> None:
        sent_messages.append(message)

    monkeypatch.setattr(reread, "get_settings_store", lambda: FakeRereadStore())
    monkeypatch.setattr(reread, "_REREAD_STATE", reread.RereadRepeatState())
    monkeypatch.setattr(reread.reread_message_matcher, "send", fake_send)

    asyncio.run(reread.handle_reread_message(FakeRereadEvent("复读内容")))
    asyncio.run(reread.handle_reread_message(FakeRereadEvent("复读内容")))
    asyncio.run(reread.handle_reread_message(FakeRereadEvent("复读内容")))

    assert [str(message) for message in sent_messages] == ["复读内容"]


def test_reread_resets_after_different_message(monkeypatch) -> None:
    sent_messages: list[object] = []

    async def fake_send(message: object) -> None:
        sent_messages.append(message)

    monkeypatch.setattr(reread, "get_settings_store", lambda: FakeRereadStore())
    monkeypatch.setattr(reread, "_REREAD_STATE", reread.RereadRepeatState())
    monkeypatch.setattr(reread.reread_message_matcher, "send", fake_send)

    for text in ("A", "A", "B", "B"):
        asyncio.run(reread.handle_reread_message(FakeRereadEvent(text)))

    assert [str(message) for message in sent_messages] == ["A", "B"]


def test_reread_skips_old_group_message(monkeypatch) -> None:
    sent_messages: list[object] = []

    class OldRereadEvent(FakeRereadEvent):
        time = 9

    async def fake_send(message: object) -> None:
        sent_messages.append(message)

    monkeypatch.setattr(reread, "is_before_onebot_connect", lambda event_time: event_time == 9)
    monkeypatch.setattr(reread, "get_settings_store", lambda: FakeRereadStore())
    monkeypatch.setattr(reread, "_REREAD_STATE", reread.RereadRepeatState())
    monkeypatch.setattr(reread.reread_message_matcher, "send", fake_send)

    asyncio.run(reread.handle_reread_message(OldRereadEvent("旧消息")))

    assert sent_messages == []


def test_social_group_poke_uses_group_poke_api(monkeypatch) -> None:
    reset_group_message_interval_state()
    order: list[tuple[str, object]] = []

    class OrderedBot(FakeBot):
        async def call_api(self, api: str, **data: object) -> None:
            order.append(("api", api))
            await super().call_api(api, **data)

    async def fake_sleep(seconds: float) -> None:
        order.append(("sleep", seconds))

    monkeypatch.setattr(social.random, "randint", lambda _a, _b: 1)
    monkeypatch.setattr(social, "asyncio", SimpleNamespace(sleep=fake_sleep), raising=False)
    monkeypatch.setattr(social, "get_settings_store", lambda: FakeSocialStore())
    bot = OrderedBot(self_id="114514")
    event = SimpleNamespace(group_id=2333, user_id=605738729, target_id=114514)

    asyncio.run(social.handle_poke(bot, event))

    assert [api for api, _ in bot.calls] == [
        "send_group_msg",
        "send_group_msg",
        "group_poke",
        "send_group_msg",
        "group_poke",
    ]
    assert bot.calls[2][1] == {"group_id": "2333", "user_id": "605738729"}
    assert bot.calls[4][1] == {"group_id": "2333", "user_id": "605738729"}
    assert order[0:2] == [("api", "send_group_msg"), ("sleep", 1.0)]
    assert order[2][0] == "sleep"
    assert 0 < float(order[2][1]) <= 0.5
    assert order[3:6] == [
        ("api", "send_group_msg"),
        ("api", "group_poke"),
        ("sleep", 1.0),
    ]
    assert order[6][0] == "sleep"
    assert 0 < float(order[6][1]) <= 0.5
    assert order[7:] == [("api", "send_group_msg"), ("api", "group_poke")]


def test_social_private_poke_uses_friend_poke_api(monkeypatch) -> None:
    monkeypatch.setattr(social.random, "randint", lambda _a, _b: 4)
    monkeypatch.setattr(social, "get_settings_store", lambda: FakeSocialStore())
    bot = FakeBot(self_id="114514")
    event = SimpleNamespace(group_id=None, user_id=605738729, target_id=114514)

    asyncio.run(social.handle_poke(bot, event))

    assert [api for api, _ in bot.calls] == ["send_private_msg", "send_private_msg", "friend_poke"]
    assert bot.calls[2][1] == {"user_id": "605738729"}


def test_social_request_only_auto_approves_bot_admin(monkeypatch) -> None:
    class FakeFriendRequest:
        request_type = "friend"

        def __init__(self, user_id: int) -> None:
            self.user_id = user_id
            self.flag = f"friend-{user_id}"
            self.approved = False

        async def approve(self, _bot) -> None:
            self.approved = True

    monkeypatch.setattr(social, "FriendRequestEvent", FakeFriendRequest)
    monkeypatch.setattr(social, "get_settings_store", lambda: FakeSocialStore())
    bot = FakeBot(self_id="114514")
    admin_event = FakeFriendRequest(605738729)
    normal_event = FakeFriendRequest(10001)

    asyncio.run(social.handle_request(bot, normal_event))
    asyncio.run(social.handle_request(bot, admin_event))

    assert normal_event.approved is False
    assert admin_event.approved is False
    assert bot.calls == [
        (
            "set_friend_add_request",
            {"flag": "friend-605738729", "approve": True},
        )
    ]


def test_social_group_invite_uses_explicit_onebot_api_for_bot_admin(monkeypatch) -> None:
    class FakeGroupRequest:
        request_type = "group"
        sub_type = "invite"
        group_id = 1093545322
        user_id = 605738729
        flag = "1778310891077215"

        def __init__(self) -> None:
            self.approved = False

        async def approve(self, _bot) -> None:
            self.approved = True

    monkeypatch.setattr(social, "GroupRequestEvent", FakeGroupRequest)
    monkeypatch.setattr(social, "get_settings_store", lambda: FakeSocialStore())
    bot = FakeBot(self_id="114514")
    event = FakeGroupRequest()

    asyncio.run(social.handle_request(bot, event))

    assert event.approved is False
    assert bot.calls == [
        (
            "set_group_add_request",
            {
                "flag": "1778310891077215",
                "sub_type": "invite",
                "approve": True,
            },
        )
    ]


def test_social_group_increase_sends_inviter_notice_and_group_intro(monkeypatch) -> None:
    class FakeGroupIncrease:
        group_id = 1093545322
        user_id = 114514
        operator_id = 605738729

    monkeypatch.setattr(social, "GroupIncreaseNoticeEvent", FakeGroupIncrease)
    bot = FakeBot(self_id="114514")

    asyncio.run(social.handle_group_increase(bot, FakeGroupIncrease()))

    assert bot.calls == [
        (
            "get_group_info",
            {"group_id": 1093545322, "no_cache": True},
        ),
        (
            "send_private_msg",
            {"user_id": 605738729, "message": "棉花糖已经加入「测试群」啦，主人喵！"},
        ),
        (
            "send_group_msg",
            {
                "group_id": 1093545322,
                "message": social.BOT_GROUP_INTRO_MESSAGE,
            },
        ),
    ]
    assert "我是萌萌棉花糖♪" in social.BOT_GROUP_INTRO_MESSAGE
    assert "只有萌泪酱才是我最伟大的主人喵" in social.BOT_GROUP_INTRO_MESSAGE
    assert "你可以这样问我" not in social.BOT_GROUP_INTRO_MESSAGE
    assert "你现在有哪些风格" not in social.BOT_GROUP_INTRO_MESSAGE
    assert "菜单" not in social.BOT_GROUP_INTRO_MESSAGE
    assert "我是谁" not in social.BOT_GROUP_INTRO_MESSAGE
    assert "渲染 shapez 代码" not in social.BOT_GROUP_INTRO_MESSAGE


def test_social_group_increase_welcomes_new_member(monkeypatch) -> None:
    class FakeGroupIncrease:
        group_id = 1093545322
        user_id = 10001
        operator_id = 605738729

    monkeypatch.setattr(social, "GroupIncreaseNoticeEvent", FakeGroupIncrease)
    monkeypatch.setattr(social.random, "choice", lambda suffixes: "+=-1")
    bot = FakeBot(self_id="114514")

    asyncio.run(social.handle_group_increase(bot, FakeGroupIncrease()))

    assert bot.calls == [
        (
            "send_group_msg",
            {
                "group_id": 1093545322,
                "message": "[CQ:at,qq=10001] 欢迎大佬喵！群地位+=-1",
            },
        ),
    ]
