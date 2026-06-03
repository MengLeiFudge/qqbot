from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.config import RuntimeSettings, load_settings


def test_runtime_settings_defaults() -> None:
    settings = RuntimeSettings.from_mapping({})

    assert settings.host == "127.0.0.1"
    assert settings.port == 8080
    assert settings.onebot_ws_path == "/onebot/v11/ws"
    assert settings.onebot_access_token == ""
    assert settings.superusers == set()
    assert settings.author_qq == 0
    assert settings.author_name == "author"
    assert settings.data_root.as_posix().endswith("run")
    assert settings.arc_assets_root.as_posix() == "D:/path/to/Arcaea"
    assert settings.timezone == "Asia/Shanghai"
    assert settings.ai_provider == ""
    assert settings.ai_base_url == ""
    assert settings.ai_model == ""
    assert settings.ai_api_key == ""
    assert settings.ai_timeout_seconds == 45.0
    assert settings.ai_first_attempt_timeout_seconds == 0.0
    assert settings.ai_max_attempts == 2
    assert settings.ai_enabled is False
    assert settings.ai_default_profile == "default"
    assert settings.ai_profile_file.as_posix().endswith("config/qqbot.toml")
    assert settings.ai_max_context_messages == 12
    assert settings.ai_show_metrics is False
    assert settings.ai_bot_name == "QQBot"
    assert settings.ai_group_context_messages == 30
    assert settings.ai_memory_enabled is True
    assert settings.ai_memory_search_limit == 6
    assert settings.ai_memory_context_chars == 1200
    assert settings.ai_embedding_enabled is False
    assert settings.ai_embedding_base_url == ""
    assert settings.ai_embedding_model == "text-embedding-3-small"
    assert settings.ai_embedding_api_key == ""
    assert settings.ai_embedding_api_key_env == ""
    assert settings.ai_embedding_timeout_seconds == 45.0


def test_runtime_settings_parses_superusers_and_token() -> None:
    settings = RuntimeSettings.from_mapping(
        {
            "QQBOT_PORT": "9000",
            "QQBOT_ONEBOT_ACCESS_TOKEN": "secret-token",
            "QQBOT_SUPERUSERS": "10001, 10002 ,,10003",
            "QQBOT_AUTHOR_QQ": "123456789",
            "QQBOT_DATA_ROOT": "D:/project/qqbot/custom-run",
            "QQBOT_ARC_ASSETS_ROOT": "D:/games/arcaea-custom",
            "QQBOT_TIMEZONE": "UTC",
            "QQBOT_AI_PROVIDER": "openai_compatible",
            "QQBOT_AI_BASE_URL": "https://token-plan-cn.xiaomimimo.com/v1",
            "QQBOT_AI_MODEL": "mimo-v2.5-pro",
            "QQBOT_AI_API_KEY": "secret-key",
            "QQBOT_AI_TIMEOUT_SECONDS": "8.5",
            "QQBOT_AI_FIRST_ATTEMPT_TIMEOUT_SECONDS": "2.5",
            "QQBOT_AI_MAX_ATTEMPTS": "3",
            "QQBOT_AI_ENABLED": "true",
            "QQBOT_AI_DEFAULT_PROFILE": "xiaomi",
            "QQBOT_AI_PROFILE_FILE": "D:/project/qqbot/config/ai_providers.toml",
            "QQBOT_AI_MAX_CONTEXT_MESSAGES": "8",
            "QQBOT_AI_SHOW_METRICS": "true",
            "QQBOT_AI_BOT_NAME": "测试棉花糖",
            "QQBOT_AI_GROUP_CONTEXT_MESSAGES": "16",
            "QQBOT_AI_MEMORY_ENABLED": "false",
            "QQBOT_AI_MEMORY_SEARCH_LIMIT": "4",
            "QQBOT_AI_MEMORY_CONTEXT_CHARS": "800",
            "QQBOT_AI_EMBEDDING_ENABLED": "true",
            "QQBOT_AI_EMBEDDING_BASE_URL": "https://api.openai.com/v1",
            "QQBOT_AI_EMBEDDING_MODEL": "text-embedding-3-small",
            "QQBOT_AI_EMBEDDING_API_KEY": "embedding-key",
            "QQBOT_AI_EMBEDDING_API_KEY_ENV": "QQBOT_OPENAI_API_KEY",
            "QQBOT_AI_EMBEDDING_TIMEOUT_SECONDS": "9.5",
        }
    )

    assert settings.port == 9000
    assert settings.onebot_access_token == "secret-token"
    assert settings.superusers == {"10001", "10002", "10003"}
    assert settings.author_qq == 123456789
    assert settings.author_name == "author"
    assert settings.data_root.as_posix().endswith("custom-run")
    assert settings.arc_assets_root.as_posix() == "D:/games/arcaea-custom"
    assert settings.timezone == "UTC"
    assert settings.ai_provider == "openai_compatible"
    assert settings.ai_base_url == "https://token-plan-cn.xiaomimimo.com/v1"
    assert settings.ai_model == "mimo-v2.5-pro"
    assert settings.ai_api_key == "secret-key"
    assert settings.ai_timeout_seconds == 8.5
    assert settings.ai_first_attempt_timeout_seconds == 2.5
    assert settings.ai_max_attempts == 3
    assert settings.ai_enabled is True
    assert settings.ai_default_profile == "xiaomi"
    assert settings.ai_profile_file.as_posix() == "D:/project/qqbot/config/ai_providers.toml"
    assert settings.ai_max_context_messages == 8
    assert settings.ai_show_metrics is True
    assert settings.ai_bot_name == "测试棉花糖"
    assert settings.ai_group_context_messages == 16
    assert settings.ai_memory_enabled is False
    assert settings.ai_memory_search_limit == 4
    assert settings.ai_memory_context_chars == 800
    assert settings.ai_embedding_enabled is True
    assert settings.ai_embedding_base_url == "https://api.openai.com/v1"
    assert settings.ai_embedding_model == "text-embedding-3-small"
    assert settings.ai_embedding_api_key == "embedding-key"
    assert settings.ai_embedding_api_key_env == "QQBOT_OPENAI_API_KEY"
    assert settings.ai_embedding_timeout_seconds == 9.5


def test_load_settings_reads_main_config_and_env_overrides(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_file = tmp_path / "config" / "qqbot.toml"
    config_file.parent.mkdir()
    config_file.write_text(
        """
[bot]
host = "0.0.0.0"
port = 9000
author_qq = 10000
author_name = "配置作者"

[onebot]
ws_path = "/custom/ws"

[paths]
data_root = "./custom-run"
arc_assets_root = "D:/config/arcaea"

[ai]
enabled = true
default_profile = "xiaomi"
max_context_messages = 8
show_metrics = true
bot_name = "配置机器人"
first_attempt_timeout_seconds = 3
max_attempts = 4
embedding_enabled = true
embedding_base_url = "https://api.openai.com/v1"
embedding_model = "text-embedding-3-small"
embedding_api_key_env = "QQBOT_OPENAI_API_KEY"
embedding_timeout_seconds = 10
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("QQBOT_CONFIG_FILE", str(config_file))
    monkeypatch.setenv("QQBOT_PORT", "9100")
    monkeypatch.setenv("QQBOT_AI_BOT_NAME", "环境机器人")

    settings = load_settings()

    assert settings.config_file == config_file
    assert settings.host == "0.0.0.0"
    assert settings.port == 9100
    assert settings.onebot_ws_path == "/custom/ws"
    assert settings.author_qq == 10000
    assert settings.author_name == "配置作者"
    assert settings.data_root.as_posix() == "custom-run"
    assert settings.arc_assets_root.as_posix() == "D:/config/arcaea"
    assert settings.ai_enabled is True
    assert settings.ai_default_profile == "xiaomi"
    assert settings.ai_max_context_messages == 8
    assert settings.ai_show_metrics is True
    assert settings.ai_bot_name == "环境机器人"
    assert settings.ai_first_attempt_timeout_seconds == 3.0
    assert settings.ai_max_attempts == 4
    assert settings.ai_embedding_enabled is True
    assert settings.ai_embedding_base_url == "https://api.openai.com/v1"
    assert settings.ai_embedding_model == "text-embedding-3-small"
    assert settings.ai_embedding_api_key_env == "QQBOT_OPENAI_API_KEY"
    assert settings.ai_embedding_timeout_seconds == 10.0


def test_load_settings_ignores_missing_legacy_ai_profile_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_file = tmp_path / "config" / "qqbot.toml"
    config_file.parent.mkdir()
    config_file.write_text(
        """
[ai]
enabled = true
default_profile = "xiaomi"

[ai.providers.xiaomi]
provider = "xiaomi_mimo"
base_url = "https://api.xiaomimimo.com/v1"
model = "mimo-v2.5-pro"
api_key_env = "QQBOT_AI_KEY_XIAOMI"
""".strip(),
        encoding="utf-8",
    )
    stale_profile_file = tmp_path / "config" / "ai_providers.toml"
    monkeypatch.setenv("QQBOT_CONFIG_FILE", str(config_file))
    monkeypatch.setenv("QQBOT_AI_PROFILE_FILE", str(stale_profile_file))

    settings = load_settings()

    assert settings.ai_profile_file == config_file
