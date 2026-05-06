from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
import json
from pathlib import Path

from qqbot.config import load_settings


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
        raw = json.loads(self.file_path.read_text(encoding="utf-8"))
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
        self.file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@lru_cache(maxsize=1)
def get_group_nick_store() -> GroupNickStore:
    settings = load_settings()
    return GroupNickStore(settings.data_root / "settings" / "group_nick.json")
