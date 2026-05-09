from __future__ import annotations

from qqbot.config import RuntimeSettings
from qqbot.services.ai_gateway import AiGateway
from qqbot.services.ai_profile_registry import (
    AiProfile,
    list_enabled_profiles,
    load_ai_default_profile_name,
    load_ai_profiles,
    resolve_ai_profile,
)
from qqbot.services.mimo_compatible_client import MimoCompatibleClient
from qqbot.services.openai_compatible_client import OpenAICompatibleClient
from qqbot.services.settings_store import SettingsStore


def get_default_ai_profile_name(settings: RuntimeSettings) -> str:
    return (
        load_ai_default_profile_name(settings.ai_profile_file)
        or settings.ai_default_profile
    )


def get_current_ai_profile_name(
    settings: RuntimeSettings,
    store: SettingsStore,
    profiles: dict[str, AiProfile] | None = None,
) -> str:
    profiles = profiles if profiles is not None else load_ai_profiles(settings.ai_profile_file)
    enabled_names = {profile.name for profile in list_enabled_profiles(profiles)}
    default_profile = get_default_ai_profile_name(settings)
    saved_profile = store.get_ai_provider(default_profile)

    if saved_profile in enabled_names:
        return saved_profile
    if default_profile in enabled_names:
        return default_profile
    if enabled_names:
        return next(profile.name for profile in list_enabled_profiles(profiles))
    return saved_profile


def build_ai_gateway(settings: RuntimeSettings, profile_name: str) -> AiGateway:
    profiles = load_ai_profiles(settings.ai_profile_file)
    resolved = resolve_ai_profile(profiles, profile_name)
    if resolved.provider == "openai_compatible":
        client = OpenAICompatibleClient(
            base_url=resolved.base_url,
            api_key=resolved.api_key,
            model=resolved.model,
            timeout_seconds=resolved.timeout_seconds,
            supports_vision=resolved.supports_vision,
        )
    elif resolved.provider in {"xiaomi_mimo", "mimo_compatible"}:
        client = MimoCompatibleClient(
            base_url=resolved.base_url,
            api_key=resolved.api_key,
            model=resolved.model,
            timeout_seconds=resolved.timeout_seconds,
            supports_vision=resolved.supports_vision,
        )
    else:
        raise ValueError(f"暂不支持 AI provider：{resolved.provider}")
    return AiGateway(
        client=client,
        timeout_seconds=resolved.timeout_seconds,
        max_attempts=settings.ai_max_attempts,
        first_attempt_timeout_seconds=settings.ai_first_attempt_timeout_seconds,
    )
