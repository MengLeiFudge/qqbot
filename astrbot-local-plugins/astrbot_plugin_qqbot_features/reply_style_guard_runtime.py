from __future__ import annotations

from dataclasses import dataclass
import inspect
from typing import Any

from astrbot.core.message.components import Forward as CoreForward
from astrbot.core.message.components import At as CoreAt
from astrbot.core.message.components import Node as CoreNode
from astrbot.core.message.components import Nodes as CoreNodes
from astrbot.core.message.components import Plain as CorePlain
from astrbot.core.message.components import Reply as CoreReply
from astrbot.core.utils.quoted_message.chain_parser import OneBotPayloadParser

from .reply_style_guard_logic import should_fold_long_reply
from .reply_style_guard_logic import split_forward_text


@dataclass(frozen=True, slots=True)
class FoldedReplyChain:
    chain: list[object]
    text_chars: int
    node_count: int


def decorate_active_reply_source(
    chain: list[object],
    *,
    quote_message_id: object,
    at_user_id: object,
) -> list[object] | None:
    message_id = str(quote_message_id or "").strip()
    user_id = str(at_user_id or "").strip()
    if not message_id or not user_id or not chain:
        return None
    if any(isinstance(item, CoreReply) for item in chain):
        return None
    if not all(isinstance(item, CorePlain) for item in chain):
        return None
    return [CoreReply(id=message_id), CoreAt(qq=user_id), *chain]


def build_folded_reply_chain(
    text: str,
    *,
    threshold: int,
    uin: str,
    name: str,
) -> FoldedReplyChain | None:
    if not should_fold_long_reply(text, threshold=threshold):
        return None
    chunks = split_forward_text(text)
    if not chunks:
        return None
    node_name = str(name or "").strip() or "棉花糖"
    node_uin = str(uin or "10000").strip() or "10000"
    chain = [
        CoreNodes(
            [
                CoreNode(
                    uin=node_uin,
                    name=node_name,
                    content=[CorePlain(chunk)],
                )
                for chunk in chunks
            ]
        )
    ]
    return FoldedReplyChain(chain=chain, text_chars=len(str(text or "")), node_count=len(chunks))


def has_forward_message(event: object) -> bool:
    return any(isinstance(segment, CoreForward) for segment in _safe_get_messages(event))


async def extract_onebot_forward_text(event: object, *, max_fetch: int = 6) -> str:
    forward_ids = [
        str(getattr(segment, "id", "") or "").strip()
        for segment in _safe_get_messages(event)
        if isinstance(segment, CoreForward)
    ]
    forward_ids = [forward_id for forward_id in forward_ids if forward_id]
    if not forward_ids:
        return ""
    call_action = _resolve_onebot_call_action(event)
    if call_action is None:
        return ""

    parser = OneBotPayloadParser()
    texts: list[str] = []
    pending = list(forward_ids)
    seen: set[str] = set()
    fetch_count = 0
    while pending and fetch_count < max_fetch:
        forward_id = pending.pop(0)
        if forward_id in seen:
            continue
        seen.add(forward_id)
        fetch_count += 1
        payload = await _call_onebot_action_compat(call_action, "get_forward_msg", forward_id)
        if not isinstance(payload, dict):
            continue
        parsed = parser.parse_get_forward_payload(payload)
        if parsed.get("text"):
            texts.append(str(parsed["text"]))
        for nested_id in parsed.get("forward_ids", []):
            nested_id_text = str(nested_id or "").strip()
            if nested_id_text and nested_id_text not in seen:
                pending.append(nested_id_text)

    return "\n".join(text for text in texts if text.strip()).strip()


def _safe_get_messages(event: object) -> tuple[object, ...]:
    getter = getattr(event, "get_messages", None)
    if not callable(getter):
        return ()
    try:
        return tuple(getter() or ())
    except Exception:
        return ()


def _resolve_onebot_call_action(event: object):
    bot = getattr(event, "bot", None)
    for candidate in (getattr(bot, "api", None), bot):
        call_action = getattr(candidate, "call_action", None)
        if callable(call_action):
            return call_action
    return None


async def _call_maybe_async(call_action, action: str, **params: Any):
    result = call_action(action, **params)
    if inspect.isawaitable(result):
        return await result
    return result


async def _call_onebot_action_compat(call_action, action: str, message_id: str):
    params_list: list[dict[str, object]] = [{"message_id": message_id}, {"id": message_id}]
    if str(message_id).isdigit():
        int_id = int(message_id)
        params_list.extend([{"message_id": int_id}, {"id": int_id}])
    last_error: Exception | None = None
    for params in params_list:
        try:
            return await _call_maybe_async(call_action, action, **params)
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return None
