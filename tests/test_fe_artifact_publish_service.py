import json
from pathlib import Path

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


def test_build_publish_message_prefers_event_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        service,
        "build_latest_commit_message",
        lambda repo_path: "本次 FE 构建对应提交：\nc251753 修复：避免分馏处理器静态初始化崩溃",
    )

    message = service.build_publish_message(
        tmp_path,
        "原因：用户反馈启动崩溃\n修复：移除跨 partial 静态初始化依赖\n方式：使用固定建筑类型数量",
    )

    assert "本次 FE 构建说明：" in message
    assert "原因：用户反馈启动崩溃" in message
    assert "修复：移除跨 partial 静态初始化依赖" in message
    assert "本次 FE 构建对应提交：" in message


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
