from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import threading
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from qqbot.features.ai.rightcodes_draw_client import (
    RIGHTCODES_DRAW_DEFAULT_MODEL,
    RIGHTCODES_DRAW_MODEL_ORDER,
    RIGHTCODES_DRAW_POINT_PRICE_MULTIPLIER,
    calculate_rightcodes_draw_model_points,
    format_rightcodes_draw_model_price,
)


RIGHTCODES_DRAW_FREE_DAILY_LIMIT = 1
_DRAW_POINTS_LOCK = threading.Lock()


@dataclass(frozen=True, slots=True)
class RightCodesDrawPointBalance:
    user_id: str
    points: int
    message_count: int
    free_available: bool
    date_key: str
    multiplier: int


@dataclass(frozen=True, slots=True)
class RightCodesDrawQuotaResult:
    allowed: bool
    user_id: str
    model: str
    cost_points: int
    balance_before: int
    balance_after: int
    multiplier: int
    price: str
    date_key: str
    used_free: bool = False
    free_limit: int = RIGHTCODES_DRAW_FREE_DAILY_LIMIT

    @property
    def used(self) -> int:
        return self.free_limit if self.used_free else 0

    @property
    def limit(self) -> int:
        return self.free_limit

    @property
    def remaining(self) -> int:
        return self.balance_after


class RightCodesDrawQuotaStore:
    def __init__(
        self,
        data_root: Path,
        *,
        multiplier: int = RIGHTCODES_DRAW_POINT_PRICE_MULTIPLIER,
    ) -> None:
        self.data_root = Path(data_root)
        self.multiplier = max(1, int(multiplier))
        self.path = self.data_root / "ai" / "draw_points.json"

    def record_group_message(self, user_id: int | str, *, amount: int = 1) -> int:
        user_key = str(user_id).strip()
        if not user_key or amount <= 0:
            return 0
        with _DRAW_POINTS_LOCK:
            payload = self._read()
            users = _get_users_payload(payload)
            user_payload = _get_user_payload(users, user_key)
            points = int(user_payload.get("points", 0) or 0) + int(amount)
            message_count = int(user_payload.get("message_count", 0) or 0) + int(amount)
            user_payload["points"] = points
            user_payload["message_count"] = message_count
            users[user_key] = user_payload
            payload["users"] = users
            self._write(payload)
            return points

    def get_balance(
        self,
        user_id: int | str,
        *,
        date_key: str | None = None,
    ) -> RightCodesDrawPointBalance:
        date_key = date_key or current_draw_quota_date_key()
        user_key = str(user_id).strip()
        if not user_key:
            return RightCodesDrawPointBalance(
                user_id="",
                points=0,
                message_count=0,
                free_available=False,
                date_key=date_key,
                multiplier=self.multiplier,
            )
        with _DRAW_POINTS_LOCK:
            payload = self._read()
            users = _get_users_payload(payload)
            user_payload = _get_user_payload(users, user_key)
        free_date = str(user_payload.get("free_gpt_image_2_date", "") or "")
        return RightCodesDrawPointBalance(
            user_id=user_key,
            points=int(user_payload.get("points", 0) or 0),
            message_count=int(user_payload.get("message_count", 0) or 0),
            free_available=free_date != date_key,
            date_key=date_key,
            multiplier=self.multiplier,
        )

    def reserve(
        self,
        user_id: int | str,
        *,
        model: str = RIGHTCODES_DRAW_DEFAULT_MODEL,
        date_key: str | None = None,
    ) -> RightCodesDrawQuotaResult:
        date_key = date_key or current_draw_quota_date_key()
        user_key = str(user_id).strip()
        cost_points = calculate_rightcodes_draw_model_points(model, multiplier=self.multiplier)
        price = format_rightcodes_draw_model_price(model)
        if not user_key:
            return RightCodesDrawQuotaResult(
                allowed=False,
                user_id="",
                model=model,
                cost_points=cost_points,
                balance_before=0,
                balance_after=0,
                multiplier=self.multiplier,
                price=price,
                date_key=date_key,
            )
        with _DRAW_POINTS_LOCK:
            payload = self._read()
            users = _get_users_payload(payload)
            user_payload = _get_user_payload(users, user_key)
            balance = int(user_payload.get("points", 0) or 0)
            free_date = str(user_payload.get("free_gpt_image_2_date", "") or "")
            if model == RIGHTCODES_DRAW_DEFAULT_MODEL and free_date != date_key:
                user_payload["free_gpt_image_2_date"] = date_key
                users[user_key] = user_payload
                payload["users"] = users
                self._write(payload)
                return RightCodesDrawQuotaResult(
                    allowed=True,
                    user_id=user_key,
                    model=model,
                    cost_points=0,
                    balance_before=balance,
                    balance_after=balance,
                    multiplier=self.multiplier,
                    price=price,
                    date_key=date_key,
                    used_free=True,
                )
            if balance < cost_points:
                return RightCodesDrawQuotaResult(
                    allowed=False,
                    user_id=user_key,
                    model=model,
                    cost_points=cost_points,
                    balance_before=balance,
                    balance_after=balance,
                    multiplier=self.multiplier,
                    price=price,
                    date_key=date_key,
                )
            user_payload["points"] = balance - cost_points
            users[user_key] = user_payload
            payload["users"] = users
            self._write(payload)
            return RightCodesDrawQuotaResult(
                allowed=True,
                user_id=user_key,
                model=model,
                cost_points=cost_points,
                balance_before=balance,
                balance_after=balance - cost_points,
                multiplier=self.multiplier,
                price=price,
                date_key=date_key,
            )

    def refund(self, reservation: RightCodesDrawQuotaResult) -> None:
        if not reservation.allowed or not reservation.user_id:
            return
        with _DRAW_POINTS_LOCK:
            payload = self._read()
            users = _get_users_payload(payload)
            user_payload = _get_user_payload(users, reservation.user_id)
            if reservation.used_free:
                if user_payload.get("free_gpt_image_2_date") == reservation.date_key:
                    user_payload.pop("free_gpt_image_2_date", None)
            elif reservation.cost_points > 0:
                points = int(user_payload.get("points", 0) or 0)
                user_payload["points"] = points + reservation.cost_points
            users[reservation.user_id] = user_payload
            payload["users"] = users
            self._write(payload)

    def _read(self) -> dict[str, object]:
        if not self.path.exists():
            return {"schema_version": 1, "users": {}}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {"schema_version": 1, "users": {}}
        raw.setdefault("schema_version", 1)
        raw.setdefault("users", {})
        return raw

    def _write(self, payload: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def format_rightcodes_draw_points_status(balance: RightCodesDrawPointBalance) -> str:
    free_status = (
        f"{RIGHTCODES_DRAW_DEFAULT_MODEL} 今日免费次数：可用"
        if balance.free_available
        else f"{RIGHTCODES_DRAW_DEFAULT_MODEL} 今日免费次数：已使用"
    )
    model_lines = [
        f"- {model}: {calculate_rightcodes_draw_model_points(model, multiplier=balance.multiplier)} 积分"
        for model in RIGHTCODES_DRAW_MODEL_ORDER
    ]
    return "\n".join(
        [
            f"当前生图积分：{balance.points}",
            f"全群累计消息数：{balance.message_count}",
            free_status,
            f"扣费倍率：价格 x {balance.multiplier}",
            "模型扣费：",
            *model_lines,
        ]
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


def _get_users_payload(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    raw = payload.get("users")
    if not isinstance(raw, dict):
        return {}
    users: dict[str, dict[str, object]] = {}
    for user_id, value in raw.items():
        if not str(user_id).strip() or not isinstance(value, dict):
            continue
        users[str(user_id)] = dict(value)
    return users


def _get_user_payload(
    users: dict[str, dict[str, object]],
    user_key: str,
) -> dict[str, object]:
    raw = users.get(user_key)
    if not isinstance(raw, dict):
        return {"points": 0, "message_count": 0}
    points = _safe_int(raw.get("points"))
    message_count = _safe_int(raw.get("message_count"))
    payload = dict(raw)
    payload["points"] = points
    payload["message_count"] = message_count
    return payload


def _safe_int(value: object) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0
