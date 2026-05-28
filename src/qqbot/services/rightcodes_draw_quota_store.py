from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


RIGHTCODES_DRAW_DAILY_LIMIT = 10


@dataclass(frozen=True, slots=True)
class RightCodesDrawQuotaResult:
    allowed: bool
    used: int
    limit: int

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)


class RightCodesDrawQuotaStore:
    def __init__(
        self,
        data_root: Path,
        *,
        daily_limit: int = RIGHTCODES_DRAW_DAILY_LIMIT,
    ) -> None:
        self.data_root = Path(data_root)
        self.daily_limit = daily_limit
        self.path = self.data_root / "ai" / "draw_quota.json"

    def reserve(self, user_id: int | str, *, date_key: str | None = None) -> RightCodesDrawQuotaResult:
        date_key = date_key or current_draw_quota_date_key()
        user_key = str(user_id).strip()
        payload = self._read()
        day_payload = _get_day_payload(payload, date_key)
        used = int(day_payload.get(user_key, 0) or 0)
        if used >= self.daily_limit:
            return RightCodesDrawQuotaResult(False, used, self.daily_limit)
        used += 1
        day_payload[user_key] = used
        payload[date_key] = day_payload
        self._write(payload)
        return RightCodesDrawQuotaResult(True, used, self.daily_limit)

    def refund(self, user_id: int | str, *, date_key: str | None = None) -> None:
        date_key = date_key or current_draw_quota_date_key()
        user_key = str(user_id).strip()
        payload = self._read()
        day_payload = _get_day_payload(payload, date_key)
        used = int(day_payload.get(user_key, 0) or 0)
        if used <= 0:
            return
        if used == 1:
            day_payload.pop(user_key, None)
        else:
            day_payload[user_key] = used - 1
        payload[date_key] = day_payload
        self._write(payload)

    def _read(self) -> dict[str, object]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, payload: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def current_draw_quota_date_key() -> str:
    return datetime.now(_resolve_zone("Asia/Shanghai")).strftime("%Y-%m-%d")


def _resolve_zone(timezone_name: str):
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        if timezone_name == "Asia/Shanghai":
            return timezone(timedelta(hours=8), name=timezone_name)
        if timezone_name == "UTC":
            return timezone.utc
        return datetime.now().astimezone().tzinfo or timezone.utc


def _get_day_payload(payload: dict[str, object], date_key: str) -> dict[str, int]:
    raw = payload.get(date_key)
    if not isinstance(raw, dict):
        return {}
    return {
        str(user_id): int(count)
        for user_id, count in raw.items()
        if str(user_id).strip() and str(count).isdigit()
    }
