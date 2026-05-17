from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from json import JSONDecodeError
from pathlib import Path
import re

from qqbot.config import load_settings
from qqbot.services.json_file_store import atomic_write_json


@dataclass(slots=True)
class GroupNickRecord:
    card: str = ""
    nickname: str = ""
    updated_at: int = 0


class GroupNickStore:
    def __init__(self, file_path: Path) -> None:
        self.file_path = Path(file_path)
        self.records = self._load()

    def record_group_sender(
        self,
        group_id: int,
        qq: int,
        card: str,
        nickname: str,
        updated_at: int,
    ) -> None:
        card = card.strip()
        nickname = nickname.strip()
        if not card and not nickname:
            return

        group_key = str(group_id)
        qq_key = str(qq)
        group_records = self.records.setdefault(group_key, {})
        existing = group_records.get(qq_key)
        if existing is not None and updated_at < existing.updated_at:
            return

        group_records[qq_key] = GroupNickRecord(card=card, nickname=nickname, updated_at=updated_at)
        self._save()

    def merge_legacy_nickname(self, group_id: int, qq: int, nickname: str) -> None:
        nickname = nickname.strip()
        if not nickname:
            return

        group_key = str(group_id)
        qq_key = str(qq)
        group_records = self.records.setdefault(group_key, {})
        existing = group_records.get(qq_key)
        if existing is not None and self._pick_best_name(existing):
            return

        group_records[qq_key] = GroupNickRecord(card="", nickname=nickname, updated_at=0)
        self._save()

    def resolve_display_name(self, group_id: int, qq: int) -> str:
        group_key = str(group_id)
        qq_key = str(qq)

        current_group = self.records.get(group_key, {})
        current_record = current_group.get(qq_key)
        current_name = self._pick_best_name(current_record)
        if current_name:
            return current_name

        latest_record: GroupNickRecord | None = None
        for other_group_id, group_records in self.records.items():
            if other_group_id == group_key:
                continue
            candidate = group_records.get(qq_key)
            if candidate is None:
                continue
            if not self._pick_best_name(candidate):
                continue
            if latest_record is None or candidate.updated_at > latest_record.updated_at:
                latest_record = candidate

        if latest_record is not None:
            latest_name = self._pick_best_name(latest_record)
            if latest_name:
                return latest_name
        return str(qq)

    def resolve_call_name(self, group_id: int, qq: int) -> str:
        display_name = self.resolve_display_name(group_id, qq)
        if display_name == str(qq):
            return display_name
        return normalize_call_name(display_name) or display_name

    def build_alias_terms(self, group_id: int | str, query: str) -> tuple[str, ...]:
        query = query.strip()
        if not query:
            return ()

        terms: list[str] = []
        group_records = self.records.get(str(group_id), {})
        for qq, record in group_records.items():
            aliases = tuple(item for item in (qq, record.card, record.nickname) if item)
            if not any(alias in query for alias in aliases):
                continue
            terms.extend(aliases)
        return tuple(dict.fromkeys(terms))

    def remove_group(self, group_id: int | str) -> bool:
        removed = self.records.pop(str(group_id), None) is not None
        if removed:
            self._save()
        return removed

    def _pick_best_name(self, record: GroupNickRecord | None) -> str:
        if record is None:
            return ""
        return record.card or record.nickname

    def _load(self) -> dict[str, dict[str, GroupNickRecord]]:
        if not self.file_path.exists():
            return {}
        try:
            raw = json.loads(self.file_path.read_text(encoding="utf-8"))
        except JSONDecodeError:
            return {}
        if not isinstance(raw, dict):
            return {}
        return {
            str(group_id): {
                str(qq): GroupNickRecord(
                    card=str(payload.get("card", "")),
                    nickname=str(payload.get("nickname", "")),
                    updated_at=int(payload.get("updated_at", 0)),
                )
                for qq, payload in group_payload.items()
            }
            for group_id, group_payload in raw.items()
        }

    def _save(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            group_id: {
                qq: asdict(record)
                for qq, record in group_payload.items()
            }
            for group_id, group_payload in self.records.items()
        }
        atomic_write_json(self.file_path, payload)


def get_group_nick_store() -> GroupNickStore:
    settings = load_settings()
    return GroupNickStore(settings.data_root / "settings" / "group_nick.json")


def normalize_call_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        return ""

    cleaned = re.sub(r"[\u2066-\u2069]", "", cleaned)
    cleaned = re.sub(r"^[^A-Za-z0-9_\u4e00-\u9fff]+", "", cleaned)
    cleaned = re.split(r"[:：]", cleaned, maxsplit=1)[0].strip()
    cleaned = re.sub(r"^[^A-Za-z0-9_\u4e00-\u9fff]+", "", cleaned)
    cleaned = re.sub(r"[\[\(（【].*?[\]\)）】]$", "", cleaned).strip()
    return cleaned
