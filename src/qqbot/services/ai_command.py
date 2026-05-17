from __future__ import annotations

from dataclasses import dataclass
import re

from qqbot.services.ai_conversation_store import AiConversationStore
from qqbot.services.command_guard import is_direct_command_event, is_likely_command
from qqbot.services.offline_message_gate import is_before_onebot_connect
from qqbot.services.rightcodes_draw_client import (
    looks_like_rightcodes_draw_command,
    looks_like_rightcodes_draw_help_command,
)

QQ_GROUP_MANAGER_USER_IDS = {"2854196310"}


@dataclass(frozen=True, slots=True)
class AiModelCommand:
    action: str
    profile: str | None = None


def should_handle_ai_chat(event, text: str) -> bool:
    prompt = text.strip()
    if not prompt:
        return False
    if is_before_onebot_connect(getattr(event, "time", None)):
        return False
    if is_group_manager_welcome_message(event, prompt):
        return False
    if getattr(event, "message_type", "") != "group" and not hasattr(event, "group_id"):
        if prompt.startswith("/"):
            return False
    if is_likely_command(prompt) or parse_ai_model_command(prompt) is not None:
        return False
    if looks_like_rightcodes_draw_command(prompt) or looks_like_rightcodes_draw_help_command(prompt):
        return True
    return is_direct_command_event(event)


def is_group_manager_welcome_message(event, text: str) -> bool:
    if getattr(event, "message_type", "") != "group" and not hasattr(event, "group_id"):
        return False
    if str(getattr(event, "user_id", "")) not in QQ_GROUP_MANAGER_USER_IDS:
        return False
    normalized = "".join(text.split())
    if "欢迎" not in normalized:
        return False
    return any(marker in normalized for marker in ("加入本群", "加入群聊", "入群"))


def parse_ai_model_command(text: str) -> AiModelCommand | None:
    normalized = text.strip()
    if not normalized:
        return None

    if re.fullmatch(r"(?i)(AI模型|当前AI)", normalized):
        return AiModelCommand(action="status")

    match = re.fullmatch(r"(?i)切换AI\s+(\S+)", normalized)
    if match is None:
        return None
    return AiModelCommand(action="switch", profile=match.group(1).strip())


def build_ai_conversation_key(
    store: AiConversationStore,
    event,
    profile: str,
    scope: str,
) -> str:
    user_id = event.get_user_id()
    if getattr(event, "message_type", "") == "group" or hasattr(event, "group_id"):
        return store.group_user_key(str(getattr(event, "group_id")), user_id, profile, scope)
    return store.private_key(user_id, profile, scope)
