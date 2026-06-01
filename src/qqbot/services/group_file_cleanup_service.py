from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SHAPEZ_GROUP_ID = "1163635014"
DEFAULT_OLD_FILE_GRACE_DAYS = 7
DEFAULT_MUTE_SECONDS = 3 * 24 * 60 * 60
DEFAULT_DELETE_AFTER_SECONDS = 3 * 24 * 60 * 60
DEFAULT_DAILY_SCAN_HOUR = 8
DEFAULT_PRIVATE_NOTICE_INTERVAL_SECONDS = 3.0
DEFAULT_CONFIRM_TEXTS = frozenset({"1", "已处理", "处理好了", "清理好了", "确认"})


@dataclass(frozen=True, slots=True)
class GroupFileInfo:
    file_id: str
    name: str
    size: int
    uploaded_at: int
    uploader_id: str
    busid: str = ""
    parent_folder_id: str = ""


@dataclass(frozen=True, slots=True)
class GroupFolderInfo:
    folder_id: str
    name: str


@dataclass(frozen=True, slots=True)
class GroupFileSnapshot:
    root_files: tuple[GroupFileInfo, ...]
    folders: tuple[GroupFolderInfo, ...]
    inner_files: tuple[GroupFileInfo, ...]


@dataclass(frozen=True, slots=True)
class ShapezPendingCleanup:
    user_id: str
    file_ids: tuple[str, ...]
    file_names: tuple[str, ...]
    first_detected_at: int
    last_checked_at: int
    muted_until: int
    notice_sent_at: int
    status: str = "pending"
    deleted_at: int = 0


@dataclass(slots=True)
class ShapezGroupFileCleanupState:
    last_scan_date: str = ""
    last_scan_at: int = 0
    pending: dict[str, ShapezPendingCleanup] = field(default_factory=dict)


class ShapezGroupFileCleanupStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> ShapezGroupFileCleanupState:
        if not self.path.exists():
            return ShapezGroupFileCleanupState()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ShapezGroupFileCleanupState()
        pending: dict[str, ShapezPendingCleanup] = {}
        raw_pending = raw.get("pending", {})
        if isinstance(raw_pending, dict):
            for user_id, item in raw_pending.items():
                if not isinstance(item, dict):
                    continue
                pending[str(user_id)] = ShapezPendingCleanup(
                    user_id=str(item.get("user_id", user_id)),
                    file_ids=tuple(str(value) for value in item.get("file_ids", ())),
                    file_names=tuple(str(value) for value in item.get("file_names", ())),
                    first_detected_at=int(item.get("first_detected_at", 0) or 0),
                    last_checked_at=int(item.get("last_checked_at", 0) or 0),
                    muted_until=int(item.get("muted_until", 0) or 0),
                    notice_sent_at=int(item.get("notice_sent_at", 0) or 0),
                    status=str(item.get("status", "pending")),
                    deleted_at=int(item.get("deleted_at", 0) or 0),
                )
        return ShapezGroupFileCleanupState(
            last_scan_date=str(raw.get("last_scan_date", "")),
            last_scan_at=int(raw.get("last_scan_at", 0) or 0),
            pending=pending,
        )

    def save(self, state: ShapezGroupFileCleanupState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "last_scan_date": state.last_scan_date,
            "last_scan_at": state.last_scan_at,
            "pending": {
                user_id: {
                    **asdict(item),
                    "file_ids": list(item.file_ids),
                    "file_names": list(item.file_names),
                }
                for user_id, item in state.pending.items()
            },
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class ShapezGroupFileCleanupService:
    def __init__(
        self,
        *,
        store: ShapezGroupFileCleanupStore,
        group_id: str = SHAPEZ_GROUP_ID,
        old_file_grace_days: int = DEFAULT_OLD_FILE_GRACE_DAYS,
        mute_seconds: int = DEFAULT_MUTE_SECONDS,
        delete_after_seconds: int = DEFAULT_DELETE_AFTER_SECONDS,
        daily_scan_hour: int = DEFAULT_DAILY_SCAN_HOUR,
        private_notice_interval_seconds: float = DEFAULT_PRIVATE_NOTICE_INTERVAL_SECONDS,
        timezone_name: str = "Asia/Shanghai",
        now_func: Callable[[], datetime] | None = None,
        sleep: Callable[[float], Any] = asyncio.sleep,
    ) -> None:
        self.store = store
        self.group_id = str(group_id)
        self.old_file_grace_days = max(0, int(old_file_grace_days))
        self.mute_seconds = max(60, int(mute_seconds))
        self.delete_after_seconds = max(60, int(delete_after_seconds))
        self.daily_scan_hour = int(daily_scan_hour)
        self.private_notice_interval_seconds = max(0.0, float(private_notice_interval_seconds))
        self.zone = _resolve_zone(timezone_name)
        self.now_func = now_func
        self.sleep = sleep

    async def fetch_snapshot(self, bot: Any) -> GroupFileSnapshot:
        root_payload = await bot.call_api("get_group_root_files", group_id=int(self.group_id))
        root_files = tuple(_parse_files(_extract_list(root_payload, "files", "file", "items")))
        folders = tuple(_parse_folders(_extract_list(root_payload, "folders", "folder")))
        inner_files: list[GroupFileInfo] = []
        for folder in folders:
            folder_payload = await bot.call_api(
                "get_group_files_by_folder",
                group_id=int(self.group_id),
                folder_id=folder.folder_id,
            )
            inner_files.extend(
                _parse_files(
                    _extract_list(folder_payload, "files", "file", "items"),
                    parent_folder_id=folder.folder_id,
                )
            )
        return GroupFileSnapshot(root_files=root_files, folders=folders, inner_files=tuple(inner_files))

    def find_violations(self, snapshot: GroupFileSnapshot, *, now: datetime | None = None) -> dict[str, tuple[GroupFileInfo, ...]]:
        current = self._coerce_now(now)
        cutoff = int((current - timedelta(days=self.old_file_grace_days)).timestamp())
        grouped: dict[str, list[GroupFileInfo]] = {}
        for file_info in snapshot.root_files:
            if not file_info.uploader_id:
                continue
            if file_info.uploaded_at <= 0 or file_info.uploaded_at > cutoff:
                continue
            grouped.setdefault(file_info.uploader_id, []).append(file_info)
        return {user_id: tuple(files) for user_id, files in grouped.items()}

    async def run_daily_scan(
        self,
        bot: Any,
        *,
        now: datetime | None = None,
        force: bool = False,
    ) -> dict[str, object]:
        current = self._coerce_now(now)
        state = self.store.load()
        if not force and not self.should_run_daily(state, current):
            return {"ran": False, "reason": "not_due"}
        result = await self.scan_and_enforce(bot, now=current)
        state = self.store.load()
        state.last_scan_date = current.date().isoformat()
        state.last_scan_at = int(current.timestamp())
        self.store.save(state)
        return {"ran": True, **result}

    async def scan_and_enforce(self, bot: Any, *, now: datetime | None = None) -> dict[str, object]:
        current = self._coerce_now(now)
        snapshot = await self.fetch_snapshot(bot)
        violations = self.find_violations(snapshot, now=current)
        state = self.store.load()
        notified = 0
        muted = 0
        deleted = 0
        for user_id, files in violations.items():
            file_names = tuple(file_info.name for file_info in files)
            file_ids = tuple(file_info.file_id for file_info in files)
            previous = state.pending.get(user_id)
            if previous is not None and previous.status == "pending" and _is_cleanup_expired(previous, current, self.delete_after_seconds):
                for file_info in files:
                    await self._delete_group_file(bot, file_info)
                    deleted += 1
                state.pending[user_id] = ShapezPendingCleanup(
                    user_id=user_id,
                    file_ids=file_ids,
                    file_names=file_names,
                    first_detected_at=previous.first_detected_at,
                    last_checked_at=int(current.timestamp()),
                    muted_until=previous.muted_until,
                    notice_sent_at=previous.notice_sent_at,
                    status="deleted",
                    deleted_at=int(current.timestamp()),
                )
                continue
            muted_until = int(current.timestamp()) + self.mute_seconds
            should_notify = previous is None or previous.status != "pending"
            state.pending[user_id] = ShapezPendingCleanup(
                user_id=user_id,
                file_ids=file_ids,
                file_names=file_names,
                first_detected_at=previous.first_detected_at if previous else int(current.timestamp()),
                last_checked_at=int(current.timestamp()),
                muted_until=muted_until,
                notice_sent_at=int(current.timestamp()) if should_notify else previous.notice_sent_at,
                status="pending",
                deleted_at=0,
            )
            if should_notify:
                await bot.call_api(
                    "set_group_ban",
                    group_id=int(self.group_id),
                    user_id=int(user_id),
                    duration=self.mute_seconds,
                )
                muted += 1
                await bot.call_api(
                    "send_private_msg",
                    user_id=int(user_id),
                    message=build_shapez_cleanup_notice(files),
                )
                notified += 1
                await self._sleep_after_private_notice()
        self.store.save(state)
        return {
            "root_file_count": len(snapshot.root_files),
            "folder_count": len(snapshot.folders),
            "inner_file_count": len(snapshot.inner_files),
            "violating_user_count": len(violations),
            "muted_user_count": muted,
            "notified_user_count": notified,
            "deleted_file_count": deleted,
        }

    async def handle_private_confirmation(
        self,
        bot: Any,
        *,
        user_id: int | str,
        text: str,
        now: datetime | None = None,
    ) -> bool:
        normalized = str(text).strip()
        if normalized not in DEFAULT_CONFIRM_TEXTS:
            return False
        user_key = str(user_id)
        state = self.store.load()
        pending = state.pending.get(user_key)
        if pending is None or pending.status != "pending":
            return False
        current = self._coerce_now(now)
        snapshot = await self.fetch_snapshot(bot)
        violations = self.find_violations(snapshot, now=current)
        if user_key in violations:
            state.pending[user_key] = ShapezPendingCleanup(
                user_id=pending.user_id,
                file_ids=tuple(file_info.file_id for file_info in violations[user_key]),
                file_names=tuple(file_info.name for file_info in violations[user_key]),
                first_detected_at=pending.first_detected_at,
                last_checked_at=int(current.timestamp()),
                muted_until=int(current.timestamp()) + self.mute_seconds,
                notice_sent_at=pending.notice_sent_at,
                status="pending",
                deleted_at=0,
            )
            self.store.save(state)
            await bot.call_api(
                "send_private_msg",
                user_id=int(user_key),
                message=build_shapez_cleanup_still_pending_message(state.pending[user_key].file_names),
            )
            return True
        state.pending.pop(user_key, None)
        self.store.save(state)
        await bot.call_api(
            "set_group_ban",
            group_id=int(self.group_id),
            user_id=int(user_key),
            duration=0,
        )
        await bot.call_api("send_private_msg", user_id=int(user_key), message="复核通过，已解除禁言。")
        return True

    async def _delete_group_file(self, bot: Any, file_info: GroupFileInfo) -> None:
        payload: dict[str, object] = {
            "group_id": int(self.group_id),
            "file_id": file_info.file_id,
        }
        if file_info.busid:
            payload["busid"] = int(file_info.busid) if file_info.busid.isdigit() else file_info.busid
        await bot.call_api("delete_group_file", **payload)

    async def _sleep_after_private_notice(self) -> None:
        if self.private_notice_interval_seconds > 0:
            await self.sleep(self.private_notice_interval_seconds)

    def should_run_daily(self, state: ShapezGroupFileCleanupState, now: datetime) -> bool:
        current = self._coerce_now(now)
        if state.last_scan_date == current.date().isoformat():
            return False
        scheduled_at = current.replace(hour=self.daily_scan_hour, minute=0, second=0, microsecond=0)
        return current >= scheduled_at

    def _coerce_now(self, now: datetime | None) -> datetime:
        if now is None:
            if self.now_func is not None:
                return self._coerce_now(self.now_func())
            return datetime.now(self.zone)
        if now.tzinfo is None:
            return now.replace(tzinfo=self.zone)
        return now.astimezone(self.zone)


def build_shapez_cleanup_notice(files: tuple[GroupFileInfo, ...]) -> str:
    sorted_files = _sort_files_by_size_desc(files)
    listed = "\n".join(f"- {file_info.name}（{_format_file_size(file_info.size)}）" for file_info in sorted_files[:10])
    more = "" if len(sorted_files) <= 10 else f"\n还有 {len(sorted_files) - 10} 个文件未列出。"
    summary = f"共 {len(sorted_files)} 个文件，总大小 {_format_file_size(sum(file_info.size for file_info in sorted_files))}。"
    return (
        "检测到你上传到shapez群的文件已经超过一周未归类或删除，已按试运行规则禁言 3 天。请把它们清理掉或移动到合适文件夹内。\n"
        f"{summary}\n"
        f"{listed}{more}\n"
        "处理完成后私聊回复 1，棉花糖会复核；复核通过后解除禁言。连续 3 天仍未处理时，残留的外层文件会被直接删除。"
    )


def build_shapez_cleanup_still_pending_message(file_names: tuple[str, ...]) -> str:
    listed = "\n".join(f"- {name}" for name in file_names[:10])
    return "复核还没通过，最外层仍有需要处理的旧文件：\n" + listed


def _sort_files_by_size_desc(files: tuple[GroupFileInfo, ...]) -> tuple[GroupFileInfo, ...]:
    return tuple(sorted(files, key=lambda file_info: (-file_info.size, file_info.name)))


def _format_file_size(size: int) -> str:
    value = max(0, int(size))
    units = ("B", "KB", "MB", "GB", "TB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(amount)} {unit}"
            return f"{amount:.1f} {unit}"
        amount /= 1024


def _is_cleanup_expired(pending: ShapezPendingCleanup, now: datetime, delete_after_seconds: int) -> bool:
    return int(now.timestamp()) - pending.first_detected_at >= delete_after_seconds


def _extract_list(payload: object, *keys: str) -> tuple[dict[str, object], ...]:
    if not isinstance(payload, dict):
        return ()
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return tuple(item for item in value if isinstance(item, dict))
        if isinstance(value, dict):
            nested = _extract_list(value, *keys)
            if nested:
                return nested
    return ()


def _parse_files(raw_files: tuple[dict[str, object], ...], *, parent_folder_id: str = "") -> tuple[GroupFileInfo, ...]:
    files: list[GroupFileInfo] = []
    for item in raw_files:
        file_id = _first_text(item, "file_id", "id")
        name = _first_text(item, "file_name", "name")
        uploader_id = _first_text(item, "uploader", "uploader_id", "user_id", "sender_id")
        if not file_id or not name:
            continue
        files.append(
            GroupFileInfo(
                file_id=file_id,
                name=name,
                size=_first_int(item, "file_size", "size"),
                uploaded_at=_first_int(item, "upload_time", "uploaded_at", "create_time", "modify_time"),
                uploader_id=uploader_id,
                busid=_first_text(item, "busid", "bus_id"),
                parent_folder_id=parent_folder_id,
            )
        )
    return tuple(files)


def _parse_folders(raw_folders: tuple[dict[str, object], ...]) -> tuple[GroupFolderInfo, ...]:
    folders: list[GroupFolderInfo] = []
    for item in raw_folders:
        folder_id = _first_text(item, "folder_id", "id")
        name = _first_text(item, "folder_name", "name")
        if folder_id:
            folders.append(GroupFolderInfo(folder_id=folder_id, name=name or folder_id))
    return tuple(folders)


def _first_text(item: dict[str, object], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _first_int(item: dict[str, object], *keys: str) -> int:
    text = _first_text(item, *keys)
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def _resolve_zone(timezone_name: str):
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        if timezone_name == "Asia/Shanghai":
            return timezone(timedelta(hours=8), name=timezone_name)
        if timezone_name == "UTC":
            return timezone.utc
        return datetime.now().astimezone().tzinfo or timezone.utc
