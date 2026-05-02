from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.codex_task_service import CodexProjectBinding
from qqbot.services.project_artifact_service import find_latest_project_zip


def test_find_latest_project_zip_prefers_modzips(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    old_package = repo / "ModZips" / "old.zip"
    new_package = repo / "ModZips" / "new.zip"
    newer_unrelated = repo / "scratch" / "newer.zip"
    old_package.parent.mkdir(parents=True)
    newer_unrelated.parent.mkdir(parents=True)
    old_package.write_bytes(b"old")
    new_package.write_bytes(b"new")
    newer_unrelated.write_bytes(b"newer")
    old_time = 1000
    new_time = 2000
    unrelated_time = 3000
    os.utime(old_package, (old_time, old_time))
    os.utime(new_package, (new_time, new_time))
    os.utime(newer_unrelated, (unrelated_time, unrelated_time))
    project = CodexProjectBinding(
        project_id="mlj_dspmods",
        display_name="MLJ_DSPmods",
        repo_path=str(repo),
    )

    artifact = find_latest_project_zip(project)

    assert artifact is not None
    assert artifact.path == new_package
