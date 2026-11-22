from __future__ import annotations

import asyncio
import re
import time

import httpx


MODEL_NAME = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,63}$")
_IMAGE_NAMES = ("image", "imagen", "dall-e", "dalle", "flux", "banana", "seedream")
_VERSION = re.compile(r"\d+(?:\.\d+)*")
_UNAVAILABLE = ("is not supported on /v1/images/", "model_not_found", "model not found", "model does not exist", "unsupported model", "no available channel")
_CACHE: dict[tuple[str, str], tuple[float, tuple[str, ...]]] = {}
_LOCK = asyncio.Lock()


def model_unavailable(status: int, detail: str) -> bool:
    return status == 404 or any(hint in detail.casefold() for hint in _UNAVAILABLE)


def _model_rank(name: str) -> tuple[tuple[int, ...], int, str]:
    matched = _VERSION.search(name)
    version = tuple(-int(n) for n in matched.group().split(".")) if matched else (1,)
    return version, name.count("-"), name


def _prefer(models: tuple[str, ...], preferred: str) -> tuple[str, ...]:
    if preferred not in models:
        return models
    return (preferred, *(model for model in models if model != preferred))


async def fetch_models(api_key: str, base_url: str, *, preferred: str = "", refresh: bool = False) -> tuple[str, ...]:
    key = (base_url.rstrip("/"), api_key)
    async with _LOCK:
        cached = _CACHE.get(key)
        if cached and not refresh and time.monotonic() - cached[0] < 600:
            return _prefer(cached[1], preferred)
        headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json", "User-Agent": "QQBot-CPA-Draw/1.0"}
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            response = await client.get(f"{key[0]}/models", headers=headers)
            response.raise_for_status()
            payload = response.json()
        entries = payload.get("data") if isinstance(payload, dict) else payload
        if not isinstance(entries, list):
            raise ValueError("CPA 模型列表响应无效")
        models = set()
        for entry in entries:
            value = entry.get("id") if isinstance(entry, dict) else entry
            name = str(value or "").strip().lower()
            if MODEL_NAME.fullmatch(name) and any(hint in name for hint in _IMAGE_NAMES):
                models.add(name)
        ordered = tuple(sorted(models, key=_model_rank))
        _CACHE[key] = (time.monotonic(), ordered)
        return _prefer(ordered, preferred)
