from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING
import json
import os
from pathlib import Path
import re
import threading
import time
from typing import Any, Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


RIGHTCODES_DRAW_BASE_URL = "https://www.right.codes/draw"
RIGHTCODES_DRAW_DEFAULT_MODEL = "gpt-image-2"
RIGHTCODES_DRAW_POINT_PRICE_MULTIPLIER = 1000
RIGHTCODES_DRAW_FREE_DAILY_LIMIT = 1
RIGHTCODES_DRAW_MODEL_ORDER = (
    "gpt-image-2",
    "gpt-image-2-vip",
    "nano-banana",
    "nano-banana-2",
    "nano-banana-pro",
)
RIGHTCODES_DRAW_MODELS = set(RIGHTCODES_DRAW_MODEL_ORDER)
RIGHTCODES_DRAW_MODEL_PRICES = {
    "gpt-image-2": Decimal("0.04"),
    "gpt-image-2-vip": Decimal("0.13"),
    "nano-banana": Decimal("0.14"),
    "nano-banana-2": Decimal("0.12"),
    "nano-banana-pro": Decimal("0.18"),
}
RIGHTCODES_DRAW_MODEL_DESCRIPTIONS = {
    "gpt-image-2": "OpenAI 最新的画图模型，特价版，支持分辨率：1K",
    "gpt-image-2-vip": "OpenAI 最新的画图模型，官方直连，支持分辨率：1K、2K、4K",
    "nano-banana": "由 gemini-2.5-flash-image 模型封装而来",
    "nano-banana-2": "nano banana 第二代绘图模型，综合效果远超上一代，支持分辨率：1K、2K、4K",
    "nano-banana-pro": "nano banana 第二代绘图模型，综合效果远超上一代，支持分辨率：1K、2K、4K",
}
FEATURE_MODE_ENV = "QQBOT_ASTRBOT_FEATURE_MODE"
FEATURE_MODE_DUAL = "dual"
FEATURE_MODE_FULL = "full"
FEATURE_MODES = {FEATURE_MODE_DUAL, FEATURE_MODE_FULL}
NONEBOT2_HOST = "127.0.0.1"
NONEBOT2_PORT = 8080
_DRAW_POINTS_LOCK = threading.Lock()
_DRAW_POINTS_QUERY_RE = re.compile(
    r"^(?:(?:查|查询|查看|看)(?:一下)?)?(?:我(?:的)?|当前)?(?:生图)?积分(?:余额|情况|多少)?$"
)
_DRAW_POINTS_ENGLISH_QUERY_RE = re.compile(r"^(?:balance|points?)$", re.IGNORECASE)
_DRAW_POINTS_MUTATION_RE = re.compile(
    r"(?:加|增加|扣|扣除|减|减少|改|修改|设置|设定|送|赠|赠送|充值|充).{0,16}积分"
    r"|积分.{0,16}(?:加|增加|扣|扣除|减|减少|改|修改|设置|设定|送|赠|赠送|充值|充)"
)


@dataclass(frozen=True, slots=True)
class RightCodesDrawRequest:
    prompt: str
    model: str = RIGHTCODES_DRAW_DEFAULT_MODEL
    image_urls: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RightCodesDrawResult:
    image_url: str
    total_seconds: float


@dataclass(frozen=True, slots=True)
class RightCodesDrawPointBalance:
    user_id: str
    points: int
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


@dataclass(frozen=True, slots=True)
class RightCodesConfig:
    feature_mode: str
    data_root: Path
    api_key: str
    point_multiplier: int
    draw_timeout_seconds: float


class RightCodesDrawTimeoutError(TimeoutError):
    def __init__(self, timeout_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds
        super().__init__(f"RightCodes 生图超过 {timeout_seconds:.0f} 秒未返回")


class AsyncDrawHttpClient(Protocol):
    async def post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> Any:
        ...


class RightCodesDrawClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = RIGHTCODES_DRAW_BASE_URL,
        timeout_seconds: float = 180.0,
        http_client: AsyncDrawHttpClient | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.http_client = http_client

    async def draw(self, request: RightCodesDrawRequest) -> RightCodesDrawResult:
        if not self.api_key:
            raise ValueError("缺少 RightCodes 生图 API Key")
        started = time.perf_counter()
        data = await self._post_json(
            f"{self.base_url}/v1/images/generations",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": request.model,
                "prompt": request.prompt,
                "image": list(request.image_urls),
                "size": "1024x1024",
                "response_format": "url",
            },
            timeout=self.timeout_seconds,
        )
        image_url = extract_image_url_from_object(data)
        if not image_url:
            raise RuntimeError("RightCodes 生图没有返回图片 URL")
        return RightCodesDrawResult(
            image_url=image_url,
            total_seconds=time.perf_counter() - started,
        )

    async def _post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> object:
        if self.http_client is not None:
            return await self.http_client.post_json(url, headers=headers, json=json, timeout=timeout)
        return await post_json(url, headers, json, timeout)


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
            users = get_users_payload(payload)
            user_payload = get_user_payload(users, user_key)
            points = int(user_payload.get("points", 0) or 0) + int(amount)
            user_payload["points"] = points
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
            return RightCodesDrawPointBalance("", 0, False, date_key, self.multiplier)
        with _DRAW_POINTS_LOCK:
            payload = self._read()
            users = get_users_payload(payload)
            user_payload = get_user_payload(users, user_key)
        free_date = str(user_payload.get("free_gpt_image_2_date", "") or "")
        return RightCodesDrawPointBalance(
            user_id=user_key,
            points=int(user_payload.get("points", 0) or 0),
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
            return RightCodesDrawQuotaResult(False, "", model, cost_points, 0, 0, self.multiplier, price, date_key)
        with _DRAW_POINTS_LOCK:
            payload = self._read()
            users = get_users_payload(payload)
            user_payload = get_user_payload(users, user_key)
            balance = int(user_payload.get("points", 0) or 0)
            free_date = str(user_payload.get("free_gpt_image_2_date", "") or "")
            if model == RIGHTCODES_DRAW_DEFAULT_MODEL and free_date != date_key:
                user_payload["free_gpt_image_2_date"] = date_key
                users[user_key] = user_payload
                payload["users"] = users
                self._write(payload)
                return RightCodesDrawQuotaResult(
                    True, user_key, model, 0, balance, balance, self.multiplier, price, date_key, True
                )
            if balance < cost_points:
                return RightCodesDrawQuotaResult(
                    False, user_key, model, cost_points, balance, balance, self.multiplier, price, date_key
                )
            user_payload["points"] = balance - cost_points
            users[user_key] = user_payload
            payload["users"] = users
            self._write(payload)
            return RightCodesDrawQuotaResult(
                True,
                user_key,
                model,
                cost_points,
                balance,
                balance - cost_points,
                self.multiplier,
                price,
                date_key,
            )

    def refund(self, reservation: RightCodesDrawQuotaResult) -> None:
        if not reservation.allowed or not reservation.user_id:
            return
        with _DRAW_POINTS_LOCK:
            payload = self._read()
            users = get_users_payload(payload)
            user_payload = get_user_payload(users, reservation.user_id)
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
        payload = normalize_draw_points_payload(payload)
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_rightcodes_config(config=None) -> RightCodesConfig:
    feature_mode = read_feature_mode(config)
    data_root_raw = get_config_value(config, "data_root", "")
    data_root = Path(str(data_root_raw)).expanduser() if str(data_root_raw or "").strip() else resolve_default_data_root()
    return RightCodesConfig(
        feature_mode=feature_mode,
        data_root=data_root,
        api_key=str(get_config_value(config, "api_key", "") or "").strip(),
        point_multiplier=max(1, safe_int(get_config_value(config, "point_multiplier", 1000), 1000)),
        draw_timeout_seconds=max(
            30.0,
            float(safe_int(get_config_value(config, "draw_timeout_seconds", 240), 240)),
        ),
    )


def read_feature_mode(config=None) -> str:
    raw = os.environ.get(FEATURE_MODE_ENV, "").strip().lower()
    if not raw and config is not None:
        try:
            raw = str(config.get("feature_mode", "") or "").strip().lower()
        except Exception:
            raw = ""
    if raw in FEATURE_MODES:
        return FEATURE_MODE_FULL
    return FEATURE_MODE_FULL


def should_record_passive_group_points(
    *,
    feature_mode: str,
    nonebot2_online: bool,
) -> bool:
    return True


def parse_rightcodes_draw_command(text: str) -> RightCodesDrawRequest | None:
    normalized = text.strip()
    rest = extract_rightcodes_draw_prompt(normalized)
    if rest is None or not rest:
        return None
    model = RIGHTCODES_DRAW_DEFAULT_MODEL
    prompt = rest
    bracket_match = re.match(r"^\[([^\]]+)\]\s*(.+)$", rest)
    if bracket_match is not None:
        candidate = bracket_match.group(1).strip()
        if candidate in RIGHTCODES_DRAW_MODELS:
            model = candidate
            prompt = bracket_match.group(2).strip()
        else:
            return RightCodesDrawRequest(prompt=rest, model=model)
    else:
        parts = rest.split(maxsplit=1)
        if len(parts) == 2 and parts[0] in RIGHTCODES_DRAW_MODELS:
            model = parts[0]
            prompt = parts[1].strip()
    if not prompt:
        return None
    return RightCodesDrawRequest(prompt=prompt, model=model)


def looks_like_rightcodes_draw_invocation(text: str) -> bool:
    return extract_rightcodes_draw_prompt(text.strip()) is not None


def looks_like_rightcodes_draw_suggestion(text: str) -> bool:
    return extract_natural_draw_prompt(text.strip()) is not None


def extract_rightcodes_draw_prompt(text: str) -> str | None:
    command_match = re.match(r"^(?:棉花糖|棉花)\s*生图([\s\S]*)$", text)
    if command_match is not None:
        return command_match.group(1).strip()
    return None


def extract_natural_draw_prompt(text: str) -> str | None:
    natural_match = re.match(r"^生成\s*(.+?)(?:的)?(?:图片|图像|图)\s*$", text)
    if natural_match is not None:
        return natural_match.group(1).strip()
    return None


def format_rightcodes_draw_suggestion_message() -> str:
    return "你是不是想用生图功能？指令是：棉花糖生图 提示词。这个功能会消耗生图积分。"


def looks_like_rightcodes_draw_command(text: str) -> bool:
    return parse_rightcodes_draw_command(text) is not None


def format_rightcodes_draw_missing_prompt_message() -> str:
    return "生图需要文字提示词。用法：棉花糖生图 提示词；也可以写：棉花糖生图 模型名 提示词。"


def looks_like_rightcodes_draw_help_command(text: str) -> bool:
    normalized = re.sub(r"\s+", "", text.strip())
    return normalized in {
        "生图模型说明",
        "生图模型",
        "生图价格",
        "画图模型说明",
        "画图模型",
        "画图价格",
        "棉花糖生图模型说明",
        "棉花糖生图模型",
        "棉花糖生图价格",
        "棉花生图模型说明",
        "棉花生图模型",
        "棉花生图价格",
    }


def looks_like_rightcodes_draw_points_query(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    if _DRAW_POINTS_ENGLISH_QUERY_RE.fullmatch(normalized):
        return True
    compact = re.sub(r"\s+", "", normalized)
    return _DRAW_POINTS_QUERY_RE.fullmatch(compact) is not None


def looks_like_rightcodes_draw_points_mutation_request(text: str) -> bool:
    compact = re.sub(r"\s+", "", text.strip())
    if not compact or "积分" not in compact:
        return False
    return _DRAW_POINTS_MUTATION_RE.search(compact) is not None


def format_rightcodes_draw_model_help() -> str:
    lines = ["棉花糖现在支持这些生图模型喵："]
    for model in RIGHTCODES_DRAW_MODEL_ORDER:
        description = RIGHTCODES_DRAW_MODEL_DESCRIPTIONS[model]
        price = format_rightcodes_draw_model_price(model)
        default_mark = "（默认）" if model == RIGHTCODES_DRAW_DEFAULT_MODEL else ""
        free_mark = "；每天首张免费" if model == RIGHTCODES_DRAW_DEFAULT_MODEL else ""
        lines.append(
            f"- {model}{default_mark}：${price}/张"
            f"（{calculate_rightcodes_draw_model_points(model)} 积分）{free_mark}。{description}"
        )
    lines.extend(
        [
            "",
            "用法：",
            "棉花糖生图 [模型名] 提示词",
            "棉花糖生图 模型名 提示词",
            "不写模型时默认使用 gpt-image-2。",
        ]
    )
    return "\n".join(lines)


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
            free_status,
            f"扣费倍率：价格 x {balance.multiplier}",
            "模型扣费：",
            *model_lines,
        ]
    )


def format_rightcodes_draw_points_mutation_denied() -> str:
    return "生图积分只能通过群消息自动累计，并在生图时自动扣除；普通聊天不能手动加分或改分。"


def format_draw_start_message(quota: RightCodesDrawQuotaResult) -> str:
    if quota.used_free:
        return (
            "收到，棉花糖开始生图任务啦！"
            f"{quota.model} 今天第 1 张免费，当前积分 {quota.balance_after}。"
        )
    return (
        "收到，棉花糖开始生图任务啦！"
        f"本次使用 {quota.model}，扣 {quota.cost_points} 积分，"
        f"剩余 {quota.balance_after} 积分。"
    )


def format_draw_quota_exceeded_message(quota: RightCodesDrawQuotaResult) -> str:
    return (
        f"积分不够啦：{quota.model} 需要 {quota.cost_points} 积分"
        f"（价格 ${quota.price} x 倍率 {quota.multiplier}），"
        f"你现在有 {quota.balance_before} 积分。"
        "gpt-image-2 每天第 1 张免费。"
    )


def format_rightcodes_draw_success(
    result: RightCodesDrawResult,
    *,
    model: str,
    image_count: int = 1,
) -> str:
    return (
        "✨ 生成成功！\n"
        f"📊 耗时: {result.total_seconds:.2f}s\n"
        f"🖼️ 数量: {image_count}张\n"
        f"🤖 模型: {model}"
    )


def format_rightcodes_draw_failure(exc: Exception) -> str:
    return f"❌ 生成失败: {extract_rightcodes_draw_error_message(exc)}"


def format_rightcodes_draw_timeout(timeout_seconds: float) -> str:
    return (
        f"❌ 生成失败: RightCodes 生图超过 {timeout_seconds:.0f} 秒还没返回，"
        "本次扣除的积分或免费次数已退回。"
    )


def extract_rightcodes_draw_error_message(exc: Exception) -> str:
    if isinstance(exc, RightCodesDrawTimeoutError):
        return f"RightCodes 生图超过 {exc.timeout_seconds:.0f} 秒未返回"
    if isinstance(exc, TimeoutError):
        return "RightCodes 生图请求超时"
    if isinstance(exc, HTTPError):
        detail = read_http_error_detail(exc)
        return detail or f"上游返回 HTTP {exc.code}"
    message = str(exc).strip()
    return message or type(exc).__name__


def calculate_rightcodes_draw_model_points(
    model: str,
    *,
    multiplier: int = RIGHTCODES_DRAW_POINT_PRICE_MULTIPLIER,
) -> int:
    points = get_rightcodes_draw_model_price(model) * Decimal(str(multiplier))
    return int(points.to_integral_value(rounding=ROUND_CEILING))


def get_rightcodes_draw_model_price(model: str) -> Decimal:
    return RIGHTCODES_DRAW_MODEL_PRICES.get(model, RIGHTCODES_DRAW_MODEL_PRICES[RIGHTCODES_DRAW_DEFAULT_MODEL])


def format_rightcodes_draw_model_price(model: str) -> str:
    return f"{get_rightcodes_draw_model_price(model):.2f}"


async def post_json(
    url: str,
    headers: dict[str, str],
    payload: dict[str, object],
    timeout: float,
) -> object:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=body, headers=headers, method="POST")
    return await run_urlopen_json(request, timeout)


async def run_urlopen_json(request: Request, timeout: float) -> object:
    def read_response() -> object:
        with urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
            if status >= 400:
                raise RuntimeError(f"RightCodes draw request failed: {status}")
            body = response.read().decode("utf-8")
        return json.loads(body)

    return await asyncio.to_thread(read_response)


def read_http_error_detail(exc: HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:
        return ""
    if not body:
        return ""
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return body[:200]
    for path in (("error", "message"), ("message",), ("detail",)):
        value: object = data
        for key in path:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return body[:200]


def extract_image_url_from_object(data: object) -> str:
    if isinstance(data, dict):
        value = data.get("b64_json")
        if isinstance(value, str) and value.strip():
            return f"data:image/png;base64,{value.strip()}"
        value = data.get("url")
        if isinstance(value, str):
            extracted = extract_image_url(value)
            if extracted:
                return extracted
        for child in data.values():
            extracted = extract_image_url_from_object(child)
            if extracted:
                return extracted
    elif isinstance(data, list):
        for item in data:
            extracted = extract_image_url_from_object(item)
            if extracted:
                return extracted
    return ""


def extract_image_url(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith(("http://", "https://", "data:image/")):
        return stripped
    match = re.search(r"(https?://\S+)", stripped)
    if match:
        return match.group(1).rstrip("，,。)")
    return ""


def current_draw_quota_date_key() -> str:
    return datetime.now(resolve_zone("Asia/Shanghai")).strftime("%Y-%m-%d")


def resolve_zone(timezone_name: str):
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        if timezone_name == "Asia/Shanghai":
            return timezone(timedelta(hours=8), name=timezone_name)
        if timezone_name == "UTC":
            return timezone.utc
        return datetime.now().astimezone().tzinfo or timezone.utc


def resolve_default_data_root() -> Path:
    return resolve_workspace_root() / "data" / "nonebot2" / "run"


def resolve_workspace_root() -> Path:
    astrbot_root = Path(os.environ.get("ASTRBOT_ROOT", "")).resolve()
    if astrbot_root.name == "astrbot" and astrbot_root.parent.name == "data":
        return astrbot_root.parent.parent
    current = Path.cwd().resolve()
    if current.name == "qqbot":
        return current
    if current.name == "astrbot" and current.parent.name == "data":
        return current.parent.parent
    for parent in current.parents:
        if (parent / "astrbot-local-plugins").is_dir() and (parent / "nonebot2").is_dir():
            return parent
    return current


def get_users_payload(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    raw = payload.get("users")
    if not isinstance(raw, dict):
        return {}
    users: dict[str, dict[str, object]] = {}
    for user_id, value in raw.items():
        if str(user_id).strip() and isinstance(value, dict):
            users[str(user_id)] = dict(value)
    return users


def get_user_payload(users: dict[str, dict[str, object]], user_key: str) -> dict[str, object]:
    raw = users.get(user_key)
    if not isinstance(raw, dict):
        return {"points": 0}
    payload: dict[str, object] = {"points": safe_int(raw.get("points"), 0)}
    free_date = str(raw.get("free_gpt_image_2_date", "") or "").strip()
    if free_date:
        payload["free_gpt_image_2_date"] = free_date
    return payload


def normalize_draw_points_payload(payload: dict[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {
        "schema_version": max(1, safe_int(payload.get("schema_version"), 1)),
        "users": {},
    }
    users: dict[str, dict[str, object]] = {}
    for user_id, raw_user in get_users_payload(payload).items():
        users[user_id] = get_user_payload({user_id: raw_user}, user_id)
    normalized["users"] = users
    return normalized


def get_config_value(config, key: str, default):
    if config is None:
        return default
    try:
        return config.get(key, default)
    except Exception:
        return default


def safe_int(value: object, default: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default
