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


def _service(tmp_path: Path) -> ShapezGroupFileCleanupService:
    return ShapezGroupFileCleanupService(
        store=ShapezGroupFileCleanupStore(tmp_path / "state.json"),
        timezone_name="Asia/Shanghai",
    )


def _ts(days_ago: int) -> int:
    now = datetime(2026, 6, 2, 8, 0, tzinfo=timezone(timedelta(hours=8)))
    return int((now - timedelta(days=days_ago)).timestamp())


def test_fetch_snapshot_distinguishes_root_files_and_folder_files(tmp_path: Path) -> None:
    bot = FakeGroupFileBot()
    bot.root_payload = {
        "files": [
            {
                "file_id": "root-old",
                "file_name": "外层旧文件.zip",
                "file_size": 1024,
                "upload_time": _ts(8),
                "uploader_id": "10001",
            }
        ],
        "folders": [{"folder_id": "folder-a", "folder_name": "教程"}],
    }
    bot.folder_payloads = {
        "folder-a": {
            "files": [
                {
                    "file_id": "inner-old",
                    "file_name": "内层旧文件.zip",
                    "file_size": 2048,
                    "upload_time": _ts(30),
                    "uploader_id": "10002",
                }
            ]
        }
    }
    service = _service(tmp_path)

    snapshot = asyncio.run(service.fetch_snapshot(bot))
    violations = service.find_violations(
        snapshot,
        now=datetime(2026, 6, 2, 8, 0, tzinfo=timezone(timedelta(hours=8))),
    )

    assert [file.name for file in snapshot.root_files] == ["外层旧文件.zip"]
    assert [file.name for file in snapshot.inner_files] == ["内层旧文件.zip"]
    assert snapshot.inner_files[0].parent_folder_id == "folder-a"
    assert set(violations) == {"10001"}
    assert violations["10001"][0].name == "外层旧文件.zip"
    assert bot.calls[:2] == [
        ("get_group_root_files", {"group_id": int(SHAPEZ_GROUP_ID)}),
        (
            "get_group_files_by_folder",
            {"group_id": int(SHAPEZ_GROUP_ID), "folder_id": "folder-a"},
        ),
    ]


def test_scan_mutes_and_notifies_only_root_old_file_uploaders(tmp_path: Path) -> None:
    bot = FakeGroupFileBot()
    bot.root_payload = {
        "files": [
            {
                "file_id": "root-old",
                "file_name": "外层旧文件.zip",
                "file_size": 1024,
                "upload_time": _ts(8),
                "uploader_id": "10001",
            },
            {
                "file_id": "root-new",
                "file_name": "外层新文件.zip",
                "file_size": 1024,
                "upload_time": _ts(2),
                "uploader_id": "10002",
            },
        ],
        "folders": [{"folder_id": "folder-a", "folder_name": "教程"}],
    }
    bot.folder_payloads = {
        "folder-a": {
            "files": [
                {
                    "file_id": "inner-old",
                    "file_name": "内层旧文件.zip",
                    "file_size": 1024,
                    "upload_time": _ts(30),
                    "uploader_id": "10003",
                }
            ]
        }
    }
    service = _service(tmp_path)

    result = asyncio.run(
        service.scan_and_enforce(
            bot,
            now=datetime(2026, 6, 2, 8, 0, tzinfo=timezone(timedelta(hours=8))),
        )
    )

    assert result["root_file_count"] == 2
    assert result["inner_file_count"] == 1
    assert result["violating_user_count"] == 1
    assert (
        "set_group_ban",
        {"group_id": int(SHAPEZ_GROUP_ID), "user_id": 10001, "duration": 24 * 60 * 60},
    ) in bot.calls
    private_calls = [call for call in bot.calls if call[0] == "send_private_msg"]
    assert len(private_calls) == 1
    assert private_calls[0][1]["user_id"] == 10001
    assert "外层旧文件.zip" in str(private_calls[0][1]["message"])
    assert "内层旧文件.zip" not in str(private_calls[0][1]["message"])


def test_private_confirmation_unmutes_after_root_files_are_cleaned(tmp_path: Path) -> None:
    bot = FakeGroupFileBot()
    bot.root_payload = {
        "files": [
            {
                "file_id": "root-old",
                "file_name": "外层旧文件.zip",
                "file_size": 1024,
                "upload_time": _ts(8),
                "uploader_id": "10001",
            }
        ],
        "folders": [],
    }
    service = _service(tmp_path)
    now = datetime(2026, 6, 2, 8, 0, tzinfo=timezone(timedelta(hours=8)))
    asyncio.run(service.scan_and_enforce(bot, now=now))
    bot.calls.clear()
    bot.root_payload = {"files": [], "folders": []}

    handled = asyncio.run(service.handle_private_confirmation(bot, user_id="10001", text="1", now=now))

    assert handled is True
    assert bot.calls == [
        (
            "get_group_root_files",
            {"group_id": int(SHAPEZ_GROUP_ID)},
        ),
        (
            "set_group_ban",
            {"group_id": int(SHAPEZ_GROUP_ID), "user_id": 10001, "duration": 0},
        ),
        (
            "send_private_msg",
            {"user_id": 10001, "message": "复核通过，已解除禁言。"},
        ),
    ]


def test_daily_scan_runs_after_8_once_per_day(tmp_path: Path) -> None:
    bot = FakeGroupFileBot()
    service = _service(tmp_path)
    before = datetime(2026, 6, 2, 7, 59, tzinfo=timezone(timedelta(hours=8)))
    at_eight = datetime(2026, 6, 2, 8, 0, tzinfo=timezone(timedelta(hours=8)))
    later = datetime(2026, 6, 2, 20, 0, tzinfo=timezone(timedelta(hours=8)))

    assert asyncio.run(service.run_daily_scan(bot, now=before)) == {"ran": False, "reason": "not_due"}
    assert asyncio.run(service.run_daily_scan(bot, now=at_eight))["ran"] is True
    assert asyncio.run(service.run_daily_scan(bot, now=later)) == {"ran": False, "reason": "not_due"}
    assert [api for api, _data in bot.calls] == ["get_group_root_files"]
