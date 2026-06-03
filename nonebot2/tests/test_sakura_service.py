from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.sakura_service import SakuraService


def test_register_and_profile_summary(tmp_path: Path) -> None:
    service = SakuraService(tmp_path / "data" / "sakura" / "players.json")
    player = service.register_player(10001, "角色A")

    summary = service.build_profile_summary(player)

    assert player.name == "角色A"
    assert "Lv." in summary
    assert "角色A" in summary


def test_rename_and_add_resources(tmp_path: Path) -> None:
    service = SakuraService(tmp_path / "data" / "sakura" / "players.json")
    player = service.register_player(10001, "角色A")

    rename = service.rename_player(player, "角色B")
    exp_result = service.add_exp(player, 500)
    money_result = service.add_money(player, 888)

    assert "已更改昵称为角色B" in rename
    assert "获得经验" in exp_result
    assert "获得樱币" in money_result


def test_add_points_and_reset(tmp_path: Path) -> None:
    service = SakuraService(tmp_path / "data" / "sakura" / "players.json")
    player = service.register_player(10001, "角色A")
    player.points = 10

    result = service.add_points(player, "力量", 5)
    reset = service.reset_player(player)

    assert "已为力量加点5" in result
    assert "状态已恢复" in reset
