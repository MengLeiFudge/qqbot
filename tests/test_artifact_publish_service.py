from __future__ import annotations

import asyncio
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "astrbot-local-plugins"))

from astrbot_plugin_local_artifact_api.legacy_services.artifacts.publish_service import (
    LocalArtifactPublishContext,
    LocalArtifactPublishFile,
    calculate_sha256,
    publish_local_artifacts,
)


class FakeBot:
    self_id = "10000"

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.next_upload_message_id = 12345

    async def call_api(self, api: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((api, kwargs))
        if api == "get_group_root_files":
            return {
                "files": [
                    {
                        "file_name": kwargs.get("expected_name", "mod.zip"),
                        "uploader": self.self_id,
                        "file_id": "old-file",
                    }
                ]
            }
        if api == "upload_group_file":
            message_id = self.next_upload_message_id
            self.next_upload_message_id += 1
            return {"message_id": str(message_id)}
        if api == "send_group_msg":
            return {"message_id": "23456"}
        return {}


def test_publish_local_artifacts_skips_same_group_name_sha(tmp_path: Path) -> None:
    package = tmp_path / "mod.zip"
    package.write_bytes(b"same content")
    sha256 = calculate_sha256(package)
    bot = FakeBot()
    context = LocalArtifactPublishContext(
        project_id="mlj_dspmods",
        branch="master",
        commit_hash="abcdef1",
        commit_subject="修复：测试",
        commit_detail="验证：测试",
    )
    artifact = LocalArtifactPublishFile(
        path=package,
        name="mod.zip",
        targets=(319567534,),
        sha256=sha256,
    )

    first = asyncio.run(publish_local_artifacts(bot, [artifact], context, data_root=tmp_path))
    assert first.uploaded == [
        {
            "group_id": 319567534,
            "file": str(package),
            "name": "mod.zip",
            "sha256": sha256,
            "content_sha256": sha256,
        }
    ]
    assert not first.skipped
    assert any(api == "upload_group_file" for api, _ in bot.calls)

    bot.calls.clear()
    second = asyncio.run(publish_local_artifacts(bot, [artifact], context, data_root=tmp_path))

    assert second.uploaded == []
    assert second.deleted == []
    assert second.skipped == [
        {
            "group_id": 319567534,
            "file": str(package),
            "name": "mod.zip",
            "sha256": sha256,
            "content_sha256": sha256,
            "reason": "artifact content sha256 unchanged.",
        }
    ]
    assert bot.calls == []


def test_publish_local_artifacts_skips_by_content_sha_when_zip_sha_changes(tmp_path: Path) -> None:
    first_package = tmp_path / "first.zip"
    second_package = tmp_path / "second.zip"
    first_package.write_bytes(b"zip bytes 1")
    second_package.write_bytes(b"zip bytes 2")
    first_sha256 = calculate_sha256(first_package)
    second_sha256 = calculate_sha256(second_package)
    content_sha256 = "abc123content"
    bot = FakeBot()
    context = LocalArtifactPublishContext(project_id="mlj_dspmods", branch="master", commit_hash="abcdef1")

    first_artifact = LocalArtifactPublishFile(
        path=first_package,
        name="mod.zip",
        targets=(319567534,),
        sha256=first_sha256,
        content_sha256=content_sha256,
    )
    second_artifact = LocalArtifactPublishFile(
        path=second_package,
        name="mod.zip",
        targets=(319567534,),
        sha256=second_sha256,
        content_sha256=content_sha256,
    )

    first = asyncio.run(publish_local_artifacts(bot, [first_artifact], context, data_root=tmp_path))
    assert first.uploaded[0]["sha256"] == first_sha256
    assert first.uploaded[0]["content_sha256"] == content_sha256

    bot.calls.clear()
    second = asyncio.run(publish_local_artifacts(bot, [second_artifact], context, data_root=tmp_path))

    assert second.uploaded == []
    assert second.deleted == []
    assert second.skipped == [
        {
            "group_id": 319567534,
            "file": str(second_package),
            "name": "mod.zip",
            "sha256": second_sha256,
            "content_sha256": content_sha256,
            "reason": "artifact content sha256 unchanged.",
        }
    ]
    assert bot.calls == []


def test_publish_local_artifacts_tracks_sha_per_upload_name(tmp_path: Path) -> None:
    package = tmp_path / "shared.zip"
    package.write_bytes(b"same content")
    sha256 = calculate_sha256(package)
    bot = FakeBot()
    context = LocalArtifactPublishContext(project_id="mlj_dspmods", branch="master", commit_hash="abcdef1")

    first_artifact = LocalArtifactPublishFile(
        path=package,
        name="first.zip",
        targets=(319567534,),
        sha256=sha256,
    )
    second_artifact = LocalArtifactPublishFile(
        path=package,
        name="second.zip",
        targets=(319567534,),
        sha256=sha256,
    )

    asyncio.run(publish_local_artifacts(bot, [first_artifact], context, data_root=tmp_path))
    bot.calls.clear()
    result = asyncio.run(publish_local_artifacts(bot, [second_artifact], context, data_root=tmp_path))

    assert len(result.uploaded) == 1
    assert result.uploaded[0]["name"] == "second.zip"
    assert not result.skipped
    assert any(api == "upload_group_file" for api, _ in bot.calls)


def test_publish_local_artifacts_sends_one_notice_after_multi_file_upload(tmp_path: Path) -> None:
    first_package = tmp_path / "first.zip"
    second_package = tmp_path / "second.zip"
    first_package.write_bytes(b"first content")
    second_package.write_bytes(b"second content")
    first_sha256 = calculate_sha256(first_package)
    second_sha256 = calculate_sha256(second_package)
    bot = FakeBot()
    context = LocalArtifactPublishContext(
        project_id="mlj_dspmods",
        branch="master",
        commit_hash="abcdef123456",
        commit_subject="构建：测试多包通知",
        commit_detail="验证：测试",
    )
    artifacts = [
        LocalArtifactPublishFile(
            path=first_package,
            name="first.zip",
            targets=(319567534,),
            sha256=first_sha256,
        ),
        LocalArtifactPublishFile(
            path=second_package,
            name="second.zip",
            targets=(319567534,),
            sha256=second_sha256,
        ),
    ]

    result = asyncio.run(publish_local_artifacts(bot, artifacts, context, data_root=tmp_path))

    assert [item["name"] for item in result.uploaded] == ["first.zip", "second.zip"]
    upload_calls = [kwargs for api, kwargs in bot.calls if api == "upload_group_file"]
    message_calls = [kwargs for api, kwargs in bot.calls if api == "send_group_msg"]
    assert [item["name"] for item in upload_calls] == ["first.zip", "second.zip"]
    assert len(message_calls) == 1
    assert str(message_calls[0]["message"]).startswith("[CQ:reply,id=12346]abcdef1 构建：测试多包通知")
