from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LoliconMode(Enum):
    NON_R18 = 0
    R18 = 1
    MIXED = 2


@dataclass(frozen=True, slots=True)
class LoliconCommand:
    mode: LoliconMode
    num: int
    tags: list[str]


@dataclass(frozen=True, slots=True)
class LoliconImageItem:
    title: str
    pid: int
    author: str
    uid: int
    url: str
    r18: bool


def parse_lolicon_command(text: str) -> LoliconCommand | None:
    normalized = text.strip()
    if normalized.startswith("来点"):
        normalized = normalized[2:].strip()
    if len(normalized) < 2:
        return None

    prefix = normalized[:2]
    if prefix == "美图":
        mode = LoliconMode.NON_R18
    elif prefix in {"色图", "涩图", "蛇图"}:
        mode = LoliconMode.R18
    elif prefix == "混合":
        mode = LoliconMode.MIXED
    else:
        return None

    payload = normalized[2:].strip()
    if not payload:
        return LoliconCommand(mode=mode, num=1, tags=[])
    if payload.isdigit():
        return LoliconCommand(mode=mode, num=int(payload), tags=[])

    parts = payload.split()
    num = 5
    if parts[-1].isdigit():
        num = int(parts[-1])
        parts = parts[:-1]
    return LoliconCommand(mode=mode, num=num, tags=parts)


def parse_lolicon_response(payload: dict) -> list[LoliconImageItem]:
    if payload.get("error"):
        return []
    items: list[LoliconImageItem] = []
    for raw in payload.get("data", []):
        items.append(
            LoliconImageItem(
                title=raw["title"],
                pid=int(raw["pid"]),
                author=raw["author"],
                uid=int(raw["uid"]),
                url=raw["urls"]["original"],
                r18=bool(raw.get("r18", False)),
            )
        )
    return items
