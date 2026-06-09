from __future__ import annotations

import os
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.event import filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star, register
from astrbot.core.agent.message import TextPart
from astrbot.core.star.filter.event_message_type import EventMessageType

from .logic import TwinInteractionConfig
from .logic import TwinProfile
from .logic import build_direct_twin_prompt
from .logic import build_twin_injection
from .logic import clamp_int
from .logic import group_enabled
from .logic import is_bot_sender_id
from .logic import parse_group_ids
from .logic import read_bool
from .logic import read_profile
from .logic import read_profile_for_self_id
from .logic import should_handle_direct_twin_request


PROFILE_ENV = "QQBOT_ASTRBOT_PROFILE"
DEFAULT_MAX_CONTEXT_MESSAGES = 4
DEFAULT_MAX_CONTEXT_CHARS = 1200


@register(
    "astrbot_plugin_twin_interaction",
    "local",
    "Twin-aware prompt injection and explicit interaction handling for angel/demon QQBot profiles.",
    "0.1.1",
)
class TwinInteractionPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self._config = load_twin_config(config)
        self._fallback_profile = os.environ.get(PROFILE_ENV, "demon")
        self._profile = read_profile(self._fallback_profile)
        logger.info(
            "[TwinInteraction] loaded: profile=%s groups=%s direct=%s max_messages=%s max_chars=%s",
            self._fallback_profile,
            "*" if not self._config.enabled_groups else ",".join(sorted(self._config.enabled_groups)),
            self._config.direct_handler_enabled,
            self._config.max_context_messages,
            self._config.max_context_chars,
        )

    @filter.on_llm_request()
    async def inject_twin_context(self, event: AstrMessageEvent, req: ProviderRequest):
        profile = self._profile_for_event(event)
        if is_bot_sender(event, profile):
            return
        group_id = str(event.get_group_id() or "")
        if not event.is_private_chat() and not group_enabled(group_id, self._config.enabled_groups):
            return
        text = str(event.get_message_str() or "")
        injection = build_twin_injection(
            text=text,
            group_id=group_id,
            profile=profile,
            config=self._config,
        )
        if not injection:
            return
        req.extra_user_content_parts.append(TextPart(text=injection).mark_as_temp())
        logger.info(
            "[TwinInteraction] injected twin context: group=%s chars=%s",
            group_id or "private",
            len(injection),
        )

    @filter.event_message_type(EventMessageType.ALL)
    async def handle_explicit_twin_request(self, event: AstrMessageEvent):
        if not self._config.direct_handler_enabled:
            return
        profile = self._profile_for_event(event)
        if is_bot_sender(event, profile):
            return
        group_id = str(event.get_group_id() or "")
        if not event.is_private_chat() and not group_enabled(group_id, self._config.enabled_groups):
            return
        text = str(event.get_message_str() or "")
        if not should_handle_direct_twin_request(
            text,
            profile,
            is_private=event.is_private_chat(),
            is_at_or_wake_command=bool(getattr(event, "is_at_or_wake_command", False)),
        ):
            return
        prompt = build_direct_twin_prompt(
            text=text,
            group_id=group_id,
            profile=profile,
            config=self._config,
        )
        yield event.request_llm(prompt=prompt, contexts=[])
        event.stop_event()

    def _profile_for_event(self, event: AstrMessageEvent) -> TwinProfile:
        return read_profile_for_self_id(str(event.get_self_id() or ""), self._fallback_profile)


def load_twin_config(config=None) -> TwinInteractionConfig:
    return TwinInteractionConfig(
        enabled_groups=parse_group_ids(get_config_value(config, "enabled_groups", "")),
        direct_handler_enabled=read_bool(get_config_value(config, "direct_handler_enabled", True), default=True),
        max_context_messages=clamp_int(
            get_config_value(config, "max_context_messages", DEFAULT_MAX_CONTEXT_MESSAGES),
            default=DEFAULT_MAX_CONTEXT_MESSAGES,
            minimum=0,
            maximum=20,
        ),
        max_context_chars=clamp_int(
            get_config_value(config, "max_context_chars", DEFAULT_MAX_CONTEXT_CHARS),
            default=DEFAULT_MAX_CONTEXT_CHARS,
            minimum=400,
            maximum=4000,
        ),
        context_root=resolve_public_group_context_root(),
    )


def get_config_value(config, key: str, default):
    if config is None:
        return default
    try:
        return config.get(key, default)
    except Exception:
        return default


def resolve_public_group_context_root() -> Path:
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


def is_bot_sender(event: AstrMessageEvent, profile: TwinProfile) -> bool:
    return is_bot_sender_id(str(event.get_sender_id() or ""), str(event.get_self_id() or ""), profile)
