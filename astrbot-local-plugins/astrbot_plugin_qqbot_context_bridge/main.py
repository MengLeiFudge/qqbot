from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.event import filter
from astrbot.core.agent.message import TextPart
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star, register


DEFAULT_MAX_MESSAGES = 12
DEFAULT_MAX_CHARS = 1800
BOT1_ID = "1443944862"
BOT2_ID = "2629227874"
DOMAIN_HINTS = {
    "1035445959": (
        "本群是星环/OrbitalRing 模组群。三阶、二阶、功率、休谟值、火箭、球、"
        "配方、建筑和机制类问题必须优先依据 OrbitalRing-MOD 证据或 bot1 已沉淀"
        "上下文回答；证据不足就直说证据不足，不要按通用游戏机制或其他模组经验补猜。"
    )
}


@dataclass(frozen=True, slots=True)
class BridgeConfig:
    enabled_groups: set[str]
    max_messages: int
    max_chars: int
    context_root: Path


@register(
    "astrbot_plugin_qqbot_context_bridge",
    "MengLei",
    "把 NoneBot2 公开群上下文桥接到 AstrBot 本轮 LLM 请求。",
    "0.1.2",
)
class QQBotContextBridgePlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self._config = load_bridge_config(config)
        logger.info(
            "[QQBotContextBridge] loaded: groups=%s max_messages=%s max_chars=%s root=%s",
            format_enabled_groups(self._config.enabled_groups),
            self._config.max_messages,
            self._config.max_chars,
            self._config.context_root,
        )

    @filter.on_llm_request(desc="在 AstrBot 调用 LLM 前，按当前群号读取 bot1 公开群上下文并临时注入本轮请求。")
    async def inject_bot1_group_context(self, event: AstrMessageEvent, req: ProviderRequest):
        group_id = str(event.get_group_id() or "")
        if self._config.enabled_groups and group_id not in self._config.enabled_groups:
            return
        injection = build_group_context_injection(group_id, self._config)
        if not injection:
            return
        req.extra_user_content_parts.append(TextPart(text=injection).mark_as_temp())
        logger.info(
            "[QQBotContextBridge] injected bot1 context: group=%s chars=%s",
            group_id,
            len(injection),
        )


def load_bridge_config(config=None) -> BridgeConfig:
    enabled_groups = parse_group_ids(get_config_value(config, "enabled_groups", ""))
    max_messages = clamp_int(
        get_config_value(config, "max_messages", DEFAULT_MAX_MESSAGES),
        default=DEFAULT_MAX_MESSAGES,
        minimum=1,
        maximum=40,
    )
    max_chars = clamp_int(
        get_config_value(config, "max_chars", DEFAULT_MAX_CHARS),
        default=DEFAULT_MAX_CHARS,
        minimum=400,
        maximum=6000,
    )
    return BridgeConfig(
        enabled_groups=enabled_groups,
        max_messages=max_messages,
        max_chars=max_chars,
        context_root=resolve_bot1_context_root(),
    )


def format_enabled_groups(enabled_groups: set[str]) -> str:
    if not enabled_groups:
        return "*"
    return ",".join(sorted(enabled_groups))


def get_config_value(config, key: str, default):
    if config is None:
        return default
    try:
        return config.get(key, default)
    except Exception:
        return default


def parse_group_ids(raw: object) -> set[str]:
    if isinstance(raw, (list, tuple, set)):
        values = raw
    else:
        values = str(raw or "").replace("，", ",").split(",")
    groups: set[str] = set()
    for value in values:
        group_id = str(value).strip()
        if group_id.isdigit():
            groups.add(group_id)
    return groups


def clamp_int(raw: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def resolve_bot1_context_root() -> Path:
    astrbot_root = Path(os.environ.get("ASTRBOT_ROOT", "")).resolve()
    if astrbot_root.name == "astrbot" and astrbot_root.parent.name == "data":
        workspace_root = astrbot_root.parent.parent
    else:
        cwd = Path.cwd().resolve()
        if cwd.name == "qqbot":
            workspace_root = cwd
        elif cwd.name == "astrbot" and cwd.parent.name == "data":
            workspace_root = cwd.parent.parent
        else:
            workspace_root = cwd
    return workspace_root / "data" / "nonebot2" / "run" / "ai" / "group_context"


def build_group_context_injection(group_id: str, config: BridgeConfig) -> str:
    context_file = safe_group_context_file(config.context_root, group_id)
    if context_file is None or not context_file.is_file():
        logger.debug("[QQBotContextBridge] bot1 context not found: group=%s", group_id)
        return ""
    records = load_group_context_records(context_file)
    if not records:
        return ""
    lines = [
        "bot1/NoneBot2 已沉淀的同群公开上下文，仅作为事实参考，不要向用户提到内部桥接：",
    ]
    domain_hint = DOMAIN_HINTS.get(group_id)
    if domain_hint:
        lines.append(f"领域规则：{domain_hint}")
    lines.append("最近公开群聊：")
    for record in records[-config.max_messages :]:
        line = format_context_record(record)
        if line:
            lines.append(line)
    return trim_text("\n".join(lines), config.max_chars)


def safe_group_context_file(context_root: Path, group_id: str) -> Path | None:
    if not group_id.isdigit():
        return None
    context_root = context_root.resolve()
    path = (context_root / f"{group_id}.json").resolve()
    try:
        path.relative_to(context_root)
    except ValueError:
        return None
    return path


def load_group_context_records(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        logger.warning("[QQBotContextBridge] failed to read bot1 context %s: %s", path, exc)
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def format_context_record(record: dict[str, Any]) -> str:
    user_id = str(record.get("user_id") or "").strip()
    sender_name = str(record.get("sender_name") or user_id or "unknown").strip()
    text = " ".join(str(record.get("text") or "").split())
    if not text:
        return ""
    speaker = "bot1" if user_id == BOT1_ID else "bot2" if user_id == BOT2_ID else sender_name
    message_id = str(record.get("message_id") or "").strip()
    suffix = f" #{message_id}" if message_id else ""
    return f"- {speaker}{suffix}: {text}"


def trim_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 12)].rstrip() + "\n...（已截断）"
