from __future__ import annotations

from qqbot.config import RuntimeSettings
from qqbot.features.ai.gateway import AiGateway
from qqbot.features.ai.profile_registry import (
    AiProfile,
    list_enabled_profiles,
    load_ai_default_profile_name,
    load_ai_profiles,
    resolve_ai_profile,
)
from qqbot.features.ai.mimo_compatible_client import MimoCompatibleClient
from qqbot.features.ai.openai_compatible_client import OpenAICompatibleClient
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

    if default_profile in enabled_names:
        return default_profile
    if enabled_names:
        return next(profile.name for profile in list_enabled_profiles(profiles))
    return default_profile


def list_ai_profile_fallback_order(
    settings: RuntimeSettings,
    store: SettingsStore,
    profiles: dict[str, AiProfile] | None = None,
    *,
    preferred_profile: str | None = None,
) -> tuple[str, ...]:
    profiles = profiles if profiles is not None else load_ai_profiles(settings.ai_profile_file)
    enabled = list_enabled_profiles(profiles)
    enabled_names = {profile.name for profile in enabled}
    primary = preferred_profile or get_current_ai_profile_name(settings, store, profiles)
    ordered: list[str] = []
    if primary in enabled_names:
        ordered.append(primary)
    for profile in enabled:
        if profile.name not in ordered:
            ordered.append(profile.name)
    return tuple(ordered)


def build_ai_gateway(settings: RuntimeSettings, profile_name: str) -> AiGateway:
    profiles = load_ai_profiles(settings.ai_profile_file)
    resolved = resolve_ai_profile(profiles, profile_name)
    if resolved.provider == "openai_compatible":
        client = OpenAICompatibleClient(
            base_url=resolved.base_url,
            api_key=resolved.api_key,
            model=resolved.model,
            timeout_seconds=resolved.timeout_seconds,
            max_output_tokens=resolved.max_output_tokens,
            supports_vision=resolved.supports_vision,
            extra_body=resolved.extra_body,
        )
    elif resolved.provider in {"xiaomi_mimo", "mimo_compatible"}:
        client = MimoCompatibleClient(
            base_url=resolved.base_url,
            api_key=resolved.api_key,
            model=resolved.model,
            vision_model=resolved.vision_model,
            timeout_seconds=resolved.timeout_seconds,
            max_output_tokens=resolved.max_output_tokens,
            supports_vision=resolved.supports_vision,
        )
    else:
        raise ValueError(f"暂不支持 AI provider：{resolved.provider}")
    return AiGateway(
        client=client,
        timeout_seconds=resolved.timeout_seconds,
        max_attempts=settings.ai_max_attempts,
        first_attempt_timeout_seconds=settings.ai_first_attempt_timeout_seconds,
        profile_name=resolved.name,
    )
