from pathlib import Path

from qqbot.services import fe_artifact_publish_service as service


def test_build_latest_commit_message_includes_summary_body_and_stats(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run_git(repo_path: Path, *args: str) -> str:
        calls.append(args)
        if args[:3] == ("log", "-1", "--pretty=format:%h%n%s%n%b"):
            return "a178181\n功能：自动上传构建产物到QQ群\n补充 FE 产物发布说明"
        if args[:5] == ("show", "--stat", "--oneline", "--no-renames", "--format="):
            return "AfterBuildEvent.cs | 12 +++++++++---\n1 file changed, 9 insertions(+), 3 deletions(-)"
        return ""

    monkeypatch.setattr(service, "_run_git", fake_run_git)

    message = service.build_latest_commit_message(tmp_path)

    assert "本次 FE 构建对应提交：" in message
    assert "a178181 功能：自动上传构建产物到QQ群" in message
    assert "补充 FE 产物发布说明" in message
    assert "改动统计：" in message
    assert "AfterBuildEvent.cs | 12 +++++++++---" in message
    assert calls == [
        ("log", "-1", "--pretty=format:%h%n%s%n%b"),
        ("show", "--stat", "--oneline", "--no-renames", "--format=", "HEAD"),
    ]
