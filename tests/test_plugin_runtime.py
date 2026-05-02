from pathlib import Path
import sys
import asyncio
import re
from types import SimpleNamespace

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


def test_reread_feature_binding_points_to_feature_1() -> None:
    feature = reread.get_reread_feature()

    assert feature is not None
    assert feature.index == 1
    assert feature.name == "随机复读"


def test_thunder_feature_binding_points_to_feature_2() -> None:
    feature = thunder.get_thunder_feature()

    assert feature is not None
    assert feature.index == 2
    assert feature.name == "随机禁言"


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


def test_arc_guess_answer_matchers_require_enabled_active_session(monkeypatch) -> None:
    class FakeGroupEvent:
        group_id = 516286670

        def __init__(self, text: str) -> None:
            self.text = text

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

    assert re.match(pattern, "菜单13") is not None
    assert re.match(pattern, "菜单arc") is not None
    assert re.match(pattern, "菜单arcaea") is not None


class FakeBot:
    def __init__(self, self_id: str) -> None:
        self.self_id = self_id
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def call_api(self, api: str, **data: object) -> None:
        self.calls.append((api, data))


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
    bot = OrderedBot(self_id="114514")
    event = SimpleNamespace(group_id=2333, user_id=10001, target_id=114514)

    asyncio.run(social.handle_poke(bot, event))

    assert [api for api, _ in bot.calls] == [
        "send_group_msg",
        "send_group_msg",
        "group_poke",
        "send_group_msg",
        "group_poke",
    ]
    assert bot.calls[2][1] == {"group_id": "2333", "user_id": "10001"}
    assert bot.calls[4][1] == {"group_id": "2333", "user_id": "10001"}
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
    bot = FakeBot(self_id="114514")
    event = SimpleNamespace(group_id=None, user_id=10001, target_id=114514)

    asyncio.run(social.handle_poke(bot, event))

    assert [api for api, _ in bot.calls] == ["send_private_msg", "send_private_msg", "friend_poke"]
    assert bot.calls[2][1] == {"user_id": "10001"}
