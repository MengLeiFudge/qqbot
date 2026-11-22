from __future__ import annotations

import asyncio
import base64
from collections.abc import Callable
from dataclasses import dataclass, replace
from decimal import Decimal, ROUND_CEILING
import hashlib
import json
from io import BytesIO
from pathlib import Path
import re
import threading
import time
from urllib.error import HTTPError
from urllib.parse import unquote, urlsplit

import httpx
from PIL import Image

from .draw_output import load_generated_image
from .model_catalog import MODEL_NAME, fetch_models, model_unavailable
from .storage import RuntimeJsonStore
from .storage import read_json_file


RIGHTCODES_DRAW_BASE_URL = "http://127.0.0.1:8317/v1"
RIGHTCODES_DRAW_USER_AGENT = "QQBot-CPA-Draw/1.0"
RIGHTCODES_DRAW_DEFAULT_MODEL = "gpt-image-2.6"
RIGHTCODES_DRAW_POINT_PRICE_MULTIPLIER = 1000
RIGHTCODES_DRAW_MODEL_PRICES = {
    RIGHTCODES_DRAW_DEFAULT_MODEL: Decimal("0.06"),
    "gpt-image-2.6-flare": Decimal("0.15"),
    "gpt-image-2.6-sunburst": Decimal("0.15"),
}
_DRAW_SIZES = {
    "1k": {"": "1024x1024", "横": "1536x1024", "竖": "1024x1536"},
    "2k": {"": "2048x2048", "横": "2048x1152", "竖": "1152x2048"},
    "4k": {"": "4096x4096", "横": "4096x2304", "竖": "2304x4096"},
}
STANDARD_DRAW_PREFIX = re.compile(r"^\s*(文生|图生|头像生)([横竖动]?)图")
_LEVEL = re.compile(r"(1k|2k|4k)", re.IGNORECASE)
_POINTS_KEY = "draw.points"
_DRAW_POINTS_LOCK = threading.Lock()
_DRAW_POINTS_QUERY_RE = re.compile(
    r"^(?:(?:查|查询|查看|看)(?:一下)?)?(?:我(?:的)?|当前)?(?:生图)?积分(?:余额|情况|多少)?$"
)
_DRAW_POINTS_ENGLISH_QUERY_RE = re.compile(r"^(?:balance|points?)$", re.IGNORECASE)
_DRAW_POINTS_MUTATION_RE = re.compile(
    r"(?:加|增加|扣|扣除|减|减少|改|修改|设置|设定|送|赠|赠送|充值|充).{0,16}积分"
    r"|积分.{0,16}(?:加|增加|扣|扣除|减|减少|改|修改|设置|设定|送|赠|赠送|充值|充)"
)
_DRAW_MODEL_SWITCH_PRIMARY_RE = re.compile(r"^切换\s*生图\s*模型\s*(.*)$", re.IGNORECASE)
_DRAW_MODEL_SWITCH_ALIAS_RE = re.compile(r"^生图\s*模型\s*(.+)$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class RightCodesDrawRequest:
    prompt: str
    model: str = RIGHTCODES_DRAW_DEFAULT_MODEL
    image_urls: tuple[str, ...] = ()
    size: str = "4096x4096"
    gif: bool = False


@dataclass(frozen=True, slots=True)
class RightCodesDrawResult:
    """CPA 原始图片来源、耗时及供保存和发送复用的已校验 PNG 字节。"""

    image_url: str
    total_seconds: float
    image_bytes: bytes = b""
    model: str = RIGHTCODES_DRAW_DEFAULT_MODEL
    gif: bool = False


@dataclass(frozen=True, slots=True)
class RightCodesDrawPointBalance:
    user_id: str
    points: int
    model: str
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


class RightCodesDrawTimeoutError(TimeoutError):
    def __init__(self, timeout_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds
        super().__init__(f"生图超过 {timeout_seconds:.0f} 秒未返回")


class RightCodesDrawClient:
    """向 CPA 提交图片请求，渠道选择和上游重试均由 CPA 负责。"""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = RIGHTCODES_DRAW_BASE_URL,
        timeout_seconds: float = 240.0,
    ) -> None:
        """保存 CPA 客户端凭据、包含 /v1 的地址和含参考图下载的总超时秒数。"""
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def draw_batch(
        self, requests: tuple[RightCodesDrawRequest, ...],
    ) -> tuple[RightCodesDrawResult | BaseException, ...]:
        """并行等待单张或四张请求，按输入顺序保留成品及错误；取消时回收全部任务。"""
        if len(requests) not in (1, 4):
            raise ValueError("生图批次必须包含一张或四张")
        tasks = [asyncio.create_task(self.draw(request)) for request in requests]
        try:
            return tuple(await asyncio.gather(*tasks, return_exceptions=True))
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def models(self, preferred: str = "", *, refresh: bool = False) -> tuple[str, ...]:
        if not self.api_key:
            raise ValueError("缺少 CPA 生图 API Key")
        return await fetch_models(self.api_key, self.base_url, preferred=preferred, refresh=refresh)

    async def draw(self, request: RightCodesDrawRequest) -> RightCodesDrawResult:
        """Send one image call, refreshing CPA registration after a rejected model."""

        if not self.api_key:
            raise ValueError("缺少 CPA 生图 API Key")
        candidates = [request.model]
        try:
            available = await self.models(request.model)
            candidates = list(available) or candidates
        except (httpx.HTTPError, ValueError):
            pass
        tried: set[str] = set()
        refreshed = False
        for model in candidates:
            if model in tried or len(tried) >= 4:
                continue
            tried.add(model)
            try:
                return await self._draw_once(replace(request, model=model))
            except _ModelUnavailable:
                if not refreshed:
                    refreshed = True
                    try:
                        candidates.extend(await self.models(request.model, refresh=True))
                    except (httpx.HTTPError, ValueError):
                        pass
        raise RuntimeError("CPA 没有可用的生图模型，请检查渠道模型的 image 配置")

    async def _draw_once(self, request: RightCodesDrawRequest) -> RightCodesDrawResult:
        started = time.perf_counter()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "User-Agent": RIGHTCODES_DRAW_USER_AGENT,
        }
        payload = {
            "model": request.model,
            "prompt": request.prompt,
            "n": 1,
            "size": request.size,
            "response_format": "b64_json",
            "output_format": "gif" if request.gif else "png",
        }
        try:
            async with asyncio.timeout(self.timeout_seconds):
                async with httpx.AsyncClient(timeout=self.timeout_seconds, trust_env=False) as client:
                    if request.image_urls:
                        # 单张沿用单文件字段，多张参考图才使用数组字段。
                        field = "image" if len(request.image_urls) == 1 else "image[]"
                        files = []
                        for index, source in enumerate(request.image_urls):
                            image, mime = await load_draw_reference_image(source, client)
                            files.append((field, (f"reference-{index}.{mime.split('/')[-1]}", image, mime)))
                        response = await client.post(
                            f"{self.base_url}/images/edits",
                            headers=headers,
                            data={key: str(value) for key, value in payload.items()},
                            files=files,
                        )
                    else:
                        response = await client.post(
                            f"{self.base_url}/images/generations",
                            headers=headers,
                            json=payload,
                        )
                    response.raise_for_status()
                    data = response.json()
                    image_url = extract_image_url_from_object(data)
                    if not image_url:
                        raise RuntimeError(extract_rightcodes_task_error(data) or "生图服务没有返回图片")
                    image_bytes = await load_generated_image(image_url, client, gif=request.gif)
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise RightCodesDrawTimeoutError(self.timeout_seconds) from exc
        except httpx.HTTPStatusError as exc:
            try:
                detail = extract_rightcodes_task_error(exc.response.json())
            except (ValueError, httpx.ResponseNotRead):
                detail = ""
            detail = re.sub(r"\s+", " ", detail).replace(self.api_key, "[redacted]")
            detail = re.sub(r"\b(?:sk-|Bearer\s+)[A-Za-z0-9._-]+", "[redacted]", detail, flags=re.IGNORECASE)[:300]
            if model_unavailable(exc.response.status_code, detail):
                raise _ModelUnavailable from exc
            message = f"生图服务返回 HTTP {exc.response.status_code}"
            if detail:
                message += f"：{detail}"
            raise RuntimeError(message) from exc
        return RightCodesDrawResult(
            image_url=image_url, image_bytes=image_bytes, total_seconds=time.perf_counter() - started,
            model=request.model, gif=request.gif,
        )


class _ModelUnavailable(RuntimeError):
    pass

async def load_draw_reference_image(source: str, client: httpx.AsyncClient) -> tuple[bytes, str]:
    """加载最多 20 MiB 的参考图并识别 MIME；远程下载不携带 CPA 凭据。"""
    limit = 20 * 1024 * 1024
    if source.startswith(("data:image/", "base64://")):
        if source.startswith("data:image/"):
            header, separator, encoded = source.partition(",")
            if not separator or ";base64" not in header.lower():
                raise ValueError("参考图必须是 Base64 data URL")
        else:
            encoded = source.removeprefix("base64://")
        encoded = re.sub(r"\s+", "", encoded)
        if len(encoded) > (limit + 2) // 3 * 4:
            raise ValueError("参考图不能超过 20 MiB")
        image = base64.b64decode(encoded, validate=True)
    elif source.startswith(("http://", "https://")):
        content = bytearray()
        async with client.stream("GET", source, follow_redirects=True) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > limit:
                    raise ValueError("参考图不能超过 20 MiB")
        image = bytes(content)
    else:
        path = source
        if source.startswith("file://"):
            path = unquote(urlsplit(source).path)
            if re.match(r"^/[A-Za-z]:", path):
                path = path[1:]
        with Path(path).open("rb") as stream:
            image = stream.read(limit + 1)
    if not image or len(image) > limit:
        raise ValueError("参考图不能为空或超过 20 MiB")
    with Image.open(BytesIO(image)) as reference:
        mime = Image.MIME.get(reference.format or "", "")
        if mime not in {"image/png", "image/jpeg", "image/webp"}:
            converted = BytesIO()
            reference.convert("RGBA").save(converted, format="PNG")
            image, mime = converted.getvalue(), "image/png"
        else:
            reference.verify()
    if len(image) > limit:
        raise ValueError("参考图转换后不能超过 20 MiB")
    return image, mime


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
        self.store = RuntimeJsonStore(self.data_root)

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

    def get_balance(self, user_id: int | str) -> RightCodesDrawPointBalance:
        user_key = str(user_id).strip()
        if not user_key:
            return RightCodesDrawPointBalance("", 0, RIGHTCODES_DRAW_DEFAULT_MODEL, self.multiplier)
        with _DRAW_POINTS_LOCK:
            payload = self._read()
            users = get_users_payload(payload)
            user_payload = get_user_payload(users, user_key)
        return RightCodesDrawPointBalance(
            user_id=user_key,
            points=int(user_payload.get("points", 0) or 0),
            model=normalize_rightcodes_draw_model(user_payload.get("model")),
            multiplier=self.multiplier,
        )

    def set_model(self, user_id: int | str, model: str) -> RightCodesDrawPointBalance:
        user_key = str(user_id).strip()
        model_key = str(model or "").strip().lower()
        if not user_key:
            raise ValueError("缺少 QQ 用户 ID")
        if not MODEL_NAME.fullmatch(model_key):
            raise ValueError(f"不支持的生图模型: {model}")
        with _DRAW_POINTS_LOCK:
            payload = self._read()
            users = get_users_payload(payload)
            user_payload = get_user_payload(users, user_key)
            user_payload["model"] = model_key
            users[user_key] = user_payload
            payload["users"] = users
            self._write(payload)
            return RightCodesDrawPointBalance(
                user_id=user_key,
                points=int(user_payload.get("points", 0) or 0),
                model=model_key,
                multiplier=self.multiplier,
            )

    def get_points_ranking(self, *, limit: int = 10) -> tuple[RightCodesDrawPointBalance, ...]:
        with _DRAW_POINTS_LOCK:
            payload = self._read()
            users = get_users_payload(payload)
        balances = [
            RightCodesDrawPointBalance(
                user_id=user_id,
                points=int(user_payload.get("points", 0) or 0),
                model=normalize_rightcodes_draw_model(user_payload.get("model")),
                multiplier=self.multiplier,
            )
            for user_id, user_payload in users.items()
        ]
        balances.sort(key=lambda item: (-item.points, sortable_user_id(item.user_id)))
        return tuple(balances[: max(0, int(limit))])

    def reserve(
        self,
        user_id: int | str,
        *,
        model: str = RIGHTCODES_DRAW_DEFAULT_MODEL,
    ) -> RightCodesDrawQuotaResult:
        user_key = str(user_id).strip()
        model = normalize_rightcodes_draw_model(model)
        cost_points = calculate_rightcodes_draw_model_points(model, multiplier=self.multiplier)
        price = format_rightcodes_draw_model_price(model)
        if not user_key:
            return RightCodesDrawQuotaResult(False, "", model, cost_points, 0, 0, self.multiplier, price)
        with _DRAW_POINTS_LOCK:
            payload = self._read()
            users = get_users_payload(payload)
            user_payload = get_user_payload(users, user_key)
            balance = int(user_payload.get("points", 0) or 0)
            if balance < cost_points:
                return RightCodesDrawQuotaResult(
                    False, user_key, model, cost_points, balance, balance, self.multiplier, price
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
            )

    def refund(self, reservation: RightCodesDrawQuotaResult) -> None:
        if not reservation.allowed or not reservation.user_id:
            return
        with _DRAW_POINTS_LOCK:
            payload = self._read()
            users = get_users_payload(payload)
            user_payload = get_user_payload(users, reservation.user_id)
            if reservation.cost_points > 0:
                points = int(user_payload.get("points", 0) or 0)
                user_payload["points"] = points + reservation.cost_points
            users[reservation.user_id] = user_payload
            payload["users"] = users
            self._write(payload)

    def _read(self) -> dict[str, object]:
        raw = self.store.read(_POINTS_KEY, {"schema_version": 2, "users": {}})
        if not isinstance(raw, dict):
            raw = {"schema_version": 2, "users": {}}
        normalized = normalize_draw_points_payload(raw)
        if normalized != raw:
            self.store.write(_POINTS_KEY, normalized)
        raw = normalized
        if not self.path.exists():
            return raw
        fingerprint = fingerprint_file(self.path)
        imports = self.store.read(f"{_POINTS_KEY}_legacy_imports", {"files": {}})
        imported_files = imports.get("files") if isinstance(imports, dict) else {}
        if isinstance(imported_files, dict) and imported_files.get(str(self.path)) == fingerprint:
            return raw
        legacy_raw = read_json_file(self.path, {"schema_version": 1, "users": {}})
        merged = merge_draw_points_payload(raw, legacy_raw)
        if merged != raw:
            self.store.write(_POINTS_KEY, merged)
        if not isinstance(imported_files, dict):
            imported_files = {}
        imported_files[str(self.path)] = fingerprint
        self.store.write(f"{_POINTS_KEY}_legacy_imports", {"files": imported_files})
        return merged

    def _write(self, payload: dict[str, object]) -> None:
        payload = normalize_draw_points_payload(payload)
        self.store.write(_POINTS_KEY, payload)


def parse_draw_prefix(text: str) -> tuple[str, str, bool, int] | None:
    match = STANDARD_DRAW_PREFIX.match(text)
    if match is None:
        return None
    base, mode = match.groups()
    end = match.end()
    tail = text[end:].lstrip()
    level = _LEVEL.match(tail)
    size = "4k"
    if level:
        rest = tail[level.end():]
        if not rest or rest[0].isspace():
            size = level.group(1).lower()
            end = len(text) - len(rest)
        elif text[end:] == tail:
            raise ValueError(f"“{level.group(1)}”后面要空一格再写提示词")
    return base + "图", _DRAW_SIZES[size][mode if mode in ("横", "竖") else ""], mode == "动", end


def parse_rightcodes_draw_command(text: str) -> RightCodesDrawRequest | None:
    if text.strip() == "生成豆豆眼头像":
        return RightCodesDrawRequest(prompt="豆豆眼")
    if parsed := parse_draw_prefix(text):
        _, size, gif, end = parsed
        if prompt := text[end:].strip():
            return RightCodesDrawRequest(prompt=prompt, size=size, gif=gif)
    return None


def looks_like_rightcodes_draw_invocation(text: str) -> bool:
    return text.strip() == "生成豆豆眼头像" or STANDARD_DRAW_PREFIX.match(text) is not None


def looks_like_rightcodes_draw_feature_request(text: str) -> bool:
    normalized = str(text or "").strip()
    if not normalized:
        return False
    return (
        looks_like_rightcodes_draw_invocation(normalized)
        or looks_like_rightcodes_draw_points_mutation_request(normalized)
        or looks_like_rightcodes_draw_points_query(normalized)
        or looks_like_rightcodes_draw_points_ranking(normalized)
        or looks_like_rightcodes_draw_help_command(normalized)
        or looks_like_rightcodes_draw_model_switch(normalized)
    )


def extract_removed_rightcodes_draw_temporary_model(text: str) -> str | None:
    if text.lstrip().startswith(("文生图", "图生图", "头像生图")):
        return None
    try:
        parsed = parse_draw_prefix(text)
    except ValueError:
        return None
    rest = text[parsed[3]:].strip() if parsed else ""
    if not rest:
        return None
    bracket_match = re.match(r"^\[([^\]]+)\](?:\s+|$)", rest)
    if bracket_match is not None:
        candidate = bracket_match.group(1).strip().lower()
    else:
        candidate = rest.split(maxsplit=1)[0].strip().lower()
    # 继续识别已退役的临时模型写法，避免将其当作提示词扣费执行。
    return candidate if re.fullmatch(r"gpt-image-2(?:\.5|-vip)?|nano-banana(?:-2(?:-lite)?|-pro)?", candidate) else None


def looks_like_rightcodes_draw_command(text: str) -> bool:
    return parse_rightcodes_draw_command(text) is not None


def format_rightcodes_draw_missing_prompt_message() -> str:
    return "请填写提示词。用法：文生图 提示词；图生图 提示词（附图或引用图）；头像生图 [@某人] 提示词。"


def format_rightcodes_draw_temporary_model_removed(model: str) -> str:
    return (
        f"生图命令不再支持临时指定模型 {model}，本次没有扣积分。"
        "请使用“切换生图模型 模型名”设置常用模型。"
    )


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


def looks_like_rightcodes_draw_points_ranking(text: str) -> bool:
    compact = re.sub(r"\s+", "", text.strip())
    return compact in {"积分排行", "积分排行榜"}


def looks_like_rightcodes_draw_points_mutation_request(text: str) -> bool:
    compact = re.sub(r"\s+", "", text.strip())
    if not compact or "积分" not in compact:
        return False
    return _DRAW_POINTS_MUTATION_RE.search(compact) is not None


def extract_rightcodes_draw_model_switch(text: str) -> str | None:
    normalized = text.strip()
    match = _DRAW_MODEL_SWITCH_PRIMARY_RE.fullmatch(normalized)
    if match is not None:
        return match.group(1).strip()
    match = _DRAW_MODEL_SWITCH_ALIAS_RE.fullmatch(normalized)
    if match is not None:
        return match.group(1).strip()
    return None


def looks_like_rightcodes_draw_model_switch(text: str) -> bool:
    return extract_rightcodes_draw_model_switch(text) is not None


def parse_rightcodes_draw_model_switch(text: str) -> str | None:
    candidate = extract_rightcodes_draw_model_switch(text)
    if candidate is None:
        return None
    model = candidate.lower()
    return model if MODEL_NAME.fullmatch(model) else None


def format_rightcodes_draw_model_help(
    current_model: str = RIGHTCODES_DRAW_DEFAULT_MODEL,
    *,
    multiplier: int = RIGHTCODES_DRAW_POINT_PRICE_MULTIPLIER,
    models: tuple[str, ...] = (),
) -> str:
    current_model = normalize_rightcodes_draw_model(current_model)
    lines = [f"当前生图模型：{current_model}", "可用模型："]
    if not models:
        lines.append("暂时无法读取 CPA 的图片模型列表。")
    for model in models:
        description = "支持文字生图和参考图生图"
        price = format_rightcodes_draw_model_price(model)
        current_mark = "（当前）" if model == current_model else ""
        lines.append(
            f"· {model}{current_mark}：{price} 元/次，"
            f"{calculate_rightcodes_draw_model_points(model, multiplier=multiplier)} 积分。{description}"
        )
    lines.extend(
        [
            "",
            "生图指令：文生图、图生图或头像生图。可写成“文生竖图2k 提示词”或“图生动图 提示词”。",
        ]
    )
    return "\n".join(lines)


def format_rightcodes_draw_points_status(balance: RightCodesDrawPointBalance) -> str:
    cost_points = calculate_rightcodes_draw_model_points(balance.model, multiplier=balance.multiplier)
    return "\n".join(
        [
            f"当前生图积分：{balance.points}",
            f"当前生图模型：{balance.model}",
            f"当前模型消耗：{cost_points} 积分/次",
            "",
            "查看模型与价格：生图模型",
        ]
    )


def format_rightcodes_draw_points_ranking(
    ranking: tuple[RightCodesDrawPointBalance, ...],
    *,
    resolve_display_name: Callable[[str], str] | None = None,
) -> str:
    if not ranking:
        return "全群还没有生图积分记录。"
    lines = ["全群生图积分排行榜："]
    for index, balance in enumerate(ranking, start=1):
        display_name = resolve_display_name(balance.user_id) if resolve_display_name is not None else balance.user_id
        identity = display_name if display_name != balance.user_id else f"QQ {mask_qq_user_id(balance.user_id)}"
        lines.append(f"{index}. {identity}：{balance.points} 积分")
    return "\n".join(lines)


def format_rightcodes_draw_model_switch_success(balance: RightCodesDrawPointBalance) -> str:
    cost_points = calculate_rightcodes_draw_model_points(balance.model, multiplier=balance.multiplier)
    description = "支持文字生图和参考图生图"
    return "\n".join(
        [
            f"已切换生图模型：{balance.model}",
            f"单次消耗：{cost_points} 积分",
            description,
            "之后发送“文生图 提示词”或“图生图 提示词”就会使用这个模型。",
        ]
    )


def format_rightcodes_draw_model_switch_invalid(candidate: str) -> str:
    candidate = str(candidate or "").strip()
    first_line = f"不支持这个生图模型：{candidate}" if candidate else "请输入要切换的生图模型。"
    return first_line + "\n发送“生图模型”查询可用模型。"



def format_rightcodes_draw_points_mutation_denied() -> str:
    return "生图积分只能通过群消息自动累计，并在生图时自动扣除；普通聊天不能手动加分或改分。"


def format_draw_start_message(quota: RightCodesDrawQuotaResult) -> str:
    return (
        "收到，棉花糖开始生图任务啦！"
        f"本次使用 {quota.model}，扣 {quota.cost_points} 积分，"
        f"剩余 {quota.balance_after} 积分。"
    )


def format_draw_quota_exceeded_message(quota: RightCodesDrawQuotaResult) -> str:
    return (
        f"积分不够啦：{quota.model} 需要 {quota.cost_points} 积分"
        f"（价格 {quota.price} 元），"
        f"你现在有 {quota.balance_before} 积分。"
        "可发送“查看积分”查询余额，通过群消息继续累计积分。"
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
    return (
        f"❌ 生成失败: {extract_rightcodes_draw_error_message(exc)}。"
        "本次扣除的积分已退回，请稍后重试。"
    )


def format_rightcodes_draw_timeout(timeout_seconds: float) -> str:
    return (
        f"❌ 生成失败: 生图超过 {timeout_seconds:.0f} 秒还没返回，"
        "本次扣除的积分已退回，请稍后重试。"
    )


def extract_rightcodes_draw_error_message(exc: Exception) -> str:
    if isinstance(exc, RightCodesDrawTimeoutError):
        return f"生图超过 {exc.timeout_seconds:.0f} 秒未返回"
    if isinstance(exc, TimeoutError):
        return "生图请求超时"
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
    return RIGHTCODES_DRAW_MODEL_PRICES.get(normalize_rightcodes_draw_model(model), Decimal("0.06"))


def format_rightcodes_draw_model_price(model: str) -> str:
    return f"{get_rightcodes_draw_model_price(model):.2f}"


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


def extract_rightcodes_task_error(data: object) -> str:
    if not isinstance(data, dict):
        return ""
    error = data.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    message = data.get("message")
    return message.strip() if isinstance(message, str) else ""


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
        return {"points": 0, "model": RIGHTCODES_DRAW_DEFAULT_MODEL}
    payload: dict[str, object] = {
        "points": safe_int(raw.get("points"), 0),
        "model": normalize_rightcodes_draw_model(raw.get("model")),
    }
    return payload


def normalize_draw_points_payload(payload: dict[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {
        "schema_version": max(2, safe_int(payload.get("schema_version"), 2)),
        "users": {},
    }
    users: dict[str, dict[str, object]] = {}
    for user_id, raw_user in get_users_payload(payload).items():
        users[user_id] = get_user_payload({user_id: raw_user}, user_id)
    normalized["users"] = users
    return normalized


def merge_draw_points_payload(current: dict[str, object], legacy: dict[str, object]) -> dict[str, object]:
    merged = normalize_draw_points_payload(current)
    users = get_users_payload(merged)
    for user_id, legacy_user in get_users_payload(normalize_draw_points_payload(legacy)).items():
        current_exists = user_id in users
        current_user = get_user_payload(users, user_id)
        legacy_payload = get_user_payload({user_id: legacy_user}, user_id)
        current_points = safe_int(current_user.get("points"), 0)
        legacy_points = safe_int(legacy_payload.get("points"), 0)
        if legacy_points > current_points:
            current_user["points"] = legacy_points
        if not current_exists:
            current_user["model"] = normalize_rightcodes_draw_model(legacy_payload.get("model"))
        users[user_id] = current_user
    merged["users"] = users
    return merged


def fingerprint_file(path: Path) -> str:
    stat = path.stat()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"{stat.st_size}:{stat.st_mtime_ns}:{digest}"


def safe_int(value: object, default: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def normalize_rightcodes_draw_model(model: object) -> str:
    candidate = str(model or "").strip().lower()
    return candidate if MODEL_NAME.fullmatch(candidate) else RIGHTCODES_DRAW_DEFAULT_MODEL


def mask_qq_user_id(user_id: object) -> str:
    value = str(user_id or "").strip()
    if len(value) <= 6:
        return "*" * max(1, len(value))
    return f"{value[:3]}{'*' * (len(value) - 6)}{value[-3:]}"


def sortable_user_id(user_id: str) -> tuple[int, int | str]:
    user_key = str(user_id or "").strip()
    if user_key.isdigit():
        return (0, int(user_key))
    return (1, user_key)
