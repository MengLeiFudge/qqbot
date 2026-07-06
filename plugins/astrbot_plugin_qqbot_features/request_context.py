from __future__ import annotations

from dataclasses import dataclass
import re

try:
    from astrbot.api.message_components import At, Image, Plain, Reply
    _ASTRBOT_COMPONENTS_AVAILABLE = True
except Exception:  # pragma: no cover - imported by lightweight unit tests.
    At = Image = Plain = Reply = object  # type: ignore[assignment]
    _ASTRBOT_COMPONENTS_AVAILABLE = False


BOT_NAME_MARKERS = ("棉花糖", "天使棉花糖", "恶魔棉花糖", "呼叫棉花糖")


@dataclass(frozen=True, slots=True)
class CurrentRequestContext:
    current_text: str
    reply_texts: tuple[str, ...]
    combined_query: str
    named_call: bool
    unresolved_media_context: bool


def build_current_request_context(event: object, prompt: str = "") -> CurrentRequestContext:
    current_text = normalize_space(prompt) or extract_plain_text(event)
    reply_texts = tuple(text for text in extract_reply_texts(event) if text)
    combined_query = compose_query(current_text, reply_texts)
    return CurrentRequestContext(
        current_text=current_text,
        reply_texts=reply_texts,
        combined_query=combined_query,
        named_call=contains_bot_name(current_text),
        unresolved_media_context=has_unresolved_media_context(event),
    )


def compose_query(current_text: str, reply_texts: tuple[str, ...] | list[str]) -> str:
    lines: list[str] = []
    for index, text in enumerate(reply_texts, start=1):
        normalized = normalize_space(text)
        if normalized:
            lines.append(f"被引用消息{index}：{normalized}")
    normalized_current = normalize_space(current_text)
    if normalized_current:
        lines.append(f"当前消息：{normalized_current}")
    return "\n".join(lines).strip()


def extract_plain_text(event: object) -> str:
    parts: list[str] = []
    for segment in safe_get_messages(event):
        if is_plain_segment(segment):
            parts.append(str(getattr(segment, "text", "") or ""))
    text = "".join(parts).strip()
    if text:
        return text
    getter = getattr(event, "get_message_str", None)
    if callable(getter):
        try:
            return str(getter() or "").strip()
        except Exception:
            return ""
    return ""


def extract_reply_texts(event: object) -> list[str]:
    texts: list[str] = []
    for segment in safe_get_messages(event):
        if not is_reply_segment(segment):
            continue
        text = reply_segment_text(segment)
        if text:
            texts.append(text)
    return dedupe_keep_order(texts)


def reply_segment_text(segment: object) -> str:
    for attr in ("message_str", "text"):
        text = normalize_space(getattr(segment, attr, "") or "")
        if text and not is_media_placeholder_text(text):
            return text
    chain = getattr(segment, "chain", None)
    if not chain:
        return ""
    parts: list[str] = []
    for item in chain:
        if is_plain_segment(item):
            parts.append(str(getattr(item, "text", "") or ""))
    text = normalize_space("".join(parts))
    return "" if is_media_placeholder_text(text) else text


def canonical_event_claim_key(event: object, *, purpose: str, include_private_self_id: bool = False) -> str:
    group_id = safe_call(event, "get_group_id")
    if not group_id:
        self_id = safe_call(event, "get_self_id") if include_private_self_id else ""
        group_id = f"private:{self_id}" if self_id else "private"
    sender_id = safe_call(event, "get_sender_id") or "unknown"
    text = re.sub(r"\s+", "", extract_plain_text(event))[:160]
    at_ids = ",".join(sorted(extract_at_ids(event)))
    reply_key = canonical_reply_key(event)
    bucket = event_time_bucket(event)
    if text or at_ids or reply_key:
        return f"canonical:{purpose}:{group_id}:{sender_id}:{bucket}:{at_ids}:{reply_key}:{text}"
    message_id = event_message_id(event)
    if message_id:
        return f"message:{purpose}:{message_id}"
    return f"fallback:{purpose}:{group_id}:{sender_id}:{bucket}"


def canonical_reply_key(event: object) -> str:
    reply_texts = tuple(
        re.sub(r"\s+", "", text)[:160]
        for text in extract_reply_texts(event)
        if text
    )
    if reply_texts:
        return "text:" + "|".join(reply_texts)
    reply_ids = extract_reply_ids(event)
    return "id:" + ",".join(reply_ids) if reply_ids else ""


def extract_at_ids(event: object) -> tuple[str, ...]:
    ids: list[str] = []
    for segment in safe_get_messages(event):
        if is_at_segment(segment):
            qq = str(getattr(segment, "qq", "") or "").strip()
            if qq:
                ids.append(qq)
    return tuple(ids)


def extract_image_sources(event: object) -> tuple[str, ...]:
    sources: list[str] = []
    for segment in safe_get_messages(event):
        sources.extend(image_sources_from_segment(segment))
    return tuple(dedupe_keep_order(sources))


def image_sources_from_segment(segment: object) -> list[str]:
    if is_image_segment(segment):
        return image_segment_sources(segment)
    if not is_reply_segment(segment):
        return []
    sources: list[str] = []
    for item in getattr(segment, "chain", None) or []:
        if is_image_segment(item):
            sources.extend(image_segment_sources(item))
    return sources


def image_segment_sources(segment: object) -> list[str]:
    return [
        value
        for value in (
            getattr(segment, "url", ""),
            getattr(segment, "file", ""),
            getattr(segment, "path", ""),
        )
        if looks_like_image_source(value)
    ]


def looks_like_image_source(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return (
        text.startswith("http://")
        or text.startswith("https://")
        or text.startswith("file:///")
        or text.startswith("/")
        or re.match(r"^[A-Za-z]:[\\/]", text) is not None
    )


def extract_reply_ids(event: object) -> tuple[str, ...]:
    ids: list[str] = []
    for segment in safe_get_messages(event):
        if is_reply_segment(segment):
            reply_id = str(getattr(segment, "id", "") or "").strip()
            if reply_id:
                ids.append(reply_id)
    return tuple(ids)


def event_message_id(event: object) -> str:
    return str(getattr(getattr(event, "message_obj", None), "message_id", "") or "").strip()


def event_time_bucket(event: object, *, seconds: int = 10) -> str:
    message_obj = getattr(event, "message_obj", None)
    raw = getattr(message_obj, "timestamp", None) or getattr(message_obj, "time", None)
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return ""
    return str(value // max(1, seconds))


def contains_bot_name(text: str) -> bool:
    normalized = str(text or "")
    return any(marker in normalized for marker in BOT_NAME_MARKERS)


def has_unresolved_media_context(event: object) -> bool:
    return any(segment_has_unresolved_media(segment) for segment in safe_get_messages(event))


def segment_has_unresolved_media(segment: object) -> bool:
    if is_plain_segment(segment):
        return is_media_placeholder_text(getattr(segment, "text", "") or "")
    if is_media_segment(segment):
        return True
    if not is_reply_segment(segment):
        return False
    for attr in ("message_str", "text"):
        text = normalize_space(getattr(segment, attr, "") or "")
        if is_media_placeholder_text(text):
            return True
    chain = getattr(segment, "chain", None)
    if not chain:
        return False
    has_media = False
    has_text = False
    for item in chain:
        if is_media_segment(item):
            has_media = True
        elif is_plain_segment(item):
            text = normalize_space(getattr(item, "text", "") or "")
            if text and not is_media_placeholder_text(text):
                has_text = True
    return has_media and not has_text


def is_media_placeholder_text(text: object) -> bool:
    normalized = normalize_space(text)
    if not normalized:
        return False
    return re.fullmatch(r"\[(?:图片|表情|视频|语音|文件|卡片消息|转发消息)(?:[^\]]*)\]", normalized) is not None


def normalize_space(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def safe_get_messages(event: object) -> tuple[object, ...]:
    getter = getattr(event, "get_messages", None)
    if not callable(getter):
        return ()
    try:
        return tuple(getter() or ())
    except Exception:
        return ()


def safe_call(event: object, method_name: str) -> str:
    method = getattr(event, method_name, None)
    if not callable(method):
        return ""
    try:
        return str(method() or "").strip()
    except Exception:
        return ""


def is_plain_segment(segment: object) -> bool:
    return (_ASTRBOT_COMPONENTS_AVAILABLE and isinstance(segment, Plain)) or segment.__class__.__name__.lower() == "plain"


def is_at_segment(segment: object) -> bool:
    return (_ASTRBOT_COMPONENTS_AVAILABLE and isinstance(segment, At)) or segment.__class__.__name__.lower() == "at"


def is_media_segment(segment: object) -> bool:
    return segment.__class__.__name__.lower() in {
        "image",
        "video",
        "record",
        "file",
        "face",
        "node",
        "xml",
        "json",
    }


def is_image_segment(segment: object) -> bool:
    return (_ASTRBOT_COMPONENTS_AVAILABLE and isinstance(segment, Image)) or segment.__class__.__name__.lower() == "image"


def is_reply_segment(segment: object) -> bool:
    return (_ASTRBOT_COMPONENTS_AVAILABLE and isinstance(segment, Reply)) or segment.__class__.__name__.lower() == "reply"


def dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = normalize_space(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result
