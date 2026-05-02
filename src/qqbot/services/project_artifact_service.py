from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from qqbot.services.codex_task_service import CodexProjectBinding, normalize_local_path


@dataclass(frozen=True, slots=True)
class ProjectZipArtifact:
    path: Path

    @property
    def file_name(self) -> str:
        return self.path.name


def find_latest_project_zip(project: CodexProjectBinding) -> ProjectZipArtifact | None:
    repo_path = normalize_local_path(project.repo_path)
    if not repo_path.is_dir():
        return None

    candidates = [
        path
        for path in repo_path.rglob("*.zip")
        if path.is_file() and _is_allowed_zip_path(path, repo_path)
    ]
    if not candidates:
        return None

    candidates.sort(
        key=lambda path: (
            _zip_priority(path),
            path.stat().st_mtime,
            path.name,
        ),
        reverse=True,
    )
    return ProjectZipArtifact(candidates[0])


def _is_allowed_zip_path(path: Path, repo_path: Path) -> bool:
    try:
        path.resolve().relative_to(repo_path.resolve())
    except ValueError:
        return False
    blocked_parts = {".git", ".venv", "node_modules", "__pycache__"}
    return not any(part in blocked_parts for part in path.parts)


def _zip_priority(path: Path) -> int:
    return 1 if "ModZips" in path.parts else 0
