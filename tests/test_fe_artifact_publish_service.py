import json
from pathlib import Path
import asyncio

from qqbot.services import fe_artifact_publish_service as service


def test_build_latest_commit_message_includes_summary_body_without_stats(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run_git(repo_path: Path, *args: str) -> str:
        calls.append(args)
        if args[:3] == ("log", "-1", "--pretty=format:%h%n%s%n%b"):
            return "a178181\n功能：自动上传构建产物到QQ群\n补充 FE 产物发布说明"
        return ""

    monkeypatch.setattr(service, "_run_git", fake_run_git)

    message = service.build_latest_commit_message(tmp_path)

    assert "本次 FE 构建对应提交：" in message
    assert "a178181 功能：自动上传构建产物到QQ群" in message
    assert "补充 FE 产物发布说明" in message
    assert "改动统计：" not in message
    assert calls == [("log", "-1", "--pretty=format:%h%n%s%n%b")]


def test_build_publish_message_formats_fix_summary_and_quotes_upload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        service,
        "read_latest_commit_summary",
        lambda repo_path: service.CommitSummary(
            short_hash="c251753",
            title="修复：避免分馏处理器静态初始化崩溃",
            body="",
        ),
    )

    message = service.build_publish_message(
        tmp_path,
        "原因：用户反馈启动崩溃\n原因：跨 partial 静态字段初始化顺序不稳定\n修复：移除跨 partial 静态初始化依赖\n方式：使用固定建筑类型数量\n验证：MSBuild 0 warning 0 error",
        reply_message_id="12345",
    )

    assert message == (
        "[CQ:reply,id=12345]\n"
        "c251753 修复：避免分馏处理器静态初始化崩溃\n\n"
        "根本原因：\n"
        "1.用户反馈启动崩溃\n"
        "2.跨 partial 静态字段初始化顺序不稳定\n\n"
        "修复方式：\n"
        "1.使用固定建筑类型数量\n"
        "2.移除跨 partial 静态初始化依赖\n\n"
        "验证：\n"
        "1.MSBuild 0 warning 0 error"
    )


def test_build_publish_message_formats_feature_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        service,
        "read_latest_commit_summary",
        lambda repo_path: service.CommitSummary(
            short_hash="2016562",
            title="功能：构建上传携带FE发布说明",
            body="",
        ),
    )

    message = service.build_publish_message(
        tmp_path,
        "原因：用户不想手动整理上传说明\n新增：上传事件携带发布说明\n使用：AfterBuildEvent 传自然语言说明\n影响：群消息不再显示文件级 diff\n验证：qqbot 全量测试通过",
    )

    assert message == (
        "2016562 功能：构建上传携带FE发布说明\n\n"
        "背景原因：\n"
        "1.用户不想手动整理上传说明\n\n"
        "新增能力：\n"
        "1.上传事件携带发布说明\n\n"
        "使用方式：\n"
        "1.AfterBuildEvent 传自然语言说明\n\n"
        "影响范围：\n"
        "1.群消息不再显示文件级 diff\n\n"
        "验证：\n"
        "1.qqbot 全量测试通过"
    )


def test_build_publish_message_formats_refactor_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        service,
        "read_latest_commit_summary",
        lambda repo_path: service.CommitSummary(
            short_hash="abc1234",
            title="重构：整理FE发布说明模板",
            body="",
        ),
    )

    message = service.build_publish_message(
        tmp_path,
        "原因：说明字段逐步变多\n结构：按提交类型拆分段落\n影响：不改变上传流程\n验证：单测通过",
    )

    assert message == (
        "abc1234 重构：整理FE发布说明模板\n\n"
        "调整原因：\n"
        "1.说明字段逐步变多\n\n"
        "结构变化：\n"
        "1.按提交类型拆分段落\n\n"
        "行为影响：\n"
        "1.不改变上传流程\n\n"
        "验证：\n"
        "1.单测通过"
    )


def test_build_publish_message_formats_misc_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        service,
        "read_latest_commit_summary",
        lambda repo_path: service.CommitSummary(
            short_hash="def5678",
            title="杂项：补充FE发布说明约定",
            body="",
        ),
    )

    message = service.build_publish_message(
        tmp_path,
        "变更：记录发布说明格式约定\n补充：不再发送文件级 diff\n验证：文档检查通过",
    )

    assert message == (
        "def5678 杂项：补充FE发布说明约定\n\n"
        "变更内容：\n"
        "1.记录发布说明格式约定\n\n"
        "补充说明：\n"
        "1.不再发送文件级 diff\n\n"
        "验证：\n"
        "1.文档检查通过"
    )


def test_read_publish_summary_from_afterbuild_result(tmp_path: Path) -> None:
    result_path = tmp_path / "afterbuild-result.json"
    result_path.write_text(
        json.dumps(
            {
                "automation_mode": True,
                "publish_summary": "原因：用户反馈启动崩溃\n修复：移除静态初始化顺序依赖",
            }
        ),
        encoding="utf-8",
    )

    summary = service.read_publish_summary_from_afterbuild_result(result_path)

    assert summary == "原因：用户反馈启动崩溃\n修复：移除静态初始化顺序依赖"


def test_find_uploaded_file_message_id_reads_group_history() -> None:
    class FakeBot:
        async def call_api(self, api: str, **data: object) -> dict[str, object]:
            assert api == "get_group_msg_history"
            assert data["group_id"] == 319567534
            return {
                "messages": [
                    {
                        "message_id": 10001,
                        "message": "普通消息",
                    },
                    {
                        "message_id": 10002,
                        "message": [
                            {
                                "type": "file",
                                "data": {
                                    "file": "FractionateEverything_2.3.0.zip",
                                },
                            }
                        ],
                    },
                ],
            }

    message_id = asyncio.run(
        service.find_uploaded_file_message_id(
            FakeBot(),
            319567534,
            "FractionateEverything_2.3.0.zip",
            retries=1,
        )
    )

    assert message_id == "10002"


def test_find_uploaded_file_message_id_uses_latest_matching_message() -> None:
    class FakeBot:
        async def call_api(self, api: str, **data: object) -> dict[str, object]:
            return {
                "data": {
                    "messages": [
                        {
                            "message_id": 10001,
                            "raw_message": "[文件：FractionateEverything_2.3.0.zip]",
                        },
                        {
                            "message_id": 10002,
                            "raw_message": "[文件：FractionateEverything_2.3.0.zip]",
                        },
                    ],
                },
            }

    message_id = asyncio.run(
        service.find_uploaded_file_message_id(
            FakeBot(),
            319567534,
            "FractionateEverything_2.3.0.zip",
            retries=1,
        )
    )

    assert message_id == "10002"
