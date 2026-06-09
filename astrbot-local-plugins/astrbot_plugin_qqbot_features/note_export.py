from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re


DEFAULT_NOTE_EXPORT_COUNT = 50
MAX_NOTE_EXPORT_COUNT = 200


@dataclass(frozen=True, slots=True)
class GroupNoteRecord:
    user_id: str
    sender_name: str
    text: str
    timestamp: int = 0
    message_id: str = ""


@dataclass(frozen=True, slots=True)
class GroupNoteExportResult:
    path: Path
    count: int


class GroupNoteExportError(RuntimeError):
    pass


def export_group_notes_markdown(
    *,
    group_id: str,
    text: str,
    now: datetime | None = None,
) -> GroupNoteExportResult:
    count = parse_note_export_count(text)
    records = load_public_group_context_records(group_id, limit=count)
    if not records:
        raise GroupNoteExportError("没有可导出的公开群聊记录。")
    current_time = now or datetime.now().astimezone()
    output_dir = get_group_note_export_root()
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / build_group_note_export_filename(group_id, current_time)
    content = format_group_notes_markdown(
        group_id=group_id,
        records=records,
        generated_at=current_time,
    )
    path.write_text(content, encoding="utf-8", newline="\n")
    return GroupNoteExportResult(path=path, count=len(records))


def parse_note_export_count(text: str) -> int:
    stripped = str(text or "").strip()
    match = re.search(r"(?:棉花(?:记录|导出(?:md|MD)?)|最近)\s*([0-9]{1,3})", stripped)
    if match is None:
        return DEFAULT_NOTE_EXPORT_COUNT
    try:
        count = int(match.group(1))
    except ValueError:
        return DEFAULT_NOTE_EXPORT_COUNT
    return max(1, min(count, MAX_NOTE_EXPORT_COUNT))


def load_public_group_context_records(group_id: str, *, limit: int) -> tuple[GroupNoteRecord, ...]:
    path = get_nonebot2_data_root() / "ai" / "group_context" / f"{group_id}.json"
    if not path.is_file():
        return ()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GroupNoteExportError(f"读取公开群聊记录失败：{exc}") from exc
    if not isinstance(payload, list):
        return ()
    records: list[GroupNoteRecord] = []
    for raw in payload:
        if not isinstance(raw, dict):
            continue
        record = normalize_group_note_record(raw)
        if record is not None:
            records.append(record)
    return tuple(records[-max(1, min(int(limit), MAX_NOTE_EXPORT_COUNT)) :])


def normalize_group_note_record(raw: dict[str, object]) -> GroupNoteRecord | None:
    text = str(raw.get("text") or "").strip()
    if not text:
        return None
    try:
        timestamp = int(raw.get("timestamp") or 0)
    except (TypeError, ValueError):
        timestamp = 0
    user_id = str(raw.get("user_id") or "").strip()
    sender_name = str(raw.get("sender_name") or "").strip() or user_id or "未知用户"
    return GroupNoteRecord(
        user_id=user_id,
        sender_name=sender_name,
        text=text,
        timestamp=timestamp,
        message_id=str(raw.get("message_id") or "").strip(),
    )


def format_group_notes_markdown(
    *,
    group_id: str,
    records: tuple[GroupNoteRecord, ...],
    generated_at: datetime,
) -> str:
    lines = [
        f"# 群聊记录导出 - {group_id}",
        "",
        f"- 来源：公开群上下文缓存 data/nonebot2/run/ai/group_context/{group_id}.json",
        f"- 导出时间：{generated_at.isoformat(timespec='seconds')}",
        f"- 消息数量：{len(records)}",
        "",
    ]
    for index, record in enumerate(records, start=1):
        timestamp_text = format_group_note_timestamp(record.timestamp)
        header = f"## {index}. {record.sender_name}"
        if record.user_id:
            header += f" ({record.user_id})"
        if timestamp_text:
            header += f" - {timestamp_text}"
        lines.extend([header, ""])
        if record.message_id:
            lines.extend([f"message_id: {record.message_id}", ""])
        lines.extend([record.text.strip(), ""])
    return "\n".join(lines).rstrip() + "\n"


def format_group_note_timestamp(timestamp: int) -> str:
    if timestamp <= 0:
        return ""
    try:
        return datetime.fromtimestamp(timestamp).astimezone().isoformat(timespec="seconds")
    except (OSError, ValueError, OverflowError):
        return ""


def build_group_note_export_filename(group_id: str, now: datetime) -> str:
    safe_group_id = re.sub(r"[^0-9A-Za-z_-]+", "_", str(group_id or "unknown")).strip("_") or "unknown"
    return f"group-{safe_group_id}-{now.strftime('%Y%m%d-%H%M%S')}.md"


def get_group_note_export_root() -> Path:
    return get_astrbot_data_root() / "exports" / "group_notes"


def get_astrbot_data_root() -> Path:
    astrbot_root = os.environ.get("ASTRBOT_ROOT", "").strip()
    if astrbot_root:
        return Path(astrbot_root).resolve() / "data"
    return get_workspace_root() / "data" / "astrbot" / "data"


def get_nonebot2_data_root() -> Path:
    return get_workspace_root() / "data" / "nonebot2" / "run"


def get_workspace_root() -> Path:
    astrbot_root = os.environ.get("ASTRBOT_ROOT", "").strip()
    if astrbot_root:
        return Path(astrbot_root).resolve().parents[1]
    return Path.cwd().resolve()
