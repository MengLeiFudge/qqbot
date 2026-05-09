from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any
import tomllib

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080
DEFAULT_ONEBOT_WS_PATH = "/onebot/v11/ws"
DEFAULT_COMMAND_START = "/"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_AUTHOR_QQ = 0
DEFAULT_AUTHOR_NAME = "author"
DEFAULT_CONFIG_FILE = PROJECT_ROOT / "config" / "qqbot.toml"
LEGACY_AI_PROFILE_FILE = PROJECT_ROOT / "config" / "ai_providers.toml"
DEFAULT_DATA_ROOT = PROJECT_ROOT / "run"
DEFAULT_ARC_ASSETS_ROOT = Path("D:/path/to/Arcaea")
DEFAULT_ARCAEA_RECORD_ROOT = Path("D:/path/to/arcaeaRecord")
DEFAULT_ARCAEA_RECORD_MAVEN = (
    "C:/path/to/maven/bin/mvn.cmd"
)
DEFAULT_ARCAEA_RECORD_JAVA_HOME = "C:/path/to/jdk"
DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_AI_TIMEOUT_SECONDS = 45.0
DEFAULT_AI_FIRST_ATTEMPT_TIMEOUT_SECONDS = 0.0
DEFAULT_AI_MAX_ATTEMPTS = 2
DEFAULT_AI_PROFILE_FILE = DEFAULT_CONFIG_FILE
DEFAULT_AI_DEFAULT_PROFILE = "default"
DEFAULT_AI_MAX_CONTEXT_MESSAGES = 12
DEFAULT_AI_BOT_NAME = "QQBot"
DEFAULT_AI_GROUP_CONTEXT_MESSAGES = 30
DEFAULT_AI_MEMORY_ENABLED = True
DEFAULT_AI_MEMORY_SEARCH_LIMIT = 6
DEFAULT_AI_MEMORY_CONTEXT_CHARS = 1200
DEFAULT_AI_EMBEDDING_ENABLED = False
DEFAULT_AI_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_AI_EMBEDDING_TIMEOUT_SECONDS = 45.0


def _parse_csv(raw_value: str) -> set[str]:
    return {item.strip() for item in raw_value.split(",") if item.strip()}


def _parse_bool(raw_value: str, default: bool = False) -> bool:
    normalized = raw_value.strip().lower()
    if not normalized:
        return default
    return normalized in {"1", "true", "yes", "on", "y"}


@dataclass(slots=True)
class RuntimeSettings:
    config_file: Path = DEFAULT_CONFIG_FILE
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    onebot_ws_path: str = DEFAULT_ONEBOT_WS_PATH
    onebot_access_token: str = ""
    superusers: set[str] = field(default_factory=set)
    command_start: str = DEFAULT_COMMAND_START
    log_level: str = DEFAULT_LOG_LEVEL
    author_qq: int = DEFAULT_AUTHOR_QQ
    author_name: str = DEFAULT_AUTHOR_NAME
    data_root: Path = DEFAULT_DATA_ROOT
    arc_assets_root: Path = DEFAULT_ARC_ASSETS_ROOT
    arcaea_record_root: Path = DEFAULT_ARCAEA_RECORD_ROOT
    arcaea_record_maven: str = DEFAULT_ARCAEA_RECORD_MAVEN
    arcaea_record_java_home: str = DEFAULT_ARCAEA_RECORD_JAVA_HOME
    timezone: str = DEFAULT_TIMEZONE
    ai_provider: str = ""
    ai_base_url: str = ""
    ai_model: str = ""
    ai_api_key: str = ""
    ai_timeout_seconds: float = DEFAULT_AI_TIMEOUT_SECONDS
    ai_first_attempt_timeout_seconds: float = DEFAULT_AI_FIRST_ATTEMPT_TIMEOUT_SECONDS
    ai_max_attempts: int = DEFAULT_AI_MAX_ATTEMPTS
    ai_enabled: bool = False
    ai_default_profile: str = DEFAULT_AI_DEFAULT_PROFILE
    ai_profile_file: Path = DEFAULT_AI_PROFILE_FILE
    ai_max_context_messages: int = DEFAULT_AI_MAX_CONTEXT_MESSAGES
    ai_show_metrics: bool = False
    ai_bot_name: str = DEFAULT_AI_BOT_NAME
    ai_group_context_messages: int = DEFAULT_AI_GROUP_CONTEXT_MESSAGES
    ai_memory_enabled: bool = DEFAULT_AI_MEMORY_ENABLED
    ai_memory_search_limit: int = DEFAULT_AI_MEMORY_SEARCH_LIMIT
    ai_memory_context_chars: int = DEFAULT_AI_MEMORY_CONTEXT_CHARS
    ai_embedding_enabled: bool = DEFAULT_AI_EMBEDDING_ENABLED
    ai_embedding_base_url: str = ""
    ai_embedding_model: str = DEFAULT_AI_EMBEDDING_MODEL
    ai_embedding_api_key: str = ""
    ai_embedding_api_key_env: str = ""
    ai_embedding_timeout_seconds: float = DEFAULT_AI_EMBEDDING_TIMEOUT_SECONDS

    @classmethod
    def from_mapping(cls, mapping: dict[str, str]) -> "RuntimeSettings":
        # 统一从环境变量风格的键读取，避免后续脚本和代码各自维护一套命名。
        return cls(
            config_file=Path(mapping.get("QQBOT_CONFIG_FILE", str(DEFAULT_CONFIG_FILE))),
            host=mapping.get("QQBOT_HOST", DEFAULT_HOST),
            port=int(mapping.get("QQBOT_PORT", str(DEFAULT_PORT))),
            onebot_ws_path=mapping.get("QQBOT_ONEBOT_WS_PATH", DEFAULT_ONEBOT_WS_PATH),
            onebot_access_token=mapping.get(
                "QQBOT_ONEBOT_ACCESS_TOKEN",
                "",
            ),
            superusers=_parse_csv(mapping.get("QQBOT_SUPERUSERS", "")),
            command_start=mapping.get("QQBOT_COMMAND_START", DEFAULT_COMMAND_START),
            log_level=mapping.get("QQBOT_LOG_LEVEL", DEFAULT_LOG_LEVEL),
            author_qq=int(mapping.get("QQBOT_AUTHOR_QQ", str(DEFAULT_AUTHOR_QQ))),
            author_name=mapping.get("QQBOT_AUTHOR_NAME", DEFAULT_AUTHOR_NAME),
            data_root=Path(mapping.get("QQBOT_DATA_ROOT", str(DEFAULT_DATA_ROOT))),
            arc_assets_root=Path(
                mapping.get("QQBOT_ARC_ASSETS_ROOT", str(DEFAULT_ARC_ASSETS_ROOT))
            ),
            arcaea_record_root=Path(
                mapping.get("QQBOT_ARCAEA_RECORD_ROOT", str(DEFAULT_ARCAEA_RECORD_ROOT))
            ),
            arcaea_record_maven=mapping.get(
                "QQBOT_ARCAEA_RECORD_MAVEN",
                DEFAULT_ARCAEA_RECORD_MAVEN,
            ),
            arcaea_record_java_home=mapping.get(
                "QQBOT_ARCAEA_RECORD_JAVA_HOME",
                DEFAULT_ARCAEA_RECORD_JAVA_HOME,
            ),
            timezone=mapping.get("QQBOT_TIMEZONE", DEFAULT_TIMEZONE),
            ai_provider=mapping.get("QQBOT_AI_PROVIDER", ""),
            ai_base_url=mapping.get("QQBOT_AI_BASE_URL", ""),
            ai_model=mapping.get("QQBOT_AI_MODEL", ""),
            ai_api_key=mapping.get("QQBOT_AI_API_KEY", ""),
            ai_timeout_seconds=float(
                mapping.get("QQBOT_AI_TIMEOUT_SECONDS", str(DEFAULT_AI_TIMEOUT_SECONDS))
            ),
            ai_first_attempt_timeout_seconds=float(
                mapping.get(
                    "QQBOT_AI_FIRST_ATTEMPT_TIMEOUT_SECONDS",
                    str(DEFAULT_AI_FIRST_ATTEMPT_TIMEOUT_SECONDS),
                )
            ),
            ai_max_attempts=int(mapping.get("QQBOT_AI_MAX_ATTEMPTS", str(DEFAULT_AI_MAX_ATTEMPTS))),
            ai_enabled=_parse_bool(mapping.get("QQBOT_AI_ENABLED", ""), default=False),
            ai_default_profile=mapping.get(
                "QQBOT_AI_DEFAULT_PROFILE",
                DEFAULT_AI_DEFAULT_PROFILE,
            ),
            ai_profile_file=Path(
                mapping.get("QQBOT_AI_PROFILE_FILE", str(DEFAULT_AI_PROFILE_FILE))
            ),
            ai_max_context_messages=int(
                mapping.get(
                    "QQBOT_AI_MAX_CONTEXT_MESSAGES",
                    str(DEFAULT_AI_MAX_CONTEXT_MESSAGES),
                )
            ),
            ai_show_metrics=_parse_bool(
                mapping.get("QQBOT_AI_SHOW_METRICS", ""),
                default=False,
            ),
            ai_bot_name=mapping.get("QQBOT_AI_BOT_NAME", DEFAULT_AI_BOT_NAME),
            ai_group_context_messages=int(
                mapping.get(
                    "QQBOT_AI_GROUP_CONTEXT_MESSAGES",
                    str(DEFAULT_AI_GROUP_CONTEXT_MESSAGES),
                )
            ),
            ai_memory_enabled=_parse_bool(
                mapping.get(
                    "QQBOT_AI_MEMORY_ENABLED",
                    "true" if DEFAULT_AI_MEMORY_ENABLED else "false",
                ),
                default=DEFAULT_AI_MEMORY_ENABLED,
            ),
            ai_memory_search_limit=int(
                mapping.get(
                    "QQBOT_AI_MEMORY_SEARCH_LIMIT",
                    str(DEFAULT_AI_MEMORY_SEARCH_LIMIT),
                )
            ),
            ai_memory_context_chars=int(
                mapping.get(
                    "QQBOT_AI_MEMORY_CONTEXT_CHARS",
                    str(DEFAULT_AI_MEMORY_CONTEXT_CHARS),
                )
            ),
            ai_embedding_enabled=_parse_bool(
                mapping.get(
                    "QQBOT_AI_EMBEDDING_ENABLED",
                    "true" if DEFAULT_AI_EMBEDDING_ENABLED else "false",
                ),
                default=DEFAULT_AI_EMBEDDING_ENABLED,
            ),
            ai_embedding_base_url=mapping.get("QQBOT_AI_EMBEDDING_BASE_URL", ""),
            ai_embedding_model=mapping.get(
                "QQBOT_AI_EMBEDDING_MODEL",
                DEFAULT_AI_EMBEDDING_MODEL,
            ),
            ai_embedding_api_key=mapping.get("QQBOT_AI_EMBEDDING_API_KEY", ""),
            ai_embedding_api_key_env=mapping.get("QQBOT_AI_EMBEDDING_API_KEY_ENV", ""),
            ai_embedding_timeout_seconds=float(
                mapping.get(
                    "QQBOT_AI_EMBEDDING_TIMEOUT_SECONDS",
                    str(DEFAULT_AI_EMBEDDING_TIMEOUT_SECONDS),
                )
            ),
        )

    @property
    def onebot_ws_url(self) -> str:
        return f"ws://{self.host}:{self.port}{self.onebot_ws_path}"


def load_settings() -> RuntimeSettings:
    env_mapping = dict(os.environ)
    config_file = Path(env_mapping.get("QQBOT_CONFIG_FILE", str(DEFAULT_CONFIG_FILE)))
    config_mapping = _load_config_mapping(config_file)
    _drop_missing_legacy_ai_profile_file(env_mapping, config_file)
    if (
        "QQBOT_AI_PROFILE_FILE" not in env_mapping
        and "QQBOT_AI_PROFILE_FILE" not in config_mapping
        and config_file.exists()
    ):
        config_mapping["QQBOT_AI_PROFILE_FILE"] = str(config_file)
    if (
        "QQBOT_AI_PROFILE_FILE" not in env_mapping
        and "QQBOT_AI_PROFILE_FILE" not in config_mapping
        and not config_file.exists()
        and LEGACY_AI_PROFILE_FILE.exists()
    ):
        config_mapping["QQBOT_AI_PROFILE_FILE"] = str(LEGACY_AI_PROFILE_FILE)
    return RuntimeSettings.from_mapping({**config_mapping, **env_mapping})


def _drop_missing_legacy_ai_profile_file(env_mapping: dict[str, str], config_file: Path) -> None:
    raw_profile_file = env_mapping.get("QQBOT_AI_PROFILE_FILE")
    if not raw_profile_file:
        return
    profile_file = Path(raw_profile_file)
    if profile_file.exists():
        return
    if profile_file.name != LEGACY_AI_PROFILE_FILE.name:
        return
    if config_file.exists():
        env_mapping.pop("QQBOT_AI_PROFILE_FILE", None)


def _load_config_mapping(config_file: Path) -> dict[str, str]:
    if not config_file.exists():
        return {}
    data = tomllib.loads(config_file.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}

    mapping: dict[str, str] = {"QQBOT_CONFIG_FILE": str(config_file)}
    _copy_section(
        mapping,
        data.get("bot"),
        {
            "host": "QQBOT_HOST",
            "port": "QQBOT_PORT",
            "command_start": "QQBOT_COMMAND_START",
            "log_level": "QQBOT_LOG_LEVEL",
            "author_qq": "QQBOT_AUTHOR_QQ",
            "author_name": "QQBOT_AUTHOR_NAME",
            "timezone": "QQBOT_TIMEZONE",
        },
    )
    _copy_section(
        mapping,
        data.get("onebot"),
        {
            "ws_path": "QQBOT_ONEBOT_WS_PATH",
            "access_token": "QQBOT_ONEBOT_ACCESS_TOKEN",
        },
    )
    _copy_section(
        mapping,
        data.get("paths"),
        {
            "data_root": "QQBOT_DATA_ROOT",
            "arc_assets_root": "QQBOT_ARC_ASSETS_ROOT",
            "arcaea_record_root": "QQBOT_ARCAEA_RECORD_ROOT",
            "arcaea_record_maven": "QQBOT_ARCAEA_RECORD_MAVEN",
            "arcaea_record_java_home": "QQBOT_ARCAEA_RECORD_JAVA_HOME",
        },
    )
    _copy_section(
        mapping,
        data.get("ai"),
        {
            "enabled": "QQBOT_AI_ENABLED",
            "default_profile": "QQBOT_AI_DEFAULT_PROFILE",
            "profile_file": "QQBOT_AI_PROFILE_FILE",
            "max_context_messages": "QQBOT_AI_MAX_CONTEXT_MESSAGES",
            "group_context_messages": "QQBOT_AI_GROUP_CONTEXT_MESSAGES",
            "memory_enabled": "QQBOT_AI_MEMORY_ENABLED",
            "memory_search_limit": "QQBOT_AI_MEMORY_SEARCH_LIMIT",
            "memory_context_chars": "QQBOT_AI_MEMORY_CONTEXT_CHARS",
            "show_metrics": "QQBOT_AI_SHOW_METRICS",
            "bot_name": "QQBOT_AI_BOT_NAME",
            "timeout_seconds": "QQBOT_AI_TIMEOUT_SECONDS",
            "first_attempt_timeout_seconds": "QQBOT_AI_FIRST_ATTEMPT_TIMEOUT_SECONDS",
            "max_attempts": "QQBOT_AI_MAX_ATTEMPTS",
            "provider": "QQBOT_AI_PROVIDER",
            "base_url": "QQBOT_AI_BASE_URL",
            "model": "QQBOT_AI_MODEL",
            "embedding_enabled": "QQBOT_AI_EMBEDDING_ENABLED",
            "embedding_base_url": "QQBOT_AI_EMBEDDING_BASE_URL",
            "embedding_model": "QQBOT_AI_EMBEDDING_MODEL",
            "embedding_api_key_env": "QQBOT_AI_EMBEDDING_API_KEY_ENV",
            "embedding_timeout_seconds": "QQBOT_AI_EMBEDDING_TIMEOUT_SECONDS",
        },
    )
    return mapping


def _copy_section(
    mapping: dict[str, str],
    section: object,
    key_map: dict[str, str],
) -> None:
    if not isinstance(section, dict):
        return
    for config_key, env_key in key_map.items():
        if config_key not in section:
            continue
        value = section[config_key]
        if isinstance(value, (dict, list)):
            continue
        mapping[env_key] = _stringify_config_value(value)


def _stringify_config_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
