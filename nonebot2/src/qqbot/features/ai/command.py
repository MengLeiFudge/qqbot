from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re

from qqbot.features.ai.conversation_store import AiConversationStore
from qqbot.services.command_guard import is_direct_command_event, is_likely_command
from qqbot.services.offline_message_gate import is_before_onebot_connect
from qqbot.features.ai.rightcodes_draw_client import (
    looks_like_rightcodes_draw_command,
    looks_like_rightcodes_draw_help_command,
)
from qqbot.features.ai.topic_concentration import (
    is_third_party_named_mention,
    looks_like_topic_concentration_candidate,
)
from qqbot.features.group.reread_service import DEFAULT_REREAD_STATE, is_plain_text_message

QQ_GROUP_MANAGER_USER_IDS = {"2854196310"}


@dataclass(frozen=True, slots=True)
class AiModelCommand:
    action: str
    profile: str | None = None


class AiChatTriggerKind(StrEnum):
    IGNORE = "ignore"
    PRIVATE = "private"
    DIRECT = "direct"
    NAMED = "named"
    PROACTIVE = "proactive"
    DRAW = "draw"


def should_handle_ai_chat(
    event,
    text: str,
    *,
    bot_names: tuple[str, ...] = (),
) -> bool:
    return classify_ai_chat_trigger(
        event,
        text,
        bot_names=bot_names,
    ) != AiChatTriggerKind.IGNORE


def classify_ai_chat_trigger(
    event,
    text: str,
    *,
    bot_names: tuple[str, ...] = (),
) -> AiChatTriggerKind:
    prompt = text.strip()
    if not prompt:
        if getattr(event, "message_type", "") != "group" and not hasattr(event, "group_id"):
            return AiChatTriggerKind.IGNORE
        return AiChatTriggerKind.DIRECT if is_direct_command_event(event) else AiChatTriggerKind.IGNORE
    if is_before_onebot_connect(getattr(event, "time", None)):
        return AiChatTriggerKind.IGNORE
    if is_group_manager_welcome_message(event, prompt):
        return AiChatTriggerKind.IGNORE
    if getattr(event, "message_type", "") != "group" and not hasattr(event, "group_id"):
        if prompt.startswith("/"):
            return AiChatTriggerKind.IGNORE
        if (
            is_likely_command(prompt)
            or parse_ai_model_command(prompt) is not None
        ):
            return AiChatTriggerKind.IGNORE
        return AiChatTriggerKind.PRIVATE
    if (
        is_likely_command(prompt)
        or parse_ai_model_command(prompt) is not None
    ):
        return AiChatTriggerKind.IGNORE
    if is_duplicate_reread_text_message(event, prompt):
        return AiChatTriggerKind.IGNORE
    if looks_like_rightcodes_draw_command(prompt) or looks_like_rightcodes_draw_help_command(prompt):
        return AiChatTriggerKind.DRAW
    if is_direct_command_event(event):
        return AiChatTriggerKind.DIRECT
    if looks_like_ai_named_trigger(prompt, bot_names=bot_names):
        return AiChatTriggerKind.NAMED
    if looks_like_ai_proactive_trigger(prompt, bot_names=bot_names):
        return AiChatTriggerKind.PROACTIVE
    return AiChatTriggerKind.IGNORE


def is_duplicate_reread_text_message(event, text: str) -> bool:
    if getattr(event, "message_type", "") != "group" and not hasattr(event, "group_id"):
        return False
    message = getattr(event, "original_message", None) or getattr(event, "message", None)
    if not is_plain_text_message(message):
        return False
    observation = DEFAULT_REREAD_STATE.observe(
        getattr(event, "group_id", ""),
        text,
        message_id=getattr(event, "message_id", ""),
    )
    return observation.is_duplicate


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


def looks_like_ai_proactive_trigger(text: str, *, bot_names: tuple[str, ...] = ()) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    compact = re.sub(r"\s+", "", normalized)
    if looks_like_ai_named_trigger(compact, bot_names=bot_names):
        return True
    if looks_like_sensitive_credential_request(compact):
        return True
    if looks_like_ai_meta_conversation(compact):
        return False
    if looks_like_ambiguous_chat_evaluation(compact):
        return False

    return looks_like_topic_concentration_candidate(compact, bot_names=bot_names)


def looks_like_sensitive_credential_request(text: str) -> bool:
    compact = re.sub(r"\s+", "", text.strip().lower())
    if not compact:
        return False
    secret_file_markers = (
        ".claude/.credentials.json",
        ".claude.json",
        ".codex/auth.json",
        ".codex/settings.toml",
        ".openclaw/openclaw.json",
        ".hermes/config.yaml",
        ".kube/config",
        ".config/opencode/opencode.json",
        "kubeconfig",
    )
    if sum(1 for marker in secret_file_markers if marker in compact) >= 2:
        return True
    if _looks_like_token_usage_context(compact):
        return False
    credential_markers = ("credentials", "credential", "auth.json", "apikey", "api_key", "api-key", "secret")
    token_markers = ("token", "access_token", "refresh_token", "bearertoken")
    file_request_markers = (
        "发我",
        "发一下",
        "发出来",
        "给我",
        "给一下",
        "分享",
        "上传",
        "贴一下",
        "贴出来",
        "内容",
        "配置",
        "文件",
    )
    if any(marker in compact for marker in credential_markers) and any(
        marker in compact for marker in file_request_markers
    ):
        return True
    token_request_markers = file_request_markers + ("轮换", "泄露", "公开", "撤回")
    return any(marker in compact for marker in credential_markers) and any(
        marker in compact for marker in file_request_markers
    ) or any(marker in compact for marker in token_markers) and any(
        marker in compact for marker in token_request_markers
    )


def _looks_like_token_usage_context(compact: str) -> bool:
    if "token" not in compact:
        return False
    usage_markers = (
        "用了",
        "用掉",
        "消耗",
        "额度",
        "计费",
        "价格",
        "够用",
        "不够",
        "上下文",
        "输出",
        "输入",
        "模型",
        "国产模型",
        "deepseek",
        "sonnet",
        "claude",
        "haiku",
        "flash",
        "gpt",
    )
    amount_pattern = re.search(r"\d+(?:\.\d+)?(?:亿|万|k|m|千|百)?(?:左右|多)?(?:个)?token", compact)
    return bool(amount_pattern) or any(marker in compact for marker in usage_markers)


def looks_like_ambiguous_chat_evaluation(text: str) -> bool:
    compact = re.sub(r"\s+", "", text.strip())
    if not compact:
        return False
    if len(compact) > 16:
        return False
    fuzzy_markers = (
        "感觉有点怪",
        "这感觉怪",
        "有点怪",
        "有点奇怪",
        "怪啊",
        "怪怪的",
        "不太对劲",
    )
    return any(marker in compact for marker in fuzzy_markers)


def looks_like_ai_meta_conversation(text: str) -> bool:
    compact = re.sub(r"\s+", "", text.strip().lower())
    if not compact:
        return False
    standalone_meta_markers = (
        "我问为什么报错",
        "我问为啥报错",
        "我问怎么报错",
        "说不支持",
        "直接给我降级",
        "自己改到支持",
    )
    if any(marker in compact for marker in standalone_meta_markers):
        return True
    ai_markers = ("ai", "gpt", "chatgpt", "claude", "gemini", "deepseek", "豆包", "模型")
    if not any(marker in compact for marker in ai_markers):
        return False
    technical_markers = ("接口", "api", "报错", "错误", "异常", "怎么修", "怎么解决", "修复", "日志")
    if any(marker in compact for marker in technical_markers):
        return False
    ai_meta_markers = (
        "问ai",
        "让ai",
        "ai写",
        "ai自己",
        "让gpt",
        "gpt自己",
        "问gpt",
        "模型说",
        "他说不支持",
        "说不支持",
        "直接给我降级",
        "自己改到支持",
        "代码是ai",
    )
    return any(marker in compact for marker in ai_meta_markers)


def looks_like_ai_named_trigger(text: str, *, bot_names: tuple[str, ...] = ()) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    compact = re.sub(r"\s+", "", normalized)
    lower = compact.lower()
    names = _build_ai_proactive_names(bot_names)
    for name in names:
        if not name:
            continue
        start = lower.find(name)
        while start >= 0:
            end = start + len(name)
            if (
                not is_third_party_named_mention(compact[:start], compact[end:])
                and _named_reference_is_call(compact[:start], compact[end:], compact)
            ):
                return True
            start = lower.find(name, start + len(name))
    return False


def _named_reference_is_call(before: str, after: str, compact: str) -> bool:
    stripped_after = after.lstrip("，,。.!！:：~～")
    if not before and not stripped_after:
        return True

    call_prefixes = ("呼叫", "召唤", "叫一下", "叫下", "找", "叫")
    if any(before.endswith(prefix) for prefix in call_prefixes):
        return True

    intent_prefixes = (
        "想听",
        "想看",
        "想问",
        "想让",
        "要听",
        "要问",
        "能听",
        "能不能听",
    )
    if any(before.endswith(prefix) for prefix in intent_prefixes):
        return True

    request_starters = (
        "在吗",
        "出来",
        "帮",
        "帮我",
        "看下",
        "看一下",
        "看看",
        "问",
        "请问",
        "回答",
        "解释",
        "说说",
        "讲讲",
        "能",
        "可以",
        "可不可以",
        "要不要",
        "怎么",
        "为什么",
        "为啥",
        "咋",
    )
    if stripped_after.startswith(request_starters):
        return True

    question_markers = ("?", "？", "吗", "么", "呢", "什么时候", "谁", "哪里", "哪")
    if any(marker in compact for marker in question_markers):
        return True

    soft_call_suffixes = ("呀", "啊", "欸", "诶", "喂")
    return (
        not before
        and 0 < len(stripped_after) <= 3
        and stripped_after.endswith(soft_call_suffixes)
    )


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
        return store.group_key(str(getattr(event, "group_id")), profile, scope)
    return store.private_key(user_id, profile, scope)
