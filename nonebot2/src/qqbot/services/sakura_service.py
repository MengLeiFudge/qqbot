from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from pathlib import Path


@dataclass
class SakuraPlayer:
    qq: int
    name: str
    level: int = 1
    exp: int = 0
    max_exp: int = 100
    hp: int = 100
    max_hp: int = 100
    mp: int = 100
    max_mp: int = 100
    money: int = 0
    phy_atk: int = 20
    mag_atk: int = 20
    phy_def: int = 5
    mag_def: int = 5
    speed: int = 100
    points: int = 0
    strength: int = 0
    intelligence: int = 0
    constitution: int = 0
    agility: int = 0
    charm: int = 0


class SakuraService:
    def __init__(self, file_path: Path) -> None:
        self.file_path = Path(file_path)
        self.players = self._load()

    def register_player(self, qq: int, name: str) -> SakuraPlayer:
        player = SakuraPlayer(qq=qq, name=name)
        self.players[str(qq)] = player
        self._save()
        return player

    def get_player(self, qq: int) -> SakuraPlayer | None:
        return self.players.get(str(qq))

    def rename_player(self, player: SakuraPlayer, new_name: str) -> str:
        player.name = new_name
        self._save()
        return f"已更改昵称为{new_name}"

    def add_exp(self, player: SakuraPlayer, amount: int) -> str:
        player.exp += amount
        while player.exp >= player.max_exp:
            player.exp -= player.max_exp
            player.level += 1
            player.max_exp += 100
            player.max_hp = player.hp = player.level * 100
            player.max_mp = player.mp = player.level * 100
            player.points += 5
        self._save()
        return f"获得经验{amount}"

    def add_money(self, player: SakuraPlayer, amount: int) -> str:
        player.money += amount
        self._save()
        return f"获得樱币{amount}"

    def add_points(self, player: SakuraPlayer, point_type: str, amount: int) -> str:
        if player.points < amount:
            return "剩余可分配点数不足"
        mapping = {
            "力量": "strength",
            "智力": "intelligence",
            "体质": "constitution",
            "敏捷": "agility",
            "魅力": "charm",
        }
        field = mapping[point_type]
        setattr(player, field, getattr(player, field) + amount)
        player.points -= amount
        self._save()
        return f"已为{point_type}加点{amount}"

    def reset_player(self, player: SakuraPlayer) -> str:
        player.hp = player.max_hp
        player.mp = player.max_mp
        self._save()
        return "状态已恢复"

    def build_profile_summary(self, player: SakuraPlayer) -> str:
        return (
            f"Lv.{player.level} {player.name}\n"
            f"生命：{player.hp}/{player.max_hp}\n"
            f"魔力：{player.mp}/{player.max_mp}\n"
            f"经验：{player.exp}/{player.max_exp}\n"
            f"樱币：{player.money}"
        )

    def _load(self) -> dict[str, SakuraPlayer]:
        if not self.file_path.exists():
            return {}
        raw = json.loads(self.file_path.read_text(encoding="utf-8"))
        return {key: SakuraPlayer(**value) for key, value in raw.items()}

    def _save(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {key: asdict(value) for key, value in self.players.items()}
        self.file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
