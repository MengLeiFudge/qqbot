from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from qqbot.services.group_file_cleanup_service import (
    SHAPEZ_GROUP_ID,
    ShapezGroupFileCleanupService,
    ShapezGroupFileCleanupStore,
)


class FakeGroupFileBot:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.root_payload: dict[str, object] = {"files": [], "folders": []}
        self.folder_payloads: dict[str, dict[str, object]] = {}

    async def call_api(self, api: str, **data: object) -> object:
        self.calls.append((api, data))
        if api == "get_group_root_files":
            return self.root_payload
        if api == "get_group_files_by_folder":
            return self.folder_payloads[str(data["folder_id"])]
        return {"ok": True}


class GroupBanFailingBot(FakeGroupFileBot):
    async def call_api(self, api: str, **data: object) -> object:
        if api == "set_group_ban":
            self.calls.append((api, data))
            raise RuntimeError("cannot ban owner")
        return await super().call_api(api, **data)


def _service(tmp_path: Path) -> ShapezGroupFileCleanupService:
    return ShapezGroupFileCleanupService(
        store=ShapezGroupFileCleanupStore(tmp_path / "state.json"),
        timezone_name="Asia/Shanghai",
    )


def _ts(days_ago: int) -> int:
    now = datetime(2026, 6, 2, 8, 0, tzinfo=timezone(timedelta(hours=8)))
    return int((now - timedelta(days=days_ago)).timestamp())


def test_scan_notifies_group_and_mutes_root_old_uploaders_by_size(tmp_path: Path) -> None:
    bot = FakeGroupFileBot()
    bot.root_payload = {
        "files": [
            {
                "file_id": "root-old",
                "file_name": "外层旧文件.zip",
                "file_size": 1_000_000,
                "upload_time": 0,
                "modify_time": _ts(8),
                "uploader_id": "10001",
            },
            {
                "file_id": "root-old-large",
                "file_name": "更大的外层旧文件.zip",
                "file_size": 3_000_000,
                "upload_time": _ts(8) * 1000,
                "uploader_id": "10001",
            },
            {
                "file_id": "root-new",
                "file_name": "外层新文件.zip",
                "file_size": 1000,
                "upload_time": _ts(2),
                "uploader_id": "10002",
            },
        ],
        "folders": [{"folder_id": "folder-a", "folder_name": "教程", "total_file_count": 575}],
    }
    bot.folder_payloads = {
        "folder-a": {
            "files": [
                {
                    "file_id": "inner-old",
                    "file_name": "内层旧文件.zip",
                    "file_size": 9_000_000,
                    "upload_time": _ts(30),
                    "uploader_id": "10003",
                }
            ]
        }
    }
    service = _service(tmp_path)

    result = asyncio.run(
        service.scan_and_notify_group(
            bot,
            now=datetime(2026, 6, 2, 8, 0, tzinfo=timezone(timedelta(hours=8))),
        )
    )

    assert result["root_file_count"] == 3
    assert result["inner_file_count"] == 1
    assert result["violating_user_count"] == 1
    assert result["violating_file_count"] == 2
    assert result["violating_total_size"] == 4_000_000
    assert bot.calls[:2] == [
        ("get_group_root_files", {"group_id": int(SHAPEZ_GROUP_ID), "file_count": 10000}),
        (
            "get_group_files_by_folder",
            {"group_id": int(SHAPEZ_GROUP_ID), "folder_id": "folder-a", "file_count": 10000},
        ),
    ]
    group_messages = [str(call[1]["message"]) for call in bot.calls if call[0] == "send_group_msg"]
    assert group_messages == [
        "该清理文件了喵！\n以下只统计超过一周、未归类到文件夹内的文件喵。\n请将自己的文件删除或移动到合适的文件夹喵！",
        "[CQ:at,qq=10001] 2 个，4.0 MB",
    ]
    assert (
        "set_group_ban",
        {"group_id": int(SHAPEZ_GROUP_ID), "user_id": 10001, "duration": 240},
    ) in bot.calls
    assert not [call for call in bot.calls if call[0] == "send_private_msg"]
    pending = service.store.load().pending["10001"]
    assert pending.group_id == SHAPEZ_GROUP_ID
    assert pending.file_ids == ("root-old-large", "root-old")
    assert pending.muted_until == int(_ts(0)) + 240


def test_scan_still_lists_user_but_skips_pending_when_mute_fails(tmp_path: Path) -> None:
    bot = GroupBanFailingBot()
    bot.root_payload = {
        "files": [
            {
                "file_id": "root-old",
                "file_name": "外层旧文件.zip",
                "file_size": 1_000_000,
                "upload_time": _ts(8),
                "uploader_id": "10001",
            }
        ],
        "folders": [],
    }
    service = _service(tmp_path)

    result = asyncio.run(
        service.scan_and_notify_group(
            bot,
            now=datetime(2026, 6, 2, 8, 0, tzinfo=timezone(timedelta(hours=8))),
        )
    )

    assert result["muted_user_count"] == 0
    assert result["failed_mute_count"] == 1
    assert [call for call in bot.calls if call[0] == "send_group_msg"]
    assert "10001" not in service.store.load().pending
