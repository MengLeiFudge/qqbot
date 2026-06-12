from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from typing import Any, Protocol
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SUB2API_DEFAULT_ACCOUNT_NAME = "Pro"
SUB2API_DEFAULT_TIMEOUT_SECONDS = 90.0
SUB2API_DEFAULT_REFRESH_INTERVAL_SECONDS = 300.0
SUB2API_USAGE_CACHE_TTL_SECONDS = 60.0
SUB2API_QUERY_RE = re.compile(r"^用量$", re.IGNORECASE)
SUB2API_USAGE_ALERT_THRESHOLDS = (80, 90, 95)
SUB2API_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


@dataclass(frozen=True, slots=True)
class Sub2APIConfig:
    base_url: str
    admin_api_key: str
    default_account_name: str
    timeout_seconds: float
    refresh_interval_seconds: float
    alert_group_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Sub2APICommand:
    account_name: str


@dataclass(frozen=True, slots=True)
class Sub2APIWindowStats:
    requests: int = 0
    tokens: int = 0
    cost: float = 0.0
    user_cost: float | None = None


@dataclass(frozen=True, slots=True)
class Sub2APIUsageWindow:
    utilization: float | None = None
    resets_at: str = ""
    remaining_seconds: int | None = None
    window_stats: Sub2APIWindowStats | None = None


@dataclass(frozen=True, slots=True)
class Sub2APIAccountUsage:
    account_id: int
    name: str
    platform: str = ""
    account_type: str = ""
    status: str = ""
    current_concurrency: int | None = None
    last_used_at: str = ""
    source: str = ""
    updated_at: str = ""
    five_hour: Sub2APIUsageWindow | None = None
    seven_day: Sub2APIUsageWindow | None = None
    error: str = ""


@dataclass(frozen=True, slots=True)
class Sub2APIUsageAlert:
    usage: Sub2APIAccountUsage
    threshold: int
    utilization: float


class Sub2APIUsageCache:
    def __init__(self, *, ttl_seconds: float = SUB2API_USAGE_CACHE_TTL_SECONDS) -> None:
        self.ttl_seconds = max(0.0, float(ttl_seconds))
        self._items: dict[str, tuple[float, list[Sub2APIAccountUsage]]] = {}

    def get(self, account_name: str, *, now: float) -> list[Sub2APIAccountUsage] | None:
        return self.get_fresh(account_name, now=now)

    def get_fresh(self, account_name: str, *, now: float) -> list[Sub2APIAccountUsage] | None:
        cache_key = normalize_cache_key(account_name)
        if not cache_key:
            return None
        cached = self._items.get(cache_key)
        if cached is None:
            return None
        cached_at, usage = cached
        if now - cached_at >= self.ttl_seconds:
            return None
        return usage

    def get_latest(self, account_name: str) -> list[Sub2APIAccountUsage] | None:
        cache_key = normalize_cache_key(account_name)
        if not cache_key:
            return None
        cached = self._items.get(cache_key)
        if cached is None:
            return None
        return cached[1]

    def set(self, account_name: str, usage: list[Sub2APIAccountUsage], *, now: float) -> None:
        cache_key = normalize_cache_key(account_name)
        if cache_key:
            self._items[cache_key] = (now, usage)


class AsyncSub2APIHttpClient(Protocol):
    async def get_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
    ) -> Any:
        ...


def load_sub2api_config(config: object) -> Sub2APIConfig:
    return Sub2APIConfig(
        base_url=str(get_config_value(config, "sub2api_base_url", "") or "").strip().rstrip("/"),
        admin_api_key=str(get_config_value(config, "sub2api_admin_api_key", "") or "").strip(),
        default_account_name=str(
            get_config_value(config, "sub2api_default_account_name", SUB2API_DEFAULT_ACCOUNT_NAME)
            or SUB2API_DEFAULT_ACCOUNT_NAME
        ).strip()
        or SUB2API_DEFAULT_ACCOUNT_NAME,
        timeout_seconds=float(get_config_value(config, "sub2api_timeout_seconds", SUB2API_DEFAULT_TIMEOUT_SECONDS) or SUB2API_DEFAULT_TIMEOUT_SECONDS),
        refresh_interval_seconds=max(
            60.0,
            float(
                get_config_value(
                    config,
                    "sub2api_refresh_interval_seconds",
                    SUB2API_DEFAULT_REFRESH_INTERVAL_SECONDS,
                )
                or SUB2API_DEFAULT_REFRESH_INTERVAL_SECONDS
            ),
        ),
        alert_group_ids=parse_sub2api_group_ids(get_config_value(config, "sub2api_alert_group_ids", "")),
    )


def get_config_value(config: object, key: str, default: object = None) -> object:
    if config is None:
        return default
    if isinstance(config, dict):
        return config.get(key, default)
    getter = getattr(config, "get", None)
    if callable(getter):
        try:
            return getter(key, default)
        except TypeError:
            value = getter(key)
            return default if value is None else value
    return getattr(config, key, default)


def parse_sub2api_usage_command(text: str, *, default_account_name: str = SUB2API_DEFAULT_ACCOUNT_NAME) -> Sub2APICommand | None:
    normalized = normalize_command_text(text)
    if not normalized:
        return None
    if SUB2API_QUERY_RE.match(normalized):
        return Sub2APICommand(account_name=default_account_name)
    return None


def normalize_command_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def normalize_cache_key(account_name: str) -> str:
    return str(account_name or "").strip().casefold()


def looks_like_sub2api_usage_command(text: str, *, default_account_name: str = SUB2API_DEFAULT_ACCOUNT_NAME) -> bool:
    return parse_sub2api_usage_command(text, default_account_name=default_account_name) is not None


def parse_sub2api_group_ids(raw: object) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        values = raw.replace("，", ",").split(",")
    else:
        try:
            values = list(raw)
        except TypeError:
            values = [raw]
    group_ids = []
    seen = set()
    for value in values:
        group_id = str(value or "").strip()
        if not group_id or not group_id.isdigit() or group_id in seen:
            continue
        group_ids.append(group_id)
        seen.add(group_id)
    return tuple(group_ids)


def update_sub2api_usage_alert_state(
    usages: list[Sub2APIAccountUsage],
    alerted_thresholds_by_account: dict[str, set[int]],
) -> list[Sub2APIUsageAlert]:
    alerts: list[Sub2APIUsageAlert] = []
    current_keys = set()
    for usage in usages:
        account_key = sub2api_alert_account_key(usage)
        current_keys.add(account_key)
        utilization = usage.five_hour.utilization if usage.five_hour is not None else None
        if utilization is None:
            continue
        reached = {threshold for threshold in SUB2API_USAGE_ALERT_THRESHOLDS if utilization >= threshold}
        previous = alerted_thresholds_by_account.get(account_key, set())
        newly_reached = reached - previous
        if newly_reached:
            alerts.append(
                Sub2APIUsageAlert(
                    usage=usage,
                    threshold=max(newly_reached),
                    utilization=utilization,
                )
            )
        alerted_thresholds_by_account[account_key] = reached
    for account_key in set(alerted_thresholds_by_account) - current_keys:
        alerted_thresholds_by_account.pop(account_key, None)
    return alerts


def sub2api_alert_account_key(usage: Sub2APIAccountUsage) -> str:
    if usage.account_id:
        return f"id:{usage.account_id}"
    return f"name:{normalize_cache_key(usage.name)}"


class Sub2APIClient:
    def __init__(
        self,
        *,
        base_url: str,
        admin_api_key: str,
        timeout_seconds: float = SUB2API_DEFAULT_TIMEOUT_SECONDS,
        http_client: AsyncSub2APIHttpClient | None = None,
    ) -> None:
        self.base_url = str(base_url or "").strip().rstrip("/")
        self.admin_api_key = str(admin_api_key or "").strip()
        self.timeout_seconds = float(timeout_seconds or SUB2API_DEFAULT_TIMEOUT_SECONDS)
        self.http_client = http_client

    async def get_account_usage(self, account_name: str, *, force_refresh: bool = False) -> list[Sub2APIAccountUsage]:
        if not self.base_url:
            raise ValueError("Sub2API 地址还没配置")
        if not self.admin_api_key:
            raise ValueError("Sub2API Admin API Key 还没配置")
        accounts = await self.find_accounts(account_name)
        if not accounts:
            raise LookupError(f"Sub2API 没找到账号：{account_name}")
        results: list[Sub2APIAccountUsage] = []
        for account in accounts:
            account_id = int(account.get("id") or 0)
            if account_id <= 0:
                continue
            usage = await self.fetch_usage(account_id, force_refresh=force_refresh)
            results.append(build_account_usage(account, usage))
        if not results:
            raise LookupError(f"Sub2API 账号缺少有效 id：{account_name}")
        return results

    async def find_accounts(self, account_name: str) -> list[dict[str, Any]]:
        query = urlencode(
            {
                "page": "1",
                "page_size": "10",
                "search": account_name,
                "sort_by": "name",
                "sort_order": "asc",
            }
        )
        payload = await self._get_json(f"{self.base_url}/api/v1/admin/accounts?{query}")
        items = ensure_dict(payload).get("data", {}).get("items", [])
        if not isinstance(items, list):
            return []
        return pick_matching_accounts(items, account_name)

    async def find_account(self, account_name: str) -> dict[str, Any] | None:
        accounts = await self.find_accounts(account_name)
        return accounts[0] if accounts else None

    async def fetch_usage(self, account_id: int, *, force_refresh: bool = False) -> dict[str, Any]:
        params = {"source": "active" if force_refresh else "passive"}
        if force_refresh:
            params["force"] = "true"
        query = urlencode(params)
        payload = await self._get_json(f"{self.base_url}/api/v1/admin/accounts/{account_id}/usage?{query}")
        data = ensure_dict(payload).get("data", {})
        return data if isinstance(data, dict) else {}

    async def _get_json(self, url: str) -> Any:
        headers = build_sub2api_headers(self.admin_api_key)
        if self.http_client is not None:
            return await self.http_client.get_json(url, headers=headers, timeout=self.timeout_seconds)
        return await get_json(url, headers=headers, timeout=self.timeout_seconds)


def build_sub2api_headers(admin_api_key: str) -> dict[str, str]:
    return {
        "x-api-key": admin_api_key,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "User-Agent": SUB2API_USER_AGENT,
    }


def pick_matching_accounts(items: list[object], account_name: str) -> list[dict[str, Any]]:
    normalized = account_name.strip().casefold()
    dict_items = [item for item in items if isinstance(item, dict)]
    matched = [item for item in dict_items if str(item.get("name", "")).strip().casefold() == normalized]
    return matched or dict_items


async def get_json(url: str, *, headers: dict[str, str], timeout: float) -> Any:
    def request_json() -> Any:
        request = Request(url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(format_sub2api_http_error(exc.code, detail)) from exc
        return json.loads(raw)

    return await asyncio.to_thread(request_json)


def format_sub2api_http_error(status_code: int, detail: str) -> str:
    if status_code == 403 and ("error-1010" in detail or "browser's signature" in detail or "Error 1010" in detail):
        return (
            "Sub2API 请求被 Cloudflare 拦截：HTTP 403 Error 1010，"
            "这是浏览器指纹/WAF 拦截，尚未进入 Admin API Key 鉴权。"
            "请在 Cloudflare 对 Sub2API Admin API 路径放行机器人服务器出口 IP，"
            "或把 sub2api_base_url 改为不经过 Cloudflare 的内网/源站地址。"
        )
    return f"Sub2API 请求失败：HTTP {status_code} {detail}"


def build_account_usage(account: dict[str, Any], usage: dict[str, Any]) -> Sub2APIAccountUsage:
    account_payload = ensure_dict(account.get("account") or account)
    return Sub2APIAccountUsage(
        account_id=int(account_payload.get("id") or account.get("id") or 0),
        name=str(account_payload.get("name") or account.get("name") or ""),
        platform=str(account_payload.get("platform") or account.get("platform") or ""),
        account_type=str(account_payload.get("type") or account.get("type") or ""),
        status=str(account_payload.get("status") or account.get("status") or ""),
        current_concurrency=optional_int(account.get("current_concurrency")),
        last_used_at=str(account_payload.get("last_used_at") or account.get("last_used_at") or ""),
        source=str(usage.get("source") or ""),
        updated_at=str(usage.get("updated_at") or ""),
        five_hour=parse_usage_window(usage.get("five_hour")),
        seven_day=parse_usage_window(usage.get("seven_day")),
        error=str(usage.get("error") or ""),
    )


def parse_usage_window(value: object) -> Sub2APIUsageWindow | None:
    if not isinstance(value, dict):
        return None
    return Sub2APIUsageWindow(
        utilization=optional_float(value.get("utilization")),
        resets_at=str(value.get("resets_at") or ""),
        remaining_seconds=optional_int(value.get("remaining_seconds")),
        window_stats=parse_window_stats(value.get("window_stats")),
    )


def parse_window_stats(value: object) -> Sub2APIWindowStats | None:
    if not isinstance(value, dict):
        return None
    return Sub2APIWindowStats(
        requests=optional_int(value.get("requests")) or 0,
        tokens=optional_int(value.get("tokens")) or 0,
        cost=optional_float(value.get("cost")) or 0.0,
        user_cost=optional_float(value.get("user_cost")),
    )


def format_sub2api_usage_response(usages: list[Sub2APIAccountUsage], account_name: str) -> str:
    if len(usages) == 1:
        return format_sub2api_usage_message(usages[0])
    lines = [f"Sub2API 用量：{account_name}，共 {len(usages)} 个账号"]
    for index, usage in enumerate(usages, start=1):
        lines.extend(format_sub2api_usage_message(usage, title=f"{index}. {usage.name or usage.account_id}").splitlines())
    return "\n".join(lines)


def format_sub2api_usage_alert_message(alert: Sub2APIUsageAlert) -> str:
    usage = alert.usage
    lines = [f"Sub2API 5h 用量提醒：{usage.name or usage.account_id} 已达到 {alert.threshold}%"]
    lines.append(f"当前 5h：{format_usage_window(usage.five_hour)}")
    if usage.seven_day is not None:
        lines.append(f"7d：{format_usage_window(usage.seven_day)}")
    if usage.updated_at:
        lines.append(f"更新时间：{format_time_text(usage.updated_at)}")
    return "\n".join(lines)


def format_sub2api_usage_message(usage: Sub2APIAccountUsage, *, title: str | None = None) -> str:
    lines = [title or f"Sub2API 用量：{usage.name or usage.account_id}"]
    meta = []
    if usage.platform:
        meta.append(usage.platform)
    if usage.account_type:
        meta.append(usage.account_type)
    if usage.status:
        meta.append(usage.status)
    if usage.current_concurrency is not None:
        meta.append(f"并发 {usage.current_concurrency}")
    if meta:
        lines.append(f"状态：{' / '.join(meta)}")
    lines.append(f"5h：{format_usage_window(usage.five_hour)}")
    lines.append(f"7d：{format_usage_window(usage.seven_day)}")
    if usage.last_used_at:
        lines.append(f"最近使用：{format_time_text(usage.last_used_at)}")
    if usage.updated_at:
        lines.append(f"更新时间：{format_time_text(usage.updated_at)}")
    if usage.source:
        lines.append(f"来源：{usage.source}")
    if usage.error:
        lines.append(f"提示：{usage.error}")
    return "\n".join(lines)


def format_usage_window(window: Sub2APIUsageWindow | None) -> str:
    if window is None:
        return "无数据"
    parts = []
    if window.utilization is not None:
        parts.append(f"{window.utilization:.0f}%")
    if window.window_stats is not None:
        stats = window.window_stats
        if stats.tokens:
            parts.append(f"{format_compact_number(stats.tokens)} tokens")
        if stats.requests:
            parts.append(f"{stats.requests} 次")
        if stats.cost:
            parts.append(f"${stats.cost:.2f}")
    remaining = format_remaining_seconds(window.remaining_seconds)
    if remaining:
        parts.append(f"重置剩 {remaining}")
    elif window.resets_at:
        parts.append(f"重置 {format_time_text(window.resets_at)}")
    return "，".join(parts) if parts else "无数据"


def format_remaining_seconds(value: int | None) -> str:
    if value is None or value < 0:
        return ""
    minutes = value // 60
    hours, minute = divmod(minutes, 60)
    days, hour = divmod(hours, 24)
    if days > 0:
        return f"{days}天{hour}小时"
    if hour > 0:
        return f"{hour}小时{minute}分"
    return f"{minute}分"


def format_time_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = parse_datetime(text)
    if parsed is None:
        return text
    local = parsed.astimezone()
    return local.strftime("%Y-%m-%d %H:%M")


def parse_datetime(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def format_compact_number(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def ensure_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
