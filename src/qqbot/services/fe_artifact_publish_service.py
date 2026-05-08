from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
from typing import Any

from qqbot.services.codex_task_service import normalize_local_path

FE_ARTIFACT_NAME_RE = re.compile(r"^FractionateEverything_\d+(?:\.\d+)*\.zip$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class FeArtifactPublishResult:
    uploaded: list[dict[str, str]]
    deleted: list[str]


def select_fe_package_from_afterbuild_result(
    result_path: str | Path,
    repo_path: str | Path,
) -> Path | None:
    path = normalize_local_path(result_path)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    raw_packages = payload.get("generated_packages")
    if not isinstance(raw_packages, list):
        return None

    repo = normalize_local_path(repo_path)
    candidates = [
        package
        for raw_package in raw_packages
        if isinstance(raw_package, str)
        for package in [_normalize_fe_package(raw_package, repo)]
        if package is not None
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda package: (package.stat().st_mtime, package.name), reverse=True)
    return candidates[0]


def read_publish_summary_from_afterbuild_result(result_path: str | Path) -> str:
    path = normalize_local_path(result_path)
    if not path.is_file():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    summary = payload.get("publish_summary")
    return summary.strip() if isinstance(summary, str) else ""


async def publish_fe_artifact(
    bot: Any,
    group_id: int,
    package: str | Path,
    repo_path: str | Path | None = None,
    message: str = "",
) -> FeArtifactPublishResult:
    package_path = normalize_local_path(package)
    deleted = await delete_old_fe_group_files(bot, group_id)
    await bot.call_api(
        "upload_group_file",
        group_id=group_id,
        file=str(package_path),
        name=package_path.name,
    )
    publish_message = build_publish_message(repo_path, message)
    if publish_message:
        await bot.call_api("send_group_msg", group_id=group_id, message=publish_message)
    return FeArtifactPublishResult(
        uploaded=[{"file": str(package_path), "name": package_path.name}],
        deleted=deleted,
    )


async def delete_old_fe_group_files(bot: Any, group_id: int) -> list[str]:
    payload = await bot.call_api("get_group_root_files", group_id=group_id)
    files = _extract_group_files(payload)
    deleted: list[str] = []
    self_id = str(getattr(bot, "self_id", ""))
    for file_info in files:
        name = _first_text(file_info, "file_name", "name")
        if not FE_ARTIFACT_NAME_RE.fullmatch(name):
            continue
        uploader = _first_text(file_info, "uploader", "uploader_id", "user_id", "sender_id")
        if self_id and uploader and uploader != self_id:
            continue
        file_id = _first_text(file_info, "file_id", "id")
        if not file_id:
            continue
        delete_args: dict[str, object] = {
            "group_id": group_id,
            "file_id": file_id,
        }
        busid = _first_value(file_info, "busid", "bus_id")
        if busid is not None:
            delete_args["busid"] = busid
        await bot.call_api("delete_group_file", **delete_args)
        deleted.append(name)
    return deleted


def is_fe_artifact_path(path: str | Path) -> bool:
    return FE_ARTIFACT_NAME_RE.fullmatch(Path(str(path)).name) is not None


def build_publish_message(repo_path: str | Path | None, message: str = "") -> str:
    lines: list[str] = []
    normalized_message = message.strip()
    if normalized_message:
        lines.extend(["本次 FE 构建说明：", normalized_message])
    if repo_path is not None:
        commit_message = build_latest_commit_message(repo_path)
        if commit_message:
            if lines:
                lines.append("")
            lines.append(commit_message)
    return "\n".join(lines).strip()


def build_latest_commit_message(repo_path: str | Path) -> str:
    repo = normalize_local_path(repo_path)
    if not repo.is_dir():
        return ""
    summary = _run_git(repo, "log", "-1", "--pretty=format:%h%n%s%n%b")
    if not summary:
        return ""
    parts = [part.strip() for part in summary.splitlines()]
    short_hash = parts[0] if parts else ""
    title = parts[1] if len(parts) > 1 else ""
    body = "\n".join(part for part in parts[2:] if part).strip()
    lines = [
        "本次 FE 构建对应提交：",
        f"{short_hash} {title}".strip(),
    ]
    if body:
        lines.extend(["", body])
    return "\n".join(line for line in lines if line is not None).strip()


def _normalize_fe_package(raw_path: str, repo_path: Path) -> Path | None:
    package = normalize_local_path(raw_path)
    if not package.is_file() or not is_fe_artifact_path(package):
        return None
    try:
        package.resolve().relative_to(repo_path.resolve())
    except ValueError:
        return None
    return package


def _run_git(repo_path: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_path,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _extract_group_files(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("files", "file", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _first_text(file_info: dict[str, Any], *keys: str) -> str:
    value = _first_value(file_info, *keys)
    return "" if value is None else str(value)


def _first_value(file_info: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in file_info:
            return file_info[key]
    return None
