from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.ai_profile_registry import (
    list_enabled_profiles,
    load_ai_default_profile_name,
    load_ai_profiles,
    resolve_ai_profile,
)


def write_profiles(path: Path) -> None:
    path.write_text(
        """
model_provider = "xiaomi"

[model_providers.xiaomi]
provider = "openai_compatible"
base_url = "https://example.com/v1"
model = "mimo-v2.5-pro"
vision_model = "mimo-v2.5"
api_key_env = "QQBOT_AI_KEY_XIAOMI"
timeout_seconds = 9
max_output_tokens = 2048
supports_vision = true
note = "xiaomi"

[model_providers.xiaomi.extra_body]
reasoning = { effort = "low" }
fast = true

[model_providers.disabled]
enabled = false
provider = "openai_compatible"
base_url = "https://disabled.example/v1"
model = "disabled"
api_key_env = "QQBOT_AI_KEY_DISABLED"
""".strip(),
        encoding="utf-8",
    )


def test_load_ai_profiles_and_resolve_enabled_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_file = tmp_path / "ai_providers.toml"
    write_profiles(profile_file)
    monkeypatch.setenv("QQBOT_AI_KEY_XIAOMI", "secret")

    profiles = load_ai_profiles(profile_file)
    enabled = list_enabled_profiles(profiles)
    resolved = resolve_ai_profile(profiles, "xiaomi")

    assert set(profiles) == {"xiaomi", "disabled"}
    assert [profile.name for profile in enabled] == ["xiaomi"]
    assert resolved.name == "xiaomi"
    assert resolved.base_url == "https://example.com/v1"
    assert resolved.model == "mimo-v2.5-pro"
    assert resolved.vision_model == "mimo-v2.5"
    assert resolved.api_key == "secret"
    assert resolved.timeout_seconds == 9.0
    assert resolved.max_output_tokens == 2048
    assert resolved.supports_vision is True
    assert resolved.extra_body == {"reasoning": {"effort": "low"}, "fast": True}
    assert load_ai_default_profile_name(profile_file) == "xiaomi"


def test_resolve_ai_profile_requires_secret_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_file = tmp_path / "ai_providers.toml"
    write_profiles(profile_file)
    monkeypatch.delenv("QQBOT_AI_KEY_XIAOMI", raising=False)
    profiles = load_ai_profiles(profile_file)

    with pytest.raises(ValueError, match="缺少 AI profile 密钥环境变量"):
        resolve_ai_profile(profiles, "xiaomi")


def test_resolve_ai_profile_rejects_disabled_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_file = tmp_path / "ai_providers.toml"
    write_profiles(profile_file)
    monkeypatch.setenv("QQBOT_AI_KEY_DISABLED", "secret")
    profiles = load_ai_profiles(profile_file)

    with pytest.raises(ValueError, match="AI profile 已禁用"):
        resolve_ai_profile(profiles, "disabled")


def test_load_ai_profiles_keeps_legacy_profiles_format(tmp_path: Path) -> None:
    profile_file = tmp_path / "ai_profiles.toml"
    profile_file.write_text(
        """
[profiles.legacy]
provider = "openai_compatible"
base_url = "https://legacy.example/v1"
model = "legacy-model"
api_key_env = "QQBOT_AI_KEY_LEGACY"
""".strip(),
        encoding="utf-8",
    )

    profiles = load_ai_profiles(profile_file)

    assert set(profiles) == {"legacy"}
    assert profiles["legacy"].base_url == "https://legacy.example/v1"


def test_load_ai_profiles_accepts_main_qqbot_config_format(tmp_path: Path) -> None:
    profile_file = tmp_path / "qqbot.toml"
    profile_file.write_text(
        """
[ai]
default_profile = "main"

[ai.providers.main]
provider = "openai_compatible"
base_url = "https://main.example/v1"
model = "main-model"
vision_model = "main-vision-model"
api_key_env = "QQBOT_AI_KEY_MAIN"
timeout_seconds = 12
max_output_tokens = 3072
supports_vision = true
""".strip(),
        encoding="utf-8",
    )

    profiles = load_ai_profiles(profile_file)

    assert load_ai_default_profile_name(profile_file) == "main"
    assert set(profiles) == {"main"}
    assert profiles["main"].base_url == "https://main.example/v1"
    assert profiles["main"].vision_model == "main-vision-model"
    assert profiles["main"].timeout_seconds == 12
    assert profiles["main"].max_output_tokens == 3072
    assert profiles["main"].supports_vision is True


def test_example_uses_openrouter_icu_as_default_profile() -> None:
    profile_file = ROOT / "config" / "qqbot.toml.example"

    profiles = load_ai_profiles(profile_file)
    extra_body = profiles["openrouter-icu"].extra_body

    assert load_ai_default_profile_name(profile_file) == "openrouter-icu"
    assert extra_body is not None
    assert extra_body["reasoning"] == {"effort": "high"}
    assert "codex-everywhere" not in profiles
    assert "openrouter" not in profiles


def test_resolve_ai_profile_accepts_direct_key_in_api_key_env_field(
    tmp_path: Path,
) -> None:
    profile_file = tmp_path / "ai_providers.toml"
    profile_file.write_text(
        """
[model_providers.direct]
provider = "openai_compatible"
base_url = "https://direct.example/v1"
model = "direct-model"
api_key_env = "sk-test-direct-key"
""".strip(),
        encoding="utf-8",
    )

    profiles = load_ai_profiles(profile_file)
    resolved = resolve_ai_profile(profiles, "direct")

    assert resolved.api_key == "sk-test-direct-key"


def test_load_ai_profiles_accepts_xiaomi_mimo_provider(tmp_path: Path) -> None:
    profile_file = tmp_path / "ai_providers.toml"
    profile_file.write_text(
        """
[model_providers.xiaomi]
provider = "xiaomi_mimo"
base_url = "https://api.xiaomimimo.com/v1"
model = "mimo-v2.5-pro"
vision_model = "mimo-v2.5"
api_key_env = "tp-test-direct-key"
""".strip(),
        encoding="utf-8",
    )

    profiles = load_ai_profiles(profile_file)
    resolved = resolve_ai_profile(profiles, "xiaomi")

    assert resolved.provider == "xiaomi_mimo"
    assert resolved.base_url == "https://api.xiaomimimo.com/v1"
    assert resolved.vision_model == "mimo-v2.5"
