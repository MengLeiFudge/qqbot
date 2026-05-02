from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tomllib


@dataclass(frozen=True, slots=True)
class AiProfile:
    name: str
    provider: str
    base_url: str
    model: str
    api_key_env: str
    enabled: bool = True
    timeout_seconds: float = 45.0
    supports_vision: bool = False
    note: str = ""


@dataclass(frozen=True, slots=True)
class ResolvedAiProfile:
    name: str
    provider: str
    base_url: str
    model: str
    api_key: str
    timeout_seconds: float
    supports_vision: bool = False
    note: str = ""


def load_ai_profiles(path: Path) -> dict[str, AiProfile]:
    profile_path = Path(path)
    if not profile_path.exists():
        return {}

    data = tomllib.loads(profile_path.read_text(encoding="utf-8"))
    raw_profiles = _get_raw_profiles(data)
    if not isinstance(raw_profiles, dict):
        raise ValueError("AI provider 配置必须包含 [model_providers.<name>]")

    profiles: dict[str, AiProfile] = {}
    for name, raw in raw_profiles.items():
        if not isinstance(raw, dict):
            raise ValueError(f"AI profile {name} 必须是对象")
        profile = AiProfile(
            name=str(name),
            provider=str(raw.get("provider", "openai_compatible")).strip(),
            base_url=str(raw.get("base_url", "")).strip(),
            model=str(raw.get("model", "")).strip(),
            api_key_env=str(raw.get("api_key_env", "")).strip(),
            enabled=bool(raw.get("enabled", True)),
            timeout_seconds=float(raw.get("timeout_seconds", 45.0)),
            supports_vision=bool(raw.get("supports_vision", False)),
            note=str(raw.get("note", "")).strip(),
        )
        _validate_profile(profile)
        profiles[profile.name] = profile
    return profiles


def load_ai_default_profile_name(path: Path) -> str | None:
    profile_path = Path(path)
    if not profile_path.exists():
        return None
    data = tomllib.loads(profile_path.read_text(encoding="utf-8"))
    raw_name = data.get("model_provider")
    if not isinstance(raw_name, str):
        raw_ai = data.get("ai")
        if isinstance(raw_ai, dict):
            raw_name = raw_ai.get("default_profile")
    return raw_name.strip() if isinstance(raw_name, str) and raw_name.strip() else None


def list_enabled_profiles(profiles: dict[str, AiProfile]) -> list[AiProfile]:
    return [profile for profile in profiles.values() if profile.enabled]


def resolve_ai_profile(profiles: dict[str, AiProfile], name: str) -> ResolvedAiProfile:
    profile_name = name.strip()
    if profile_name not in profiles:
        raise ValueError(f"未知 AI profile：{profile_name}")

    profile = profiles[profile_name]
    if not profile.enabled:
        raise ValueError(f"AI profile 已禁用：{profile_name}")

    api_key = os.environ.get(profile.api_key_env, "").strip()
    if not api_key and _looks_like_direct_api_key(profile.api_key_env):
        api_key = profile.api_key_env
    if not api_key:
        raise ValueError(f"缺少 AI profile 密钥环境变量：{profile.api_key_env}")

    return ResolvedAiProfile(
        name=profile.name,
        provider=profile.provider,
        base_url=profile.base_url,
        model=profile.model,
        api_key=api_key,
        timeout_seconds=profile.timeout_seconds,
        supports_vision=profile.supports_vision,
        note=profile.note,
    )


def _validate_profile(profile: AiProfile) -> None:
    missing = []
    if not profile.provider:
        missing.append("provider")
    if not profile.base_url:
        missing.append("base_url")
    if not profile.model:
        missing.append("model")
    if not profile.api_key_env:
        missing.append("api_key_env")
    if missing:
        raise ValueError(f"AI profile {profile.name} 缺少字段：{', '.join(missing)}")


def _get_raw_profiles(data: dict[str, object]) -> object:
    raw_ai = data.get("ai")
    if isinstance(raw_ai, dict) and "providers" in raw_ai:
        return raw_ai.get("providers")
    return data.get("model_providers", data.get("profiles", {}))


def _looks_like_direct_api_key(value: str) -> bool:
    normalized = value.strip()
    if not normalized:
        return False
    if normalized.startswith(("sk-", "ak-", "tp-")):
        return True
    return len(normalized) >= 24 and "-" in normalized
