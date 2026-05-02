from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NormalizedReply:
    user_id: str
    sender_name: str
    message: "NormalizedMessage"


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


def _extract_image_url(data: dict[str, object]) -> str:
    return _extract_media_url(data)


def _extract_media_url(data: dict[str, object]) -> str:
    for key in ("url", "file", "path"):
        value = str(data.get(key, "") or "").strip()
        if value:
            return value
    return ""
