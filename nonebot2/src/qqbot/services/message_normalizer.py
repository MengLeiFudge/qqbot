from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from contextlib import suppress
from typing import Any
from dataclasses import dataclass

OneBotFetcher = Callable[..., Awaitable[Any]]
MAX_FORWARD_DEPTH = 3
MAX_FORWARD_NODES = 50


@dataclass(frozen=True, slots=True)
class NormalizedReply:
    user_id: str
    sender_name: str
    message: "NormalizedMessage"
    message_id: str = ""


@dataclass(frozen=True, slots=True)
class NormalizedMessage:
    text: str
    outline: str
    image_urls: tuple[str, ...] = ()
    at_user_ids: tuple[str, ...] = ()
    audio_urls: tuple[str, ...] = ()
    video_urls: tuple[str, ...] = ()
    reply: NormalizedReply | None = None


def normalize_onebot_event(event) -> NormalizedMessage:
    message = getattr(event, "original_message", None) or getattr(event, "message", None)
    normalized = normalize_onebot_message(message)
    reply = normalize_onebot_reply(getattr(event, "reply", None))
    return NormalizedMessage(
        text=normalized.text,
        outline=normalized.outline,
        image_urls=normalized.image_urls,
        at_user_ids=normalized.at_user_ids,
        audio_urls=normalized.audio_urls,
        video_urls=normalized.video_urls,
        reply=reply,
    )


async def normalize_onebot_event_with_fetcher(
    event,
    fetcher: OneBotFetcher,
) -> NormalizedMessage:
    message = getattr(event, "original_message", None) or getattr(event, "message", None)
    normalized = await normalize_onebot_message_with_fetcher(message, fetcher)
    reply = await normalize_onebot_reply_with_fetcher(getattr(event, "reply", None), fetcher)
    return NormalizedMessage(
        text=normalized.text,
        outline=normalized.outline,
        image_urls=normalized.image_urls,
        at_user_ids=normalized.at_user_ids,
        audio_urls=normalized.audio_urls,
        video_urls=normalized.video_urls,
        reply=reply,
    )


def normalize_onebot_reply(reply) -> NormalizedReply | None:
    if reply is None:
        return None

    sender = getattr(reply, "sender", None)
    user_id = str(getattr(sender, "user_id", "") or "")
    sender_name = (
        str(getattr(sender, "card", "") or "").strip()
        or str(getattr(sender, "nickname", "") or "").strip()
        or user_id
        or "未知用户"
    )
    message = normalize_onebot_message(getattr(reply, "message", None))
    if not message.outline:
        return None
    return NormalizedReply(
        user_id=user_id,
        sender_name=sender_name,
        message=message,
        message_id=str(getattr(reply, "message_id", "") or ""),
    )


async def normalize_onebot_reply_with_fetcher(
    reply,
    fetcher: OneBotFetcher,
) -> NormalizedReply | None:
    if reply is None:
        return None

    message_id = str(getattr(reply, "message_id", "") or "")
    payload = await _fetch_onebot_message(fetcher, message_id)
    payload_sender = _extract_payload_sender(payload)
    sender = payload_sender or getattr(reply, "sender", None)
    user_id = _extract_sender_user_id(sender)
    sender_name = _extract_sender_name(sender, user_id)
    message_source = _extract_message_content(payload)
    if message_source is None:
        message_source = getattr(reply, "message", None)
    message = await normalize_onebot_message_with_fetcher(
        message_source,
        fetcher,
        _visited_message_ids={message_id} if message_id else None,
    )
    if not message.outline:
        return None
    return NormalizedReply(
        user_id=user_id,
        sender_name=sender_name,
        message=message,
        message_id=message_id,
    )


def normalize_onebot_message(message) -> NormalizedMessage:
    if message is None:
        return NormalizedMessage(text="", outline="")

    plain_text_parts: list[str] = []
    outline_parts: list[str] = []
    image_urls: list[str] = []
    at_user_ids: list[str] = []
    audio_urls: list[str] = []
    video_urls: list[str] = []

    for segment in message:
        segment_type = str(getattr(segment, "type", "")).strip()
        data = getattr(segment, "data", {}) or {}

        if segment_type == "text":
            text = str(data.get("text", "")).strip()
            if text:
                plain_text_parts.append(text)
                outline_parts.append(text)
        elif segment_type == "at":
            qq = str(data.get("qq", "")).strip()
            if qq:
                at_user_ids.append(qq)
            outline_parts.append(f"[@{qq or 'unknown'}]")
        elif segment_type == "image":
            image_url = _extract_image_url(data)
            if image_url:
                image_urls.append(image_url)
            outline_parts.append("[图片]")
        elif segment_type == "face":
            outline_parts.append("[表情]")
        elif segment_type == "record":
            audio_url = _extract_media_url(data)
            if audio_url:
                audio_urls.append(audio_url)
            outline_parts.append("[语音]")
        elif segment_type == "video":
            video_url = _extract_media_url(data)
            if video_url:
                video_urls.append(video_url)
            outline_parts.append("[视频]")
        elif segment_type == "file":
            name = str(data.get("name", "") or data.get("file", "")).strip()
            outline_parts.append(f"[文件：{name}]" if name else "[文件]")
        elif segment_type == "reply":
            continue
        elif segment_type:
            outline_parts.append(f"[{segment_type}]")

    text = " ".join(plain_text_parts).strip()
    outline = " ".join(outline_parts).strip()
    if not outline:
        outline = text

    return NormalizedMessage(
        text=text,
        outline=outline,
        image_urls=tuple(image_urls),
        at_user_ids=tuple(at_user_ids),
        audio_urls=tuple(audio_urls),
        video_urls=tuple(video_urls),
    )


async def normalize_onebot_message_with_fetcher(
    message,
    fetcher: OneBotFetcher,
    *,
    _depth: int = 0,
    _visited_forward_ids: set[str] | None = None,
    _visited_message_ids: set[str] | None = None,
) -> NormalizedMessage:
    return await _normalize_onebot_message(
        message,
        fetcher=fetcher,
        depth=_depth,
        visited_forward_ids=_visited_forward_ids or set(),
        visited_message_ids=_visited_message_ids or set(),
    )


async def _normalize_onebot_message(
    message,
    *,
    fetcher: OneBotFetcher | None,
    depth: int,
    visited_forward_ids: set[str],
    visited_message_ids: set[str],
) -> NormalizedMessage:
    if message is None:
        return NormalizedMessage(text="", outline="")
    if isinstance(message, str):
        text = message.strip()
        return NormalizedMessage(text=text, outline=text)

    plain_text_parts: list[str] = []
    outline_parts: list[str] = []
    image_urls: list[str] = []
    at_user_ids: list[str] = []
    audio_urls: list[str] = []
    video_urls: list[str] = []

    for segment in _iter_message_segments(message):
        segment_type = _get_segment_type(segment)
        data = _get_segment_data(segment)

        if segment_type == "text":
            text = str(data.get("text", "")).strip()
            if text:
                plain_text_parts.append(text)
                outline_parts.append(text)
        elif segment_type == "at":
            qq = str(data.get("qq", "")).strip()
            if qq:
                at_user_ids.append(qq)
            outline_parts.append(f"[@{qq or 'unknown'}]")
        elif segment_type == "image":
            image_url = _extract_image_url(data)
            if image_url:
                image_urls.append(image_url)
            outline_parts.append("[图片]")
        elif segment_type == "face":
            outline_parts.append("[表情]")
        elif segment_type == "record":
            audio_url = _extract_media_url(data)
            if audio_url:
                audio_urls.append(audio_url)
            outline_parts.append("[语音]")
        elif segment_type == "video":
            video_url = _extract_media_url(data)
            if video_url:
                video_urls.append(video_url)
            outline_parts.append("[视频]")
        elif segment_type == "file":
            name = str(data.get("name", "") or data.get("file", "")).strip()
            outline_parts.append(f"[文件：{name}]" if name else "[文件]")
        elif segment_type == "forward":
            forward_text = await _resolve_forward_segment(
                data,
                fetcher=fetcher,
                depth=depth,
                visited_forward_ids=visited_forward_ids,
                visited_message_ids=visited_message_ids,
            )
            if forward_text:
                plain_text_parts.append(forward_text)
                outline_parts.append(forward_text)
            else:
                outline_parts.append("[聊天记录]")
        elif segment_type == "node":
            node_text = await _normalize_forward_node(
                segment,
                fetcher=fetcher,
                depth=depth,
                visited_forward_ids=visited_forward_ids,
                visited_message_ids=visited_message_ids,
            )
            if node_text:
                plain_text_parts.append(node_text)
                outline_parts.append(node_text)
            else:
                outline_parts.append("[聊天记录]")
        elif segment_type == "reply":
            continue
        elif segment_type:
            outline_parts.append("[聊天记录]" if segment_type == "json" else f"[{segment_type}]")

    text = " ".join(plain_text_parts).strip()
    outline = " ".join(outline_parts).strip()
    if not outline:
        outline = text

    return NormalizedMessage(
        text=text,
        outline=outline,
        image_urls=tuple(image_urls),
        at_user_ids=tuple(at_user_ids),
        audio_urls=tuple(audio_urls),
        video_urls=tuple(video_urls),
    )


async def _fetch_onebot_message(fetcher: OneBotFetcher, message_id: str) -> Any:
    if not message_id:
        return None
    with suppress(Exception):
        return await fetcher("get_msg", message_id=int(message_id) if message_id.isdigit() else message_id)
    return None


async def _resolve_forward_segment(
    data: dict[str, Any],
    *,
    fetcher: OneBotFetcher | None,
    depth: int,
    visited_forward_ids: set[str],
    visited_message_ids: set[str],
) -> str:
    forward_id = str(data.get("id", "") or data.get("resid", "") or data.get("file", "")).strip()
    if fetcher is None or not forward_id or depth >= MAX_FORWARD_DEPTH or forward_id in visited_forward_ids:
        return ""
    visited_forward_ids.add(forward_id)
    payload = None
    with suppress(Exception):
        payload = await fetcher("get_forward_msg", id=forward_id)
    if payload is None:
        return ""
    lines: list[str] = []
    for node in _extract_forward_nodes(payload)[:MAX_FORWARD_NODES]:
        line = await _normalize_forward_node(
            node,
            fetcher=fetcher,
            depth=depth + 1,
            visited_forward_ids=visited_forward_ids,
            visited_message_ids=visited_message_ids,
        )
        if line:
            lines.append(line)
    return "\n".join(lines).strip()


async def _normalize_forward_node(
    node: Any,
    *,
    fetcher: OneBotFetcher | None,
    depth: int,
    visited_forward_ids: set[str],
    visited_message_ids: set[str],
) -> str:
    data = _get_segment_data(node) if _get_segment_type(node) == "node" else {}
    sender = None if data else _extract_sender(node)
    name = _extract_sender_name(sender, _extract_sender_user_id(sender)) if sender is not None else ""
    if not name:
        name = str(data.get("name", "") or data.get("nickname", "") or "").strip()
    uin = (
        (_extract_sender_user_id(sender) if sender is not None else "")
        or str(data.get("uin", "") or data.get("user_id", "") or "").strip()
    )
    content = _extract_node_content(node)
    normalized = await _normalize_onebot_message(
        content,
        fetcher=fetcher,
        depth=depth,
        visited_forward_ids=visited_forward_ids,
        visited_message_ids=visited_message_ids,
    )
    text = normalized.outline.strip()
    if not text:
        return ""
    prefix = name or uin
    if prefix and uin and uin not in prefix:
        prefix = f"{prefix}({uin})"
    return f"{prefix}: {text}" if prefix else text


def _iter_message_segments(message: Any) -> Iterable[Any]:
    if isinstance(message, dict):
        content = _extract_message_content(message)
        if content is not None and content is not message:
            return _iter_message_segments(content)
        return (message,)
    if isinstance(message, list | tuple):
        return tuple(message)
    try:
        return tuple(message)
    except TypeError:
        return ()


def _get_segment_type(segment: Any) -> str:
    if isinstance(segment, dict):
        return str(segment.get("type", "") or segment.get("msg_type", "") or "").strip()
    return str(getattr(segment, "type", "")).strip()


def _get_segment_data(segment: Any) -> dict[str, Any]:
    if isinstance(segment, dict):
        data = segment.get("data")
        return data if isinstance(data, dict) else {}
    data = getattr(segment, "data", {}) or {}
    return data if isinstance(data, dict) else {}


def _extract_message_content(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return None
    for key in ("message", "content"):
        value = payload.get(key)
        if value not in (None, ""):
            return value
    data = payload.get("data")
    if isinstance(data, dict):
        return _extract_message_content(data)
    return None


def _extract_node_content(node: Any) -> Any:
    data = _get_segment_data(node)
    for key in ("content", "message"):
        value = data.get(key)
        if value not in (None, ""):
            return value
    content = _extract_message_content(node)
    if content is not None:
        return content
    if isinstance(node, dict):
        for key in ("content", "message"):
            value = node.get(key)
            if value not in (None, ""):
                return value
    return None


def _extract_forward_nodes(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("messages", "message"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    data = payload.get("data")
    if isinstance(data, dict):
        return _extract_forward_nodes(data)
    if isinstance(data, list):
        return data
    return []


def _extract_sender(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    payload_sender = _extract_payload_sender(payload)
    if payload_sender is not None:
        return payload_sender
    if any(key in payload for key in ("user_id", "uin", "card", "nickname", "name")):
        return payload
    return None


def _extract_payload_sender(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return None
    sender = payload.get("sender")
    if sender is not None:
        return sender
    data = payload.get("data")
    if isinstance(data, dict) and data.get("sender") is not None:
        return data.get("sender")
    return None


def _extract_sender_user_id(sender: Any) -> str:
    if isinstance(sender, dict):
        return str(sender.get("user_id", "") or sender.get("uin", "") or "").strip()
    return str(getattr(sender, "user_id", "") or getattr(sender, "uin", "") or "").strip()


def _extract_sender_name(sender: Any, fallback_user_id: str = "") -> str:
    if isinstance(sender, dict):
        return (
            str(sender.get("card", "") or "").strip()
            or str(sender.get("nickname", "") or "").strip()
            or str(sender.get("name", "") or "").strip()
            or fallback_user_id
            or "未知用户"
        )
    return (
        str(getattr(sender, "card", "") or "").strip()
        or str(getattr(sender, "nickname", "") or "").strip()
        or str(getattr(sender, "name", "") or "").strip()
        or fallback_user_id
        or "未知用户"
    )


def _extract_image_url(data: dict[str, object]) -> str:
    return _extract_media_url(data)


def _extract_media_url(data: dict[str, object]) -> str:
    for key in ("url", "file", "path"):
        value = str(data.get(key, "") or "").strip()
        if value:
            return value
    return ""
