from __future__ import annotations

import time
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.event import filter
from astrbot.api.provider import LLMResponse, ProviderRequest
from astrbot.api.star import Context, Star, register
from astrbot.core.agent.message import TextPart
from astrbot.core.message.message_event_result import ResultContentType
from astrbot.core.message.components import Plain

from .logic import build_fold_notice
from .logic import build_delegated_reply_instruction_text
from .logic import is_dangerous_local_tool_name
from .logic import normalize_fold_threshold
from .logic import sanitize_reply_plain_text
from .logic import should_disable_model_regex_segmenting
from .logic import should_fold_long_reply
from .logic import split_forward_text


OWNER_QQ = "605738729"
DEFAULT_PROFILE = "demon"
DEFAULT_LONG_REPLY_FOLD_THRESHOLD_CHARS = 300
LLM_STARTED_AT_EXTRA = "_qqbot_reply_style_guard_llm_started_at"
LLM_REQUEST_SESSION_EXTRA = "_qqbot_reply_style_guard_llm_request_session"
BOT_PROFILES = {
    "angel": {
        "bot_id": "1443944862",
        "bot_name": "😇棉花糖😇",
    },
    "demon": {
        "bot_id": "2629227874",
        "bot_name": "👿棉花糖👿",
    },
}
PROFILE_BY_BOT_ID = {data["bot_id"]: profile for profile, data in BOT_PROFILES.items()}
DELEGATED_FROM_EXTRA = "_qqbot_twin_llm_delegated_from"


PLAIN_TEXT_REPLY_INSTRUCTION = (
    "本轮回复必须使用 QQ 纯文本聊天格式，不要使用 Markdown。"
    "禁止使用 # 标题、Markdown 列表符号、粗体、反引号代码块、引用块、Markdown 链接和表格。"
    "普通聊天优先短句自然表达，不要主动列项目符号；需要给 API、JSON、配置示例时允许保留换行和缩进，但不要包代码围栏。"
    "不要用“如果你愿意”“要的话”“你把具体内容发我”“我可以再帮你”等追问式收尾。"
)
@register(
    "astrbot_plugin_reply_style_guard",
    "MengLei",
    "清洗棉花糖回复格式，记录 LLM 耗时，并控制过多分段。",
    "0.1.10",
)
class ReplyStyleGuardPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self._long_reply_fold_threshold_chars = normalize_fold_threshold(
            get_config_value(
                config,
                "long_reply_fold_threshold_chars",
                DEFAULT_LONG_REPLY_FOLD_THRESHOLD_CHARS,
            ),
            default=DEFAULT_LONG_REPLY_FOLD_THRESHOLD_CHARS,
        )
        logger.info(
            "[ReplyStyleGuard] loaded: long_reply_fold_threshold_chars=%s",
            self._long_reply_fold_threshold_chars,
        )

    @filter.on_llm_request(desc="在 LLM 请求前记录耗时并移除非主人私聊的本机工具。")
    async def inject_reply_style_guard(self, event: AstrMessageEvent, req: ProviderRequest):
        started = time.monotonic()
        event.set_extra(LLM_STARTED_AT_EXTRA, started)
        event.set_extra(LLM_REQUEST_SESSION_EXTRA, req.session_id or "")
        logger.info(
            "[ReplyStyleGuard] LLM request started: session=%s message_type=%s "
            "request_session=%s model=%s prompt_chars=%s image_count=%s audio_count=%s has_tools=%s",
            getattr(event, "unified_msg_origin", ""),
            safe_event_value(event, "get_message_type"),
            req.session_id or "",
            req.model or "",
            len(req.prompt or ""),
            len(req.image_urls or []),
            len(req.audio_urls or []),
            bool(req.func_tool),
        )
        removed_tools = remove_forbidden_local_tools(event, req)
        if removed_tools:
            logger.info(
                "[ReplyStyleGuard] removed local tools for non-owner-private request: session=%s tools=%s",
                getattr(event, "unified_msg_origin", ""),
                ",".join(removed_tools),
            )
        req.extra_user_content_parts.append(TextPart(text=PLAIN_TEXT_REPLY_INSTRUCTION).mark_as_temp())
        delegated_from = str(event.get_extra(DELEGATED_FROM_EXTRA, "") or "").strip()
        if delegated_from:
            req.extra_user_content_parts.append(
                TextPart(text=build_delegated_reply_instruction(event, delegated_from)).mark_as_temp()
            )

    @filter.on_llm_response(desc="记录 LLM 返回耗时，帮助区分上游仍在处理、已返回或已失败。")
    async def log_llm_response_latency(self, event: AstrMessageEvent, response: LLMResponse):
        started = event.get_extra(LLM_STARTED_AT_EXTRA)
        elapsed = time.monotonic() - started if isinstance(started, (int, float)) else -1.0
        logger.info(
            "[ReplyStyleGuard] LLM response returned: session=%s request_session=%s "
            "elapsed=%.2fs has_text=%s has_chain=%s has_tool_call=%s has_reasoning=%s is_chunk=%s",
            getattr(event, "unified_msg_origin", ""),
            event.get_extra(LLM_REQUEST_SESSION_EXTRA, ""),
            elapsed,
            bool((getattr(response, "completion_text", "") or "").strip()) if response else False,
            bool(getattr(response, "result_chain", None)) if response else False,
            bool(getattr(response, "tools_call_args", None)) if response else False,
            bool((getattr(response, "reasoning_content", "") or "").strip()) if response else False,
            bool(getattr(response, "is_chunk", False)) if response else False,
        )

    @filter.on_decorating_result(desc="在消息发送前清理 Markdown、追问式、反问式或空洞邀请式收尾。")
    async def strip_reply_style_tail(self, event: AstrMessageEvent):
        result = event.get_result()
        if result is None or not result.chain:
            return
        started = event.get_extra(LLM_STARTED_AT_EXTRA)
        if isinstance(started, (int, float)):
            logger.info(
                "[ReplyStyleGuard] decorating reply result: session=%s request_session=%s "
                "elapsed=%.2fs chain_items=%s",
                getattr(event, "unified_msg_origin", ""),
                event.get_extra(LLM_REQUEST_SESSION_EXTRA, ""),
                time.monotonic() - started,
                len(result.chain),
            )
        changed = False
        if hasattr(result, "use_markdown"):
            result.use_markdown(False)
        cleaned_chain = []
        for comp in result.chain:
            if not isinstance(comp, Plain):
                cleaned_chain.append(comp)
                continue
            cleaned = sanitize_reply_plain_text(comp.text)
            if cleaned != comp.text:
                comp.text = cleaned
                changed = True
            if cleaned:
                cleaned_chain.append(comp)
        if changed:
            result.chain = cleaned_chain
            logger.info(
                "[ReplyStyleGuard] sanitized reply style: session=%s",
                getattr(event, "unified_msg_origin", ""),
            )
        folded = await self._try_send_folded_long_reply(event, result)
        if folded:
            event.clear_result()
            event.stop_event()
            return
        if _should_disable_segmented_reply_for_result(self.context, result):
            result.set_result_content_type(ResultContentType.GENERAL_RESULT)
            logger.info(
                "[ReplyStyleGuard] disabled segmented reply for long multi-part LLM result: session=%s",
                getattr(event, "unified_msg_origin", ""),
            )

    async def _try_send_folded_long_reply(self, event: AstrMessageEvent, result) -> bool:
        if self._long_reply_fold_threshold_chars <= 0:
            return False
        if event.get_platform_name() != "aiocqhttp":
            return False
        group_id = str(event.get_group_id() or "").strip()
        if not group_id:
            return False
        if result is None or not result.is_model_result():
            return False
        text = _plain_result_text(result.chain)
        if not should_fold_long_reply(
            text,
            threshold=self._long_reply_fold_threshold_chars,
        ):
            return False
        bot = getattr(event, "bot", None)
        call_action = getattr(bot, "call_action", None)
        if not callable(call_action):
            return False
        chunks = split_forward_text(text)
        if not chunks:
            return False
        try:
            forward_result = await call_action(
                "send_group_forward_msg",
                group_id=int(group_id) if group_id.isdigit() else group_id,
                messages=_build_onebot_forward_nodes(
                    chunks,
                    uin=safe_event_value(event, "get_self_id") or "10000",
                    name=read_bot_display_name(event),
                ),
            )
            message_id = _extract_message_id(forward_result)
            notice_message = _build_fold_notice_message(
                build_fold_notice(len(chunks)),
                reply_message_id=message_id,
            )
            await call_action(
                "send_group_msg",
                group_id=int(group_id) if group_id.isdigit() else group_id,
                message=notice_message,
            )
        except Exception as exc:
            logger.warning(
                "[ReplyStyleGuard] folded long reply send failed: session=%s error=%s",
                getattr(event, "unified_msg_origin", ""),
                exc,
            )
            return False
        logger.info(
            "[ReplyStyleGuard] folded long reply: session=%s chars=%s nodes=%s quoted=%s",
            getattr(event, "unified_msg_origin", ""),
            len(text),
            len(chunks),
            bool(_extract_message_id(forward_result)),
        )
        return True


def safe_event_value(event: AstrMessageEvent, method_name: str) -> str:
    method = getattr(event, method_name, None)
    if not callable(method):
        return ""
    try:
        return str(method() or "").strip()
    except Exception:
        return ""


def _should_disable_segmented_reply_for_result(context: Context, result) -> bool:
    if result is None or not result.is_model_result():
        return False
    segmented_reply = _read_segmented_reply_config(context)
    if segmented_reply.get("enable") is not True:
        return False
    if segmented_reply.get("only_llm_result", True) is not True:
        return False
    if str(segmented_reply.get("split_mode", "regex")) != "regex":
        return False
    return should_disable_model_regex_segmenting(segmented_reply, is_model_result=True)


def build_delegated_reply_instruction(event: AstrMessageEvent, delegated_from: str) -> str:
    return build_delegated_reply_instruction_text(
        current_id=safe_event_value(event, "get_self_id"),
        current_name=read_bot_display_name(event),
        delegated_from=delegated_from,
    )


def _read_segmented_reply_config(context: Context) -> dict:
    get_config = getattr(context, "get_config", None)
    config = None
    if callable(get_config):
        try:
            config = get_config()
        except Exception:
            config = None
    if not isinstance(config, dict):
        return {}
    platform_settings = config.get("platform_settings")
    if not isinstance(platform_settings, dict):
        return {}
    segmented_reply = platform_settings.get("segmented_reply")
    return segmented_reply if isinstance(segmented_reply, dict) else {}


def get_config_value(config, key: str, default=None):
    if config is None:
        return default
    getter = getattr(config, "get", None)
    if callable(getter):
        try:
            return getter(key, default)
        except TypeError:
            try:
                value = getter(key)
            except Exception:
                return default
            return default if value is None else value
        except Exception:
            return default
    if isinstance(config, dict):
        return config.get(key, default)
    return getattr(config, key, default)


def _plain_result_text(chain) -> str:
    if not chain:
        return ""
    texts: list[str] = []
    for comp in chain:
        if not isinstance(comp, Plain):
            return ""
        texts.append(comp.text)
    return "".join(texts).strip()


def _build_onebot_forward_nodes(
    chunks: list[str],
    *,
    uin: str,
    name: str,
) -> list[dict[str, Any]]:
    node_name = name.strip() or "棉花糖"
    node_uin = str(uin or "10000")
    return [
        {
            "type": "node",
            "data": {
                "name": node_name,
                "uin": node_uin,
                "content": [{"type": "text", "data": {"text": chunk}}],
            },
        }
        for chunk in chunks
    ]


def _build_fold_notice_message(
    text: str,
    *,
    reply_message_id: str,
) -> list[dict[str, Any]]:
    message: list[dict[str, Any]] = []
    if reply_message_id:
        message.append({"type": "reply", "data": {"id": reply_message_id}})
    message.append({"type": "text", "data": {"text": text}})
    return message


def _extract_message_id(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("message_id", "id"):
            raw = value.get(key)
            if raw not in (None, ""):
                return str(raw)
        data = value.get("data")
        if isinstance(data, dict):
            return _extract_message_id(data)
    for key in ("message_id", "id"):
        raw = getattr(value, key, None)
        if raw not in (None, ""):
            return str(raw)
    return ""


def allow_local_runtime_tools(event: AstrMessageEvent) -> bool:
    return event.is_private_chat() and safe_event_value(event, "get_sender_id") == OWNER_QQ


def remove_forbidden_local_tools(event: AstrMessageEvent, req: ProviderRequest) -> list[str]:
    toolset = getattr(req, "func_tool", None)
    if toolset is None or allow_local_runtime_tools(event):
        return []
    tools = list(getattr(toolset, "tools", []) or [])
    removed: list[str] = []
    for tool in tools:
        name = str(getattr(tool, "name", "") or "").strip()
        if not is_dangerous_local_tool_name(name):
            continue
        remover = getattr(toolset, "remove_tool", None)
        if callable(remover):
            remover(name)
        else:
            toolset.tools = [candidate for candidate in getattr(toolset, "tools", []) if getattr(candidate, "name", "") != name]
        removed.append(name)
    if getattr(toolset, "empty", None) and toolset.empty():
        req.func_tool = None
    return removed


def read_bot_display_name(event: AstrMessageEvent) -> str:
    self_id = safe_event_value(event, "get_self_id")
    profile = PROFILE_BY_BOT_ID.get(self_id, DEFAULT_PROFILE)
    data = BOT_PROFILES.get(profile, BOT_PROFILES[DEFAULT_PROFILE])
    return data["bot_name"]
