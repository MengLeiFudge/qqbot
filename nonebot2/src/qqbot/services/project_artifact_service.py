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


@dataclass(frozen=True, slots=True)
class ProjectArtifactNameFilter:
    request_aliases: tuple[str, ...]
    zip_keywords: tuple[str, ...]


PROJECT_ARTIFACT_FILTERS: dict[str, tuple[ProjectArtifactNameFilter, ...]] = {
    "mlj_dspmods": (
        ProjectArtifactNameFilter(
            request_aliases=("分馏", "万物分馏", "fe", "fractionateeverything"),
            zip_keywords=("fractionateeverything",),
        ),
        ProjectArtifactNameFilter(
            request_aliases=("getdspdata",),
            zip_keywords=("getdspdata",),
        ),
    ),
}


def find_latest_project_zip(
    project: CodexProjectBinding,
    request_text: str = "",
) -> ProjectZipArtifact | None:
    repo_path = normalize_local_path(project.repo_path)
    if not repo_path.is_dir():
        return None

    candidates = _list_project_zip_candidates(repo_path)
    filtered = _filter_zip_candidates_by_request(project, candidates, request_text)
    if filtered:
        candidates = filtered
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


def _list_project_zip_candidates(repo_path: Path) -> list[Path]:
    return [
        path
        for path in repo_path.rglob("*.zip")
        if path.is_file() and _is_allowed_zip_path(path, repo_path)
    ]


def _filter_zip_candidates_by_request(
    project: CodexProjectBinding,
    candidates: list[Path],
    request_text: str,
) -> list[Path]:
    filters = PROJECT_ARTIFACT_FILTERS.get(project.project_id, ())
    if not filters:
        return []
    normalized_request = _normalize_text(request_text)
    for item in filters:
        if not any(_normalize_text(alias) in normalized_request for alias in item.request_aliases):
            continue
        return [
            path
            for path in candidates
            if any(keyword in _normalize_text(path.name) for keyword in item.zip_keywords)
        ]
    return []


def _is_allowed_zip_path(path: Path, repo_path: Path) -> bool:
    try:
        path.resolve().relative_to(repo_path.resolve())
    except ValueError:
        return False
    blocked_parts = {".git", ".venv", "node_modules", "__pycache__"}
    return not any(part in blocked_parts for part in path.parts)


def _zip_priority(path: Path) -> int:
    return 1 if "ModZips" in path.parts else 0


def _normalize_text(text: str) -> str:
    return "".join(str(text).lower().split())
