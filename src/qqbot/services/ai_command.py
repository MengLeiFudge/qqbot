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


@dataclass(frozen=True, slots=True)
class AiOutputModeCommand:
    action: str
    scope: str = "auto"
    mode: str | None = None


def should_handle_ai_chat(
    event,
    text: str,
    *,
    proactive_enabled: bool = False,
    bot_names: tuple[str, ...] = (),
) -> bool:
    prompt = text.strip()
    if not prompt:
        if getattr(event, "message_type", "") != "group" and not hasattr(event, "group_id"):
            return False
        return is_direct_command_event(event)
    if is_before_onebot_connect(getattr(event, "time", None)):
        return False
    if is_group_manager_welcome_message(event, prompt):
        return False
    if getattr(event, "message_type", "") != "group" and not hasattr(event, "group_id"):
        if prompt.startswith("/"):
            return False
        if (
            is_likely_command(prompt)
            or parse_ai_model_command(prompt) is not None
        ):
            return False
        if parse_ai_output_mode_command(prompt) is not None:
            return False
        return True
    if (
        is_likely_command(prompt)
        or parse_ai_model_command(prompt) is not None
        or parse_ai_output_mode_command(prompt) is not None
    ):
        return False
    if looks_like_rightcodes_draw_command(prompt) or looks_like_rightcodes_draw_help_command(prompt):
        return True
    if is_direct_command_event(event):
        return True
    return proactive_enabled and looks_like_ai_proactive_trigger(prompt, bot_names=bot_names)


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


def parse_ai_output_mode_command(text: str) -> AiOutputModeCommand | None:
    normalized = re.sub(r"\s+", "", text.strip())
    if not normalized:
        return None

    if normalized in {"AI回复模式", "AI输出模式", "回复模式", "输出模式"}:
        return AiOutputModeCommand(action="status")

    scope = "auto"
    rest = normalized
    if rest.startswith("本群"):
        scope = "group"
        rest = rest.removeprefix("本群")
    elif rest.startswith("我的"):
        scope = "user"
        rest = rest.removeprefix("我的")

    if rest in {
        "AI语音模式",
        "AI回复语音模式",
        "切换语音",
        "切到语音",
        "切换到语音",
        "语音模式",
        "语音回复",
    }:
        return AiOutputModeCommand(action="set", scope=scope, mode="voice")
    if rest in {
        "AI文字模式",
        "AI文本模式",
        "AI回复文字模式",
        "AI回复文本模式",
        "切换文字",
        "切换文本",
        "切到文字",
        "切到文本",
        "切回文字",
        "切回文本",
        "切换到文字",
        "切换到文本",
        "文字模式",
        "文本模式",
        "文字回复",
        "文本回复",
    }:
        return AiOutputModeCommand(action="set", scope=scope, mode="text")
    return None


def looks_like_ai_proactive_trigger(text: str, *, bot_names: tuple[str, ...] = ()) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    compact = re.sub(r"\s+", "", normalized)
    lower = compact.lower()

    names = _build_ai_proactive_names(bot_names)
    if any(name and name in lower for name in names):
        return True

    question_markers = ("?", "？", "吗", "么", "呢")
    help_markers = (
        "有人知道",
        "有谁知道",
        "谁知道",
        "求助",
        "请问",
        "问一下",
        "能不能帮",
        "帮我看",
        "怎么",
        "为什么",
        "咋",
    )
    if any(marker in compact for marker in help_markers) and (
        any(marker in compact for marker in question_markers)
        or len(compact) >= 8
    ):
        return True
    return False


def _build_ai_proactive_names(bot_names: tuple[str, ...]) -> tuple[str, ...]:
    names = {"棉花糖", "萌萌棉花糖", "qqbot"}
    for name in bot_names:
        cleaned = re.sub(r"\s+", "", name.strip()).lower()
        if cleaned:
            names.add(cleaned)
    return tuple(sorted(names, key=len, reverse=True))


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
