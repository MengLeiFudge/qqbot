from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.kun_service import KunBoss, KunService


def _write_legacy_kun_user(legacy_root: Path, qq: int, **overrides: object) -> None:
    payload = {
        "qq": qq,
        "season": 2,
        "openNewSeasonTip": False,
        "name": "與舆宝贝",
        "level": 7239,
        "atk": 7239,
        "def": 4343,
        "hp": 28956,
        "allSignInTimes": 24,
        "weekSignInTimes": 1,
        "lastSignInDate": "2025-01-14",
        "favorite": [0, 0, 0, 0, 0, 0, 0],
        "money": 355091,
        "gmk": 0,
        "xlk": 690,
        "ckk": 97,
        "tzq": 96,
        "resetTime": 0,
        "lastSetTime": 0,
        "mkTime": 1736157607000,
        "mkTimes": 1,
        "jjTime": 1736614224000,
        "jjTimes": 1,
        "tzTime": 1736157610000,
        "tzTimes": 1,
    }
    payload.update(overrides)
    user_dir = legacy_root / "user"
    user_dir.mkdir(parents=True, exist_ok=True)
    (user_dir / f"{qq}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_legacy_boss(legacy_root: Path, **overrides: object) -> None:
    payload = {
        "name": "旧鲲王",
        "level": 8888,
        "atk": 17776,
        "def": 9999,
        "hp": 66666666,
    }
    payload.update(overrides)
    legacy_root.mkdir(parents=True, exist_ok=True)
    (legacy_root / "boss.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (legacy_root / "nowSeason.txt").write_text("#legacy\n1=2\n", encoding="utf-8")


def test_migrate_legacy_data_imports_users_boss_and_now_season(tmp_path: Path) -> None:
    data_root = tmp_path / "run"
    service = KunService(data_root / "data" / "kun" / "users.json")
    legacy_root = tmp_path / "legacy" / "kun"

    _write_legacy_kun_user(legacy_root, 605738729)
    _write_legacy_kun_user(
        legacy_root,
        651228714,
        name="我爱学习",
        level=25858,
        money=228277,
        atk=25858,
        **{"def": 17550, "hp": 120000},
    )
    _write_legacy_boss(legacy_root)

    migrated = service.migrate_legacy_data(legacy_root)

    assert migrated == 2
    users_payload = json.loads((data_root / "data" / "kun" / "users.json").read_text(encoding="utf-8"))
    assert users_payload["605738729"]["name"] == "與舆宝贝"
    assert users_payload["605738729"]["level"] == 7239
    assert users_payload["605738729"]["money"] == 355091
    assert users_payload["605738729"]["xlk"] == 690
    assert users_payload["605738729"]["ckk"] == 97
    assert users_payload["605738729"]["tzq"] == 96
    assert users_payload["605738729"]["mkTime"] == 1736157607000
    assert users_payload["605738729"]["jjTime"] == 1736614224000
    assert users_payload["605738729"]["tzTime"] == 1736157610000
    assert json.loads((data_root / "data" / "kun" / "boss.json").read_text(encoding="utf-8"))["name"] == "旧鲲王"
    assert (data_root / "data" / "kun" / "nowSeason.txt").read_text(encoding="utf-8").strip().endswith("1=2")


def test_create_kun_user_uses_legacy_style_name_and_seed_fields(tmp_path: Path) -> None:
    service = KunService(tmp_path / "data" / "kun" / "users.json")

    user = service.ensure_user(605738729)
    payload = json.loads((tmp_path / "data" / "kun" / "users.json").read_text(encoding="utf-8"))["605738729"]

    assert user.name != "鲲729"
    assert 1 <= len(user.name) <= 4
    assert 100 <= user.level <= 2000
    assert user.atk == 1
    assert user.defense == 1
    assert user.hp == 1
    assert payload["gmk"] == 0
    assert payload["xlk"] == 0
    assert payload["ckk"] == 0
    assert payload["tzq"] == 0


def test_build_attribute_summary_matches_legacy_format(tmp_path: Path) -> None:
    service = KunService(tmp_path / "data" / "kun" / "users.json")
    user = service.ensure_user(10001)
    user.name = "阿鲲"
    user.level = 7239
    user.atk = 7239
    user.defense = 4343
    user.hp = 28956
    service._save()

    summary = service.build_attribute_summary(user, rank_index=1, total_users=3)

    assert "阿鲲正在到处游弋。" in summary
    assert "血量：28956（" in summary
    assert "攻击：7239（" in summary
    assert "防御：4343（" in summary
    assert "当前排名：1 / 3" in summary
    assert "超过了所有人！太强了鸭！" in summary
    assert "新赛季私聊提示：关闭" in summary


def test_mk_first_time_returns_legacy_intro_message(tmp_path: Path) -> None:
    service = KunService(tmp_path / "data" / "kun" / "users.json")

    message = service.mk(10001, now_millis=1_800_000_000_000, is_admin=False)

    assert "你孤身一人去无尽之海，发现一只小鲲崽遗弃在海岸边。" in message
    assert "决定抚养它成为最强的鲲王。" in message
    assert "只是这无尽之海非常广阔" in message


def test_sign_in_and_repeat_message_follow_legacy_copy(tmp_path: Path) -> None:
    service = KunService(tmp_path / "data" / "kun" / "users.json")
    user = service.ensure_user(10001)

    first = service.sign_in(user, "2026-04-21", "2026-04-21")
    second = service.sign_in(user, "2026-04-21", "2026-04-21")

    assert "共签到1次" in first
    assert "本周已签到1天" in first
    assert "获得666枚萌泪币！" in first
    assert "共签到1次" in second
    assert "本周已签到1天" in second
    assert "明天再来签到吧！" in second


def test_rename_kun_requires_card_with_legacy_message(tmp_path: Path) -> None:
    service = KunService(tmp_path / "data" / "kun" / "users.json")
    user = service.ensure_user(10001)
    user.name = "老名字"

    result = service.rename_kun(user, "新名字")

    assert result == "老名字摇了摇头，表示不喜欢这个名字！\n指令提示：【购买改名卡】"


def test_rename_kun_consumes_card_and_uses_legacy_success_copy(tmp_path: Path) -> None:
    service = KunService(tmp_path / "data" / "kun" / "users.json")
    user = service.ensure_user(10001)
    user.name = "老名字"
    user.rename_card = 1

    result = service.rename_kun(user, "新名字")

    assert result == "老名字高兴地绕着你转了两圈，看来它很喜欢这个名字！\n以后它就叫新名字啦！"
    assert user.name == "新名字"


def test_build_other_attribute_summary_requires_check_card(tmp_path: Path) -> None:
    service = KunService(tmp_path / "data" / "kun" / "users.json")
    viewer = service.ensure_user(10001)
    target = service.ensure_user(10002)

    result = service.build_other_attribute_summary(viewer, target)

    assert result == "TA的鲲似乎被一层迷雾笼罩....\n指令提示：【购买查看卡】"


def test_build_boss_summary_requires_check_card(tmp_path: Path) -> None:
    service = KunService(tmp_path / "data" / "kun" / "users.json")
    user = service.ensure_user(10001)

    result = service.build_boss_summary(user)

    assert result == "你没有查看卡，无权查看对方信息！"


def test_build_boss_summary_consumes_card_and_uses_legacy_fields(tmp_path: Path) -> None:
    service = KunService(tmp_path / "data" / "kun" / "users.json")
    user = service.ensure_user(10001)
    user.check_card = 1
    service.boss = KunBoss(name="旧鲲王", level=8888, atk=17776, defense=9999, hp=66666666)

    result = service.build_boss_summary(user)

    assert result == "Boss 旧鲲王\n攻击：17776\n防御：9999\n剩余血量：66666666"
    assert user.check_card == 0


def test_challenge_boss_requires_ticket(tmp_path: Path) -> None:
    service = KunService(tmp_path / "data" / "kun" / "users.json")
    user = service.ensure_user(10001)

    result = service.challenge_boss(user, now_millis=1_800_000_000_000, is_admin=False)

    assert result == "你还没挑战券呢！"


def test_buy_and_sell_item_match_legacy_copy(tmp_path: Path) -> None:
    service = KunService(tmp_path / "data" / "kun" / "users.json")
    user = service.ensure_user(10001)
    user.money = 20000

    buy = service.buy_item(user, "改名卡", 1)
    sell = service.sell_item(user, "改名卡", 1)

    assert buy == "成功购买改名卡×1！\n花费18888枚萌泪币！\n现有萌泪币：1112枚"
    assert sell == "成功出售改名卡×1！\n获得15110枚萌泪币！\n现有萌泪币：16222枚"


def test_level_rank_empty_uses_legacy_copy(tmp_path: Path) -> None:
    service = KunService(tmp_path / "data" / "kun" / "users.json")

    result = service.build_level_rank_lines(group_id=516286670)

    assert result == ["当前无人上榜！\n（摸鲲、进击均可上榜）"]


def test_level_rank_prefers_resolved_group_display_name(tmp_path: Path) -> None:
    service = KunService(tmp_path / "data" / "kun" / "users.json")
    user = service.ensure_user(10001)
    user.name = "阿鲲"
    user.level = 2000
    service._save()

    result = service.build_level_rank_lines(
        group_id=516286670,
        resolve_display_name=lambda group_id, qq: "本群名片" if group_id == 516286670 and qq == 10001 else str(qq),
    )

    assert "本群名片(10001)" in result[0]
    assert "10001(10001)" not in result[0]


def test_money_rank_falls_back_to_qq_number_when_no_nickname(tmp_path: Path) -> None:
    service = KunService(tmp_path / "data" / "kun" / "users.json")
    user = service.ensure_user(10001)
    user.name = "阿鲲"
    user.money = 9999
    service._save()

    result = service.build_money_rank_lines(
        group_id=516286670,
        resolve_display_name=lambda group_id, qq: str(qq),
    )

    assert result[0].endswith("10001")
    assert "10001(10001)" not in result[0]
