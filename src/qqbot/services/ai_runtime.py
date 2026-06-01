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


OPENROUTER_ICU_PROFILE_HINTS = ("openrouter-icu", "openrouter_icu", "openrouter icu", "icu")
CODEX_EVERYWHERE_PROFILE_HINTS = (
    "codex-everywhere",
    "codex_everywhere",
    "codex everywhere",
    "codex-everywhere.com",
)
RIGHTCODES_PROFILE_HINTS = ("rightcodes", "right.codes")


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
    configured_order = store.get_ai_profile_priority(_default_ai_profile_priority(enabled))
    ordered: list[str] = [profile_name for profile_name in configured_order if profile_name in enabled_names]
    primary = preferred_profile or get_current_ai_profile_name(settings, store, profiles)
    if primary in enabled_names and not ordered:
        ordered.append(primary)
    default_profile = get_default_ai_profile_name(settings)
    if default_profile in enabled_names and default_profile not in ordered:
        ordered.append(default_profile)
    for profile in enabled:
        if profile.name not in ordered:
            ordered.append(profile.name)
    return _sort_profile_names_by_provider_priority(ordered, profiles)


def _default_ai_profile_priority(enabled: list[AiProfile]) -> tuple[str, ...]:
    return tuple(profile.name for profile in sorted(enabled, key=_profile_priority_key))


def _profile_priority_key(profile: AiProfile) -> tuple[int, int, str]:
    provider_key = _profile_provider_priority_key(profile)
    return (provider_key[0], provider_key[1], profile.name)


def _sort_profile_names_by_provider_priority(
    names: list[str],
    profiles: dict[str, AiProfile],
) -> tuple[str, ...]:
    indexed_names = list(enumerate(dict.fromkeys(names)))
    return tuple(
        name
        for _index, name in sorted(
            indexed_names,
            key=lambda item: (*_profile_provider_priority_key(profiles[item[1]]), item[0]),
        )
    )


def _profile_provider_priority_key(profile: AiProfile) -> tuple[int, int]:
    haystack = f"{profile.name} {profile.base_url}".lower()
    if _contains_any(haystack, OPENROUTER_ICU_PROFILE_HINTS):
        return (0, 0)
    if _contains_any(haystack, CODEX_EVERYWHERE_PROFILE_HINTS):
        return (1, 0)
    if _contains_any(haystack, RIGHTCODES_PROFILE_HINTS):
        return (2, 0)
    if profile.model.lower().startswith("gpt-"):
        return (3, 0)
    return (4, 0)


def _contains_any(text: str, hints: tuple[str, ...]) -> bool:
    return any(hint in text for hint in hints)


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
